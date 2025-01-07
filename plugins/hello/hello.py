# encoding:utf-8

import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
from plugins import *
from config import conf


@plugins.register(
    name="Hello",
    desire_priority=-1,
    hidden=True,
    desc="A simple plugin that says hello",
    version="0.1",
    author="lanvent",
)
class Hello(Plugin):

    def __init__(self):
        super().__init__()
        try:
            self.config = super().load_config()
            if not self.config:
                logger.info("[Hello] 读取其他配置")
                self.config = self._load_config_template()
            self.group_welc_fixed_msg = self.config.get("group_welc_fixed_msg", {})
            self.group_welc_prompt = self.config.get("group_welc_prompt")
            self.group_exit_prompt = self.config.get("group_exit_prompt")
            self.patpat_prompt = self.config.get("patpat_prompt")
            logger.info("[Hello] 初始化成功")
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        except Exception as e:
            logger.error(f"[Hello]初始化异常：{e}")
            raise "[Hello] 初始化失败, 忽略 "

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT,
            ContextType.JOIN_GROUP,
            ContextType.PATPAT,
            ContextType.EXIT_GROUP
        ]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
        group_name = msg.from_user_nickname

        # 处理加入群组事件
        if e_context["context"].type == ContextType.JOIN_GROUP:
            # 检查是否有群组欢迎消息配置
            if "group_welcome_msg" in conf() or group_name in self.group_welc_fixed_msg:
                reply = Reply()
                reply.type = ReplyType.TEXT
                # 根据是否有为特定群组设置欢迎消息来决定回复内容
                if group_name in self.group_welc_fixed_msg:
                    reply.content = self.group_welc_fixed_msg.get(group_name, "").format(nickname=msg.actual_user_nickname)
                else:
                    reply.content = conf().get("group_welcome_msg", "").format(nickname=msg.actual_user_nickname)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                return

            # 使用欢迎语，交给默认ai处理
            if conf().get("group_welc_prompt"):
                e_context["context"].type = ContextType.TEXT
                e_context["context"].content = self.group_welc_prompt.format(nickname=msg.actual_user_nickname)
                e_context.action = EventAction.BREAK

                # 如果没有配置欢迎消息，则改为发送提示消息
                if not self.config or not self.config.get("use_character_desc"):
                    e_context["context"]["generate_breaked_by"] = EventAction.BREAK
                return
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理退出群组事件
        if e_context["context"].type == ContextType.EXIT_GROUP:
            # 如果有配置退出群组时的消息，则发送
            if conf().get("group_chat_exit_group"):
                e_context["context"].type = ContextType.TEXT
                e_context["context"].content = self.group_exit_prompt.format(nickname=msg.actual_user_nickname)
                e_context.action = EventAction.BREAK  # 事件结束，进入默认处理逻辑
                return
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理拍了拍事件
        if e_context["context"].type == ContextType.PATPAT:
            if conf().get('patpat_prompt'):
                e_context["context"].type = ContextType.TEXT
                e_context["context"].content = self.patpat_prompt
                e_context.action = EventAction.BREAK  # 事件结束，进入默认处理逻辑
                if not self.config or not self.config.get("use_character_desc"):
                    e_context["context"]["generate_breaked_by"] = EventAction.BREAK
                return
            e_context.action = EventAction.BREAK_PASS
            return

        # 处理文本消息
        content = e_context["context"].content
        logger.debug("[Hello] on_handle_context. content: %s" % content)
        # 对特定内容（"Hello"）的回复
        if content == "Hello":
            reply = Reply()
            reply.type = ReplyType.TEXT
            if e_context["context"]["isgroup"]:
                reply.content = f"Hello, {msg.actual_user_nickname} from {msg.from_user_nickname}"
            else:
                reply.content = f"Hello, {msg.from_user_nickname}"
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑

        # 对"Hi"的回复
        if content == "Hi":
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = "Hi"
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK  # 事件结束，进入默认处理逻辑，一般会覆写reply

        # 对"End"的特殊处理，将其转换为图片创建请求
        if content == "End":
            # 如果是文本消息"End"，将请求转换成"IMAGE_CREATE"，并将content设置为"The World"
            e_context["context"].type = ContextType.IMAGE_CREATE
            content = "The World"
            e_context.action = EventAction.CONTINUE  # 事件继续，交付给下个插件或默认逻辑

    def get_help_text(self, **kwargs):
        help_text = "输入Hello，我会回复你的名字\n输入End，我会回复你世界的图片\n"
        return help_text

    def _load_config_template(self):
        logger.debug("No Hello plugin config.json, use plugins/hello/config.json.template")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
        except Exception as e:
            logger.exception(e)
