import os
import time
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

from bridge.context import Context, ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_channel import ChatChannel
from channel.gewechat.gewechat_message import GeWeChatMessage
from common.log import logger
from common.singleton import singleton
from common.tmp_dir import TmpDir
from config import conf, save_config
from common.utils import compress_imgfile, fsize
from config import conf, save_config, pconf
from lib.gewechat import GewechatClient
from voice.audio_convert import mp3_to_silk
import uuid
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
        # 如果没有指定端口，使用默认端口80
        port = parsed_url.port or 80
        logger.info(f"[gewechat] start callback server: {callback_url}")
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
        if reply.type in [ReplyType.TEXT, ReplyType.ERROR, ReplyType.INFO]:
            reply_text = reply.content
            ats = ""
            if gewechat_message and gewechat_message.is_group:
                ats = gewechat_message.actual_user_id
            self.client.post_text(self.app_id, receiver, reply_text, ats)
            logger.info("[gewechat] Do send text to {}: {}".format(receiver, reply_text))
        elif reply.type == ReplyType.VOICE:
            try:
                content = reply.content
                if content.endswith('.mp3'):
                    # 如果是mp3文件，转换为silk格式
                    silk_path = content + '.silk'
                    duration = mp3_to_silk(content, silk_path)
                    callback_url = conf().get("gewechat_callback_url")
                    silk_url = callback_url + "?file=" + silk_path
                    self.client.post_voice(self.app_id, receiver, silk_url, duration)
                    logger.info(f"[gewechat] Do send voice to {receiver}: {silk_url}, duration: {duration/1000.0} seconds")
                    return
                else:
                    logger.error(f"[gewechat] voice file is not mp3, path: {content}, only support mp3")
            except Exception as e:
                logger.error(f"[gewechat] send voice failed: {e}")
        elif reply.type == ReplyType.IMAGE_URL or reply.type == ReplyType.IMAGE:
            image_storage = reply.content
            if reply.type == ReplyType.IMAGE_URL:
                import requests
                import io
                img_url = reply.content
                logger.debug(f"[gewechat]sendImage, download image start, img_url={img_url}")
                pic_res = requests.get(img_url, stream=True)
                image_storage = io.BytesIO()
                size = 0
                for block in pic_res.iter_content(1024):
                    size += len(block)
                    image_storage.write(block)
                logger.debug(f"[gewechat]sendImage, download image success, size={size}, img_url={img_url}")
                image_storage.seek(0)
                if ".webp" in img_url:
                    try:
                        from common.utils import convert_webp_to_png
                        image_storage = convert_webp_to_png(image_storage)
                    except Exception as e:
                        logger.error(f"[gewechat]sendImage, failed to convert image: {e}")
                        return
            # Save image to tmp directory
            image_storage.seek(0)
            header = image_storage.read(6)
            image_storage.seek(0)
            img_data = image_storage.read()
            image_storage.seek(0)
            extension = ".gif" if header.startswith((b'GIF87a', b'GIF89a')) else ".png"
            img_file_name = f"img_{str(uuid.uuid4())}{extension}"
            img_file_path = TmpDir().path() + img_file_name
            with open(img_file_path, "wb") as f:
                f.write(img_data)
            # Construct callback URL
            callback_url = conf().get("gewechat_callback_url")
            img_url = callback_url + "?file=" + img_file_path
            if extension == ".gif":
                result = self.client.post_file(self.app_id, receiver, file_url=img_url, file_name=img_file_name)
                logger.info("[gewechat] sendGifAsFile, receiver={}, file_url={}, file_name={}, result={}".format(
                    receiver, img_url, img_file_name, result))
            else:
                result = self.client.post_image(self.app_id, receiver, img_url)
                logger.info("[gewechat] sendImage, receiver={}, url={}, result={}".format(receiver, img_url, result))
            if result.get('ret') == 200:
                newMsgId = result['data'].get('newMsgId')
                new_img_file_path = TmpDir().path() + str(newMsgId) + extension
                os.rename(img_file_path, new_img_file_path)
                logger.info("[gewechat] sendImage rename to {}".format(new_img_file_path))

class Query:
    def GET(self):
        # 搭建简单的文件服务器，用于向gewechat服务传输语音等文件，但只允许访问tmp目录下的文件
        params = web.input(file="")
        file_path = params.file
        if file_path:
            # 使用os.path.abspath清理路径
            clean_path = os.path.abspath(file_path)
            # 获取tmp目录的绝对路径
            tmp_dir = os.path.abspath("tmp")
            # 检查文件路径是否在tmp目录下
            if not clean_path.startswith(tmp_dir):
                logger.error(f"[gewechat] Forbidden access to file outside tmp directory: file_path={file_path}, clean_path={clean_path}, tmp_dir={tmp_dir}")
                raise web.forbidden()

            if os.path.exists(clean_path):
                with open(clean_path, 'rb') as f:
                    return f.read()
            else:
                logger.error(f"[gewechat] File not found: {clean_path}")
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


        # 微信客户端的状态同步消息
        if gewechat_msg.ctype == ContextType.STATUS_SYNC:
            logger.debug(f"[gewechat] ignore status sync message: {gewechat_msg.content}")
            return "success"

        # 忽略非用户消息（如公众号、系统通知等）
        if gewechat_msg.ctype == ContextType.NON_USER_MSG:
            logger.debug(f"[gewechat] ignore non-user message from {gewechat_msg.from_user_id}: {gewechat_msg.content}")
            return "success"

        # 判断是否需要忽略语音消息
        if gewechat_msg.ctype == ContextType.VOICE:
            if conf().get("speech_recognition") != True:
                return "success"

        # 忽略来自自己的消息
        if gewechat_msg.my_msg:
            logger.debug(f"[gewechat] ignore message from myself: {gewechat_msg.actual_user_id}: {gewechat_msg.content}")
            return "success"

        # 忽略过期的消息
        if int(gewechat_msg.create_time) < int(time.time()) - 60 * 5: # 跳过5分钟前的历史消息
            logger.debug(f"[gewechat] ignore expired message from {gewechat_msg.actual_user_id}: {gewechat_msg.content}")
            return "success"

        context = channel._compose_context(
            gewechat_msg.ctype,
            gewechat_msg.content,
            isgroup=gewechat_msg.is_group,
            msg=gewechat_msg,
        )
        if context:
            channel.produce(context)
        return "success"
