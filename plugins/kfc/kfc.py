import os
import json
import plugins
import requests
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *

@plugins.register(
    name="KFC",
    desire_priority=88,
    hidden=False,
    desc="疯狂星期四文案生成插件",
    version="0.1",
    author="chatgpt",
)
class KFC(Plugin):
    def __init__(self):
        super().__init__()
        try:
            self.conf = super().load_config()
            if not self.conf:
                logger.warn("[KFC] 配置文件不存在，使用默认配置")
                self.kfc_keyword = ["肯德基", "kfc", "KFC", "疯狂星期四"]
            else:
                logger.info("[KFC] 配置文件加载成功")
                self.kfc_keyword = self.conf.get("kfc_keyword", ["肯德基", "kfc", "KFC", "疯狂星期四"])
            
            # 疯狂星期四文案API
            self.KFC_URL = "https://api.pearktrue.cn/api/kfc"
            
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        except Exception as e:
            logger.error(f"[KFC] 初始化失败: {e}")
            raise Exception(f"[KFC] 初始化失败: {e}")

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return
        content = e_context["context"].content.strip()
        logger.debug("[KFC] on_handle_context. content: %s" % content)

        # 检查是否为疯狂星期四关键词
        if self.kfc_check_keyword(content):
            logger.debug("[KFC] 检测到疯狂星期四关键词")
            reply = Reply()
            # 获取疯狂星期四文案
            reply.type = ReplyType.TEXT
            reply.content = self.kfc_request(self.KFC_URL)
            e_context['reply'] = reply
            # 事件结束，并跳过处理context的默认逻辑
            e_context.action = EventAction.BREAK_PASS
            return

    def get_help_text(self, verbose=False, **kwargs):
        short_help_text = "发送 KFC、肯德基、疯狂星期四 等关键词获取随机疯狂星期四文案"

        if not verbose:
            return short_help_text

        help_text = "🍗 疯狂星期四插件使用指南\n\n"
        help_text += "📝 使用方法：\n"
        help_text += "  发送以下任一关键词即可获取随机疯狂星期四文案：\n"
        for keyword in self.kfc_keyword:
            help_text += f"  - {keyword}\n"
        help_text += "\n🎁 功能特点：\n"
        help_text += "  - 随机生成疯狂星期四文案\n"
        help_text += "  - 可自定义触发关键词\n"

        return help_text

    def kfc_check_keyword(self, content):
        """
        检查疯狂星期四文案关键字
        """
        # 检查关键词
        return any(keyword in content for keyword in self.kfc_keyword)

    def kfc_request(self, url):
        """
        疯狂星期四文案请求函数
        """
        try:
            # http请求
            response_data = self.http_request_data(url)

            # 返回疯狂星期四文案
            if "text" in response_data:
                # 获取疯狂星期四文案
                kfc_text = response_data['text']
            logger.debug(f"[KFC] 获取到的文案: {kfc_text}")
            return kfc_text
        except Exception as err:
            err_str = f"获取疯狂星期四文案失败: {err}"
            logger.error(err_str)
            return err_str

    def http_request_data(self, url, response_type=None, user_headers=None, user_params=None, verify_flag=None):
        """
        HTTP请求数据函数
        """
        try:
            # 设置默认请求头
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            # 使用用户自定义请求头
            if user_headers:
                headers.update(user_headers)

            # 发起请求
            if verify_flag is None:
                response = requests.get(url, headers=headers, params=user_params)
            else:
                response = requests.get(url, headers=headers, params=user_params, verify=verify_flag)

            # 设置响应格式
            if response_type == "text":
                return response.text
            elif response_type == "content":
                return response.content
            else:
                return response.json()
        except Exception as e:
            logger.error(f"[KFC] HTTP请求失败: {e}")
            return e 