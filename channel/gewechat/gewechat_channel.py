import os
import json
import uuid
import cv2
from PIL import Image
import requests
import web
from urllib.parse import urlparse
import wave
import struct
import os
import pilk  # 使用 pilk 库进行 SILK 编码
from bridge.context import Context
from bridge.reply import Reply, ReplyType
from channel.chat_channel import ChatChannel
from channel.gewechat.gewechat_message import GeWeChatMessage
from common.log import logger
from common.singleton import singleton
from common.tmp_dir import TmpDir
from common.utils import compress_imgfile, fsize
from config import conf, save_config, pconf
from lib.gewechat import GewechatClient
from voice.audio_convert import split_audio, any_to_sil
import time

MAX_UTF8_LEN = 2048


@singleton
class GeWeChatChannel(ChatChannel):
    NOT_SUPPORT_REPLYTYPE = []

    def __init__(self):
        super().__init__()

        self.base_url = conf().get("gewechat_base_url")
        if not self.base_url:
            logger.error("[gewechat] base_url 未设置")
            return
        self.token = conf().get("gewechat_token")
        self.client = GewechatClient(self.base_url, self.token)

        # 如果token为空，尝试获取token
        if not self.token:
            logger.warning("[gewechat] token 未设置，尝试获取 token")
            token_resp = self.client.get_token()
            # {'ret': 200, 'msg': '执行成功', 'data': 'tokenxxx'}
            if token_resp.get("ret") != 200:
                logger.error(f"[gewechat] 获取 token 失败: {token_resp}")
                return
            self.token = token_resp.get("data")
            conf().set("gewechat_token", self.token)
            save_config()
            logger.info(f"[gewechat] 新的 token 已保存: {self.token}")
            self.client = GewechatClient(self.base_url, self.token)

        self.app_id = conf().get("gewechat_app_id")
        if not self.app_id:
            logger.warning("[gewechat] app_id 未设置，尝试在登录时获取新的 app_id")

        self.download_url = conf().get("gewechat_download_url")
        if not self.download_url:
            logger.warning("[gewechat] download_url 未设置，无法下载图片")

        logger.info(f"[gewechat] 初始化: base_url: {self.base_url}, token: {self.token}, app_id: {self.app_id}, download_url: {self.download_url}")

    def startup(self):
        # 如果app_id为空或登录后获取到新的app_id，保存配置
        app_id, error_msg = self.client.login(self.app_id)
        if error_msg:
            logger.error(f"[gewechat] 登录失败: {error_msg}")
            return

        # 如果原来的self.app_id为空或登录后获取到新的app_id，保存配置
        if not self.app_id or self.app_id != app_id:
            conf().set("gewechat_app_id", app_id)
            save_config()
            logger.info(f"[gewechat] 新的 app_id 已保存: {app_id}")
            self.app_id = app_id

        # 获取回调地址，示例地址：http://172.17.0.1:9919/v2/api/callback/collect  
        callback_url = conf().get("gewechat_callback_url")
        if not callback_url:
            logger.error("[gewechat] callback_url 未设置，无法启动回调服务器")
            return

        # 创建新线程设置回调地址
        import threading
        def set_callback():
            # 等待服务器启动（给予适当的启动时间）
            import time
            logger.info("[gewechat] 等待服务器启动3秒，然后设置回调")
            time.sleep(3)

            # 设置回调地址，{ "ret": 200, "msg": "操作成功" }
            callback_resp = self.client.set_callback(self.token, callback_url)
            if callback_resp.get("ret") != 200:
                logger.error(f"[gewechat] 设置回调地址失败: {callback_resp}")
                return
            logger.info("[gewechat] 回调地址设置成功")

        callback_thread = threading.Thread(target=set_callback, daemon=True)
        callback_thread.start()

        # 从回调地址中解析出端口与url path，启动回调服务器  
        parsed_url = urlparse(callback_url)
        path = parsed_url.path
        port = parsed_url.port
        logger.info(f"[gewechat] 启动回调服务器: {callback_url}")
        urls = (path, "channel.gewechat.gewechat_channel.Query")
        app = web.application(urls, globals(), autoreload=False)
        web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", port))

    def send_voice2(self, receiver, content):
        # 获取每段音频的时长
        def get_segment_durations(file_paths):
            from pydub import AudioSegment
            durations = []
            for path in file_paths:
                audio = AudioSegment.from_file(path)
                durations.append(len(audio))
                return durations

        # 分割音频文件
        audio_length_ms, files = split_audio(content, 60 * 1000)
        segment_durations = get_segment_durations(files)
        for fcontent, s in zip(files, segment_durations):
            print(f'{s}----语音时间---地址---{fcontent}')
            silk_path = fcontent + '.silk'
            duration = any_to_sil(fcontent, silk_path)
            callback_url = conf().get("gewechat callback url")
            silk_url = callback_url + "?file=" + silk_path
            self.client.post_voice(self.app_id, receiver, silk_url, duration)
            logger.info(f"[gewechat]发送语音内容 {receiver}: {silk_url}, 时间: {duration / 1000.0} 秒")
            time.sleep(s / 1080)

    def send_voice(self, to_wxid, reply_text):
        vrc = pconf('voice_reply')
        url = f"{vrc['voice_models'][vrc['voice_model_now']]}&text={reply_text}"
        logger.info(f"[gewechat] 发送语音内容={reply_text}, 接收人={to_wxid},url = {url}")

        # 将 WAV 文件转换为 SILK 格式
        def convert_wav_to_silk(wav_file_path, silk_file_path=None):
            """
            将 WAV 文件转换为 SILK 格式
            :param wav_file_path: 输入的 WAV 文件路径
            :param silk_file_path: 输出的 SILK 文件路径（可选）
            :return: 转换成功的 SILK 文件路径，或 None（转换失败）
            """
            try:
                # 如果未指定输出路径，则自动生成
                if silk_file_path is None:
                    base_name = os.path.splitext(os.path.basename(wav_file_path))[0]
                    silk_file_path = os.path.join(os.path.dirname(wav_file_path), f"{base_name}.silk")

                # 分离文件名和扩展名
                pcm_file_path = os.path.splitext(wav_file_path)[0] + ".pcm"

                # WAV 转 PCM
                with wave.open(wav_file_path, 'rb') as wav_file:
                    params = wav_file.getparams()
                    nchannels, sampwidth, framerate, nframes = params[:4]
                    frames = wav_file.readframes(nframes)

                # 将 WAV 数据解码为 PCM
                pcm_data = struct.unpack(f"<{nframes * nchannels}h", frames)
                # 保存为 PCM 文件
                with open(pcm_file_path, 'wb') as pcm_file:
                    pcm_file.write(struct.pack(f"<{len(pcm_data)}h", *pcm_data))

                # PCM 转 Silk
                duration = pilk.encode(pcm_file_path, silk_file_path, pcm_rate=framerate, tencent=True)

                # 清理临时 PCM 文件
                os.remove(pcm_file_path)

                print(f"转换完成: {silk_file_path} (时长: {duration} 秒)")
                return silk_file_path, duration

            except Exception as e:
                print(f"Error converting WAV to Silk: {str(e)}")
                return None, None

        try:
            # 发起 GET 请求，下载文件
            response = requests.get(url)
            response.raise_for_status()  # 检查请求是否成功
            fid = str(uuid.uuid4())
            # 创建临时文件保存下载的 .wav 文件
            temp_wav_path = f"{TmpDir().path()}wav_audio_{fid}.wav"
            with open(temp_wav_path, "wb") as f:
                f.write(response.content)

            # 将 .wav 文件转换为 .silk 格式
            temp_silk_path, voice_duration = convert_wav_to_silk(temp_wav_path)
            silk_path = f"{conf().get('gewechat_callback_url')}?file={temp_silk_path}"
            logger.info(f"返回 .silk gewechat_callback_url文件的路径: {silk_path}")
            # 发送语音
            if voice_duration > 60:
                voice_duration = 60
            self.client.post_voice(self.app_id, to_wxid, silk_path, voice_duration * 1000)
            return silk_path

        except Exception as e:
            print(f"语音转换失败: {e}")
            raise
            # return None

    def send_video(self, to_wxid, video_url):

        try:
            # 下载视频到本地临时目录
            video_file_name = f"video_{str(uuid.uuid4())}.mp4"
            video_file_path = TmpDir().path() + video_file_name

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            # 下载视频
            with requests.get(video_url, headers=headers, stream=True) as r:
                r.raise_for_status()
                with open(video_file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            # 生成缩略图
            thumb_file_name = f"thumb_{str(uuid.uuid4())}.jpg"
            thumb_file_path = TmpDir().path() + thumb_file_name

            # 使用OpenCV读取视频第一帧作为缩略图
            cap = cv2.VideoCapture(video_file_path)
            ret, frame = cap.read()

            if ret:
                # 获取视频时长
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                video_duration = int(frame_count / fps) if fps > 0 else 10

                # 调整图片大小为480x270
                # frame = cv2.resize(frame, (480, 270))
                frame = cv2.resize(frame, (270, 480))

                # 转换为RGB格式
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # 使用PIL保存为JPEG
                image = Image.fromarray(frame_rgb)
                image.save(thumb_file_path, 'JPEG', quality=95)
            else:
                # 如果无法读取视频帧，创建一个默认的黑色缩略图
                image = Image.new('RGB', (480, 270), color='black')
                image.save(thumb_file_path, 'JPEG', quality=95)

            cap.release()

            # 构造本地URL
            callback_url = conf().get("gewechat_callback_url")
            local_video_url = callback_url + "?file=" + video_file_path
            local_thumb_url = callback_url + "?file=" + thumb_file_path

            # 发送视频
            resp = self.client.post_video(
                self.app_id,
                to_wxid,
                local_video_url,
                local_thumb_url,  # 使用生成的缩略图
                video_duration
            )

            if resp.get("ret") != 200:
                logger.error(f"[gewechat] send video failed: {resp}")
                return None

            return resp.get("data")

        except Exception as e:
            logger.error(f"[gewechat] send video error: {e}")
            return None

    def send(self, reply: Reply, context: Context):
        receiver = context["receiver"]
        gewechat_message = context.get("msg")
        if reply.type in [ReplyType.TEXT, ReplyType.ERROR, ReplyType.INFO]:  # 文本
            if pconf("voice_reply").get("open_voice_reply"):
                # self.client.post_voice(self.app_id, receiver, voice_url,2000)
                # self.send_voice(receiver, reply.content)
                self.send_voice2(receiver, reply.content)
            else:
                reply_text = reply.content
                ats = ""
                if gewechat_message and gewechat_message.is_group:
                    ats = gewechat_message.actual_user_id
                self.client.post_text(self.app_id, receiver, reply_text, ats)
                logger.info("[gewechat] 发送文本消息给 {}: {}".format(receiver, reply_text))
        elif reply.type == ReplyType.VOICE:  # 语音

            voice_url = reply.content
            logger.info(f"[gewechat] 发送语音 url={voice_url}, 接收人={receiver}")
            # self.client.post_voice(self.app_id, receiver, voice_url,2000)
            self.send_voice(receiver, reply.content)
        elif reply.type == ReplyType.IMAGE_URL:  # 图片地址
            img_url = reply.content
            logger.info(f"[gewechat] 发送图片 url={img_url}, 接收人={receiver}")
            self.client.post_image(self.app_id, receiver, img_url)
        elif reply.type == ReplyType.IMAGE:  # 图片
            image_storage = reply.content
            sz = fsize(image_storage)
            if sz >= 10 * 1024 * 1024:
                logger.info("[gewechat] 图片过大，准备压缩，sz={}".format(sz))
                image_storage = compress_imgfile(image_storage, 10 * 1024 * 1024 - 1)
                logger.info("[gewechat] 图片压缩完成，sz={}".format(fsize(image_storage)))
            image_storage.seek(0)
            self.client.post_image(self.app_id, receiver, image_storage.read())
            logger.info("[gewechat] 发送图片，接收者={}".format(receiver))
        elif reply.type == ReplyType.VIDEO_URL:  # 视频
            logger.info(f"[gewechat] 发送视频{reply.content}，接收者={receiver}")
            self.send_video(receiver, reply.content)


class Query:
    def GET(self):
        params = web.input(file="")
        if params.file:
            if os.path.exists(params.file):
                with open(params.file, 'rb') as f:
                    return f.read()
            else:
                raise web.notfound()
        return "gewechat callback server is running"

    def POST(self):
        channel = GeWeChatChannel()
        data = json.loads(web.data())
        logger.debug("[gewechat] 接收到数据: {}".format(data))
        if '回调地址链接成功' in str(data):
            logger.debug(f"[gewechat] POST 回调地址链接成功 :{str(data)}")
            return
        elif "'TypeName': 'FinderMsg'" in str(data):
            logger.debug(f"[gewechat] POST FinderMsg :{str(data)}")
            return

        gewechat_msg = GeWeChatMessage(data, channel.client)

        context = channel._compose_context(
            gewechat_msg.ctype,
            gewechat_msg.content,
            isgroup=gewechat_msg.is_group,
            msg=gewechat_msg,
        )
        if context:
            channel.produce(context)
        return "success"
