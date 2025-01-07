import os
import json
import web
from urllib.parse import urlparse

from bridge.context import Context
from bridge.reply import Reply, ReplyType
from channel.chat_channel import ChatChannel
from channel.gewechat.gewechat_message import GeWeChatMessage
from common.log import logger
from common.singleton import singleton
from common.tmp_dir import TmpDir
from common.utils import compress_imgfile, fsize
from config import conf, save_config
from lib.gewechat import GewechatClient

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

    def send(self, reply: Reply, context: Context):
        receiver = context["receiver"]
        gewechat_message = context.get("msg")
        if reply.type in [ReplyType.TEXT, ReplyType.ERROR, ReplyType.INFO]:
            reply_text = reply.content
            ats = ""
            if gewechat_message and gewechat_message.is_group:
                ats = gewechat_message.actual_user_id
            self.client.post_text(self.app_id, receiver, reply_text, ats)
            logger.info("[gewechat] 正在发送文本消息给 {}: {}".format(receiver, reply_text))
        elif reply.type == ReplyType.VOICE:
            try:
                # TODO: mp3 to silk
                content = reply.content
            except Exception as e:
                logger.error(f"[gewechat] 发送语音消息失败: {e}")
        elif reply.type == ReplyType.IMAGE_URL:
            img_url = reply.content
            self.client.post_image(self.app_id, receiver, img_url)
            logger.info("[gewechat] sendImage url={}, receiver={}".format(img_url, receiver))
        elif reply.type == ReplyType.IMAGE:
            image_storage = reply.content
            sz = fsize(image_storage)
            if sz >= 10 * 1024 * 1024:
                logger.info("[gewechat] 图片过大，准备压缩，sz={}".format(sz))
                image_storage = compress_imgfile(image_storage, 10 * 1024 * 1024 - 1)
                logger.info("[gewechat] 图片压缩完成，sz={}".format(fsize(image_storage)))
            image_storage.seek(0)
            self.client.post_image(self.app_id, receiver, image_storage.read())
            logger.info("[gewechat] 发送图片，接收者={}".format(receiver))

class Query:
    def GET(self):
        params = web.input(file="")
        if params.file:
            if os.path.exists(params.file):
                with open(params.file, 'rb', encoding="utf-8") as f:
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
