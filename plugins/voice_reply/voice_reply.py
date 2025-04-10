# encoding:utf-8
import threading
import requests
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel import channel_factory
from channel.gewechat.gewechat_channel import GeWeChatChannel
from channel.wechat.wechat_channel import WechatChannel
import plugins
from plugins import *
from common.log import logger
from typing import List, Any
import time
from concurrent.futures import ThreadPoolExecutor
from common.tmp_dir import TmpDir
from plugins.my.src_search import SrcSearch
from plugins.my.quark_utils import Quark
from pydub import AudioSegment
import uuid
import wave
import struct
import os
import pilk  # 使用 pilk 库进行 SILK 编码
from config import conf, save_config,pconf

@plugins.register(
    name="voice_reply",
    desire_priority=6,
    hidden=True,
    desc="语音回复",
    version="1.0",
    author="lei",
)
class VoiceReply(Plugin):
    def __init__(self):
        super().__init__()
        try:
            self.config = super().load_config()
            if not self.config:
                logger.info("[voice_reply] 读取其他配置")
                self.config = self._load_self_config()

            # 初始化数据
            self.voice_model_now = self.config.get("voice_model_now", "陈泽")  # 默认使用第一个
            self.open_voice_reply = self.config.get("open_voice_reply", False)  # 默认不启动
            self.voice_models = self.config.get("voice_models", {})

            # self.get_voice_list()  # 获取语音包
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context

            logger.info("[voice_reply] 初始化成功")
        except Exception as e:
            logger.warn("[voice_reply] 初始化失败")
            raise e

    # 这个事件主要用于处理上下文信息。当用户发送消息时，系统会触发这个事件，以便根据上下文来决定如何响应用户的请求。它通常用于获取和管理对话的上下文状态。
    def on_handle_context(self, context: EventContext):
        if context["context"].type not in [
            ContextType.TEXT,
        ]:
            return

        # 获取消息
        msg_content = context["context"].content.strip()
        logger.info(f"[voice_reply] 当前监听信息： {msg_content}")
        logger.info(f"[voice_reply] 模型： {self.voice_model_now}")
        reply = Reply()
        reply.other = self.build_voice_content()
        if msg_content == '开启语音回复':
            self.open_voice_reply = True

            pconf("voice_reply")["open_voice_reply"] = True
            save_config()

            reply.type = ReplyType.TEXT
            reply.content = "语音回复已开启"
            context['reply'] = reply
            context.action = EventAction.BREAK_PASS
        elif msg_content == '关闭语音回复':
            self.open_voice_reply = False

            pconf("voice_reply")["open_voice_reply"] = False
            save_config()

            reply.type = ReplyType.TEXT
            reply.content = "语音回复已关闭"
            context['reply'] = reply
            context.action = EventAction.BREAK_PASS
        elif msg_content == '切换语音包':
            reply.type = ReplyType.TEXT
            # reply.content = self.get_voice_list()
            reply.content = "可切换语音包：\n" + "\n".join([f"{key}" for key, value in self.voice_models.items()])
            context['reply'] = reply
            context.action = EventAction.BREAK_PASS
        elif "切换语音包" in msg_content:
            reply_content = f"切换语音包不存在，请检查"
            index = msg_content.find("切换语音包")
            if index != -1:
                self.voice_model_now = msg_content[index + 5:].strip()
                # 有就切换
                if pconf("voice_reply").get("voice_models").get(self.voice_model_now):

                    pconf("voice_reply")["voice_model_now"] = self.voice_model_now
                    save_config()

                    logger.info(f"切换语音包：{self.voice_model_now}")
                    reply_content = f"切换[{self.voice_model_now}]语音包成功"


            reply.type = ReplyType.TEXT
            reply.content = reply_content
            context['reply'] = reply
            context.action = EventAction.BREAK_PASS
        # else:
        #     if self.open_voice_reply:
        #         reply = Reply()
        #         reply.type = ReplyType.TEXT
        #         reply.content = msg_content
        #         reply.other = self.build_voice_content()
        #         context['reply'] = reply
        #         # 事件结束，并跳过处理context的默认逻辑
        #         # context.action = EventAction.BREAK
        #         context.action = EventAction.BREAK_PASS

    def build_voice_content(self):
        voice_url = "http://192.168.8.181:9890"
        if self.voice_model_now == "1":
            voice_url = f"{voice_url}/?refer_wav_path=E:\GPT-SoVITS-v2-240821\GPT_SoVITS\pretrained_models\丁真 希望大家都可以行动起来，我从理塘来，大家，一首微笑的歌，希望大家能够喜欢，扎西德勒。.wav&prompt_text=希望大家可以行动起来，我从理塘来，大家，一首微笑的歌，希望大家可以喜欢，扎西德勒&prompt_language=中文&text_language=中文&top_k=15&top_p=1&temperature=1&speed=1"
        return voice_url

    def get_silk(self, msg_content):

        try:
            # 发起 GET 请求，下载文件
            response = requests.get(self.build_voice_content())
            response.raise_for_status()  # 检查请求是否成功
            fid = str(uuid.uuid4())
            # 创建临时文件保存下载的 .wav 文件
            temp_wav_name = f"wav_audio_{fid}.wav"
            temp_wav_path = TmpDir().path() + temp_wav_name
            with open(temp_wav_path, "wb") as f:
                f.write(response.content)

            # 将 .wav 文件转换为 .silk 格式
            self.convert_wav_to_silk(temp_wav_path)

            temp_silk_name = f"wav_audio_{fid}.silk"
            temp_silk_path = TmpDir().path() + temp_silk_name
            # 返回 .silk 文件的路径
            logger.info(f"返回 .silk 文件的路径: {temp_silk_path}")
            silk_path = f"{conf().get('gewechat_callback_url')}?file={temp_silk_path}"
            logger.info(f"返回 .silk gewechat_callback_url文件的路径: {silk_path}")
            return silk_path

        except Exception as e:
            print(f"Error converting file: {e}")
            raise

    def convert_wav_to_silk(self, wav_file_path, silk_file_path=None):
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

            print(f"Conversion completed: {silk_file_path} (Duration: {duration} seconds)")
            return silk_file_path

        except Exception as e:
            print(f"Error converting WAV to Silk: {str(e)}")
            return None

    # http通用请求接口
    def http_request_data(self, url, response_type=None, user_headers=None, user_params=None, verify_flag=None):
        """
            通用的HTTP请求函数
        """
        try:
            # 发起GET请求
            if verify_flag:
                response = requests.get(url, headers=user_headers, params=user_params, verify=False)
            else:
                response = requests.get(url, headers=user_headers, params=user_params)

            # 打印请求信息
            logger.debug(f"发送的HTTP请求:\nGET {response.url}\n{response.request.headers}\n{response.request.body}")

            # 检查响应状态码
            # 如果响应状态码不是200，将会抛出HTTPError异常
            response.raise_for_status()

            # 打印响应信息
            logger.debug(f"收到的HTTP响应:\n{response.status_code}\n{response.headers}")

            # 解析响应体
            if "raw" == response_type:
                # 直接返回二进制流
                response_data = response.content
            elif "text" == response_type:
                # 返回文本
                response_data = response.text
            else:
                # 默认按json处理
                response_data = response.json()

            return response_data
        except requests.exceptions.HTTPError as http_err:
            err_str = f"HTTP错误: {http_err}"
            logger.error(err_str)
            return err_str
        except ValueError as json_err:
            err_str = f"JSON解析错误: {json_err}"
            logger.error(err_str)
            return err_str
        except Exception as err:
            err_str = f"其他错误: {err}"
            logger.error(err_str)
            return err_str

    def get_help_text(self, **kwargs):
        return '''
            语音回复功能
            
            命令：
            【开启语音回复】：开启语音回复
            【关闭语音回复】：关闭语音回复
            【切换语音包】 ：显示可用语音包
            【切换语音包{No}】：使用语音包 例：切换语音包1
            
        '''

    # 加载当前文件下的配置文件
    def _load_self_config(self):
        try:
            plugin_config_path = os.path.join(self.path, "config.json")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
        except Exception as e:
            logger.exception(e)
