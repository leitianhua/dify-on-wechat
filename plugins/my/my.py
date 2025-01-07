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

from plugins.my.quark_src import QURAK
from plugins.my.quark_utils import Quark


@plugins.register(
    name="My",
    desire_priority=100,
    hidden=True,
    desc="自定义插件功能",
    version="1.0",
    author="lei",
)
class My(Plugin):
    def __init__(self):
        super().__init__()
        try:
            self.conf = super().load_config()
            if not conf:
                logger.info("[my] 读取其他配置")
                self.config = self._load_self_config()
            self.src_url = self.conf.get("src_url", "ks.jizhi.me")
            self.cookie = self.conf.get("cookie")
            self.save_dir = self.conf.get("save_dir")
            self.ad_keywords = self.conf.get("ad_keywords", [])
            # logger.info(f'''
            #     [my]当前配置 conf： {self.conf}
            #     [my]当前配置 src_url： {self.conf.get("src_url")}
            #     [my]当前配置 cookie： {self.conf.get("cookie")}
            #     [my]当前配置 save_dir： {self.conf.get("save_dir")}
            #     [my]当前配置 ad_keywords： {self.conf.get("ad_keywords")}
            # ''')

            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            logger.info("[My] 初始化成功")
        except Exception as e:
            logger.warn("[My] 初始化失败")
            raise e

    # 这个事件主要用于处理上下文信息。当用户发送消息时，系统会触发这个事件，以便根据上下文来决定如何响应用户的请求。它通常用于获取和管理对话的上下文状态。
    def on_handle_context(self, context: EventContext):
        if context["context"].type not in [
            ContextType.TEXT,
        ]:
            return

        # 发送文本
        def wx_send(reply_content):
            channel_factory.create_channel(conf().get("channel_type", "wx")).send(Reply(ReplyType.TEXT, reply_content), context["context"])

        # 获取消息
        msg_content = context["context"].content.strip()
        logger.info(f"[my]当前监听信息： {msg_content}")
        logger.info(f'[my]当前配置 conf： {conf()}')

        # "搜剧", "搜", "全网搜"
        if any(msg_content.startswith(prefix) for prefix in ["搜剧", "搜", "全网搜"]) and not msg_content.startswith("搜索"):
            # 获取用户名
            user_nickname = str(context["context"]["msg"].actual_user_nickname)
            at_name = ('@' + user_nickname) if not user_nickname else ''

            # 移除前缀
            def remove_prefix(content, prefixes):
                for prefix in prefixes:
                    if content.startswith(prefix):
                        return content[len(prefix):].strip()
                return content.strip()

            # 搜索内容
            search_content = remove_prefix(msg_content, ["搜剧", "搜", "全网搜"]).strip()

            # http 搜索资源
            def to_search(title):
                url = f'https://{self.conf.get("src_url")}/api/search'
                params = {
                    'is_time': '1',
                    'page_no': '1',
                    'page_size': '5',
                    'title': title
                }
                try:
                    response = requests.get(url, params=params)
                    response.raise_for_status()  # 检查请求是否成功
                    response_data = response.json().get('data', {}).get('items', [])
                    return response_data
                except requests.exceptions.RequestException as e:
                    print(f"Error fetching data: {e}")
                    return []

            # http 全网搜
            def to_search_all(title):
                url = f'https://{self.conf.get("src_url")}/api/other/all_search'
                payload = {
                    'title': title
                }
                try:
                    response = requests.post(url, json=payload)
                    response.raise_for_status()
                    response_data = response.json().get('data', [])
                    return response_data
                except requests.exceptions.RequestException as e:
                    print(f"Error fetching data: {e}")
                    return []

            # http 全网搜 自定义
            def to_search_all_1(title):
                def fetch_data(method_name: str, qry_key: str) -> Any:
                    quark = QURAK()
                    method = getattr(quark, method_name, None)
                    if method is not None:
                        return method(qry_key)
                    return None

                logger.info('查询关键字:' + title)
                start_time = time.time()

                with ThreadPoolExecutor() as executor:
                    futures = [
                        executor.submit(fetch_data, method_name, title)
                        for method_name in [
                            'qry_kkkob',
                            'get_qry_external',
                            'get_qry_external_2',
                            'get_qry_external_3',
                            'get_qry_external_4',
                            'get_qry_external_5'
                        ]
                    ]

                # 创建一个新的列表来存储去重后的数据
                unique_data = []
                # 转存
                quark = Quark(self.conf)
                i = 1
                # 遍历合并后的数据，按链接去重
                for future in futures:
                    future_data = future.result()
                    if future_data is not None:
                        for item in future_data:
                            if i > 5:
                                break

                            # 转存
                            url = item['url']
                            try:
                                file_not_exist, file_name, share_link = quark.store(url)
                            except Exception as e:
                                print(f'转存-失败【error】：{item["title"]}   {url}：{e}')
                                import traceback
                                traceback.print_exc()
                                continue
                            if file_not_exist:
                                print(f'转存-名称【New】：{file_name}   {share_link}')
                                i += 1
                            else:
                                print(f'转存-名称【已存在】：{file_name}   {share_link}')

                            item['url'] = share_link
                            unique_data.append(item)

                end_time = time.time()
                execution_time = end_time - start_time
                logger.info(f"查询执行耗时: {execution_time:.6f} seconds")
                logger.info(f"查询结果: {unique_data}")
                return unique_data

            # 回复内容
            def send_build(response_data):
                if not response_data:
                    reply_text_final = f"{at_name}搜索内容：{search_content}"
                    reply_text_final += "\n呜呜，还没找到呢~😔"
                    reply_text_final += "\n⚠关键词错误或存在错别字"
                    reply_text_final += "\n————————————"
                    reply_text_final += "\n⚠搜索指令：搜:XXX"
                    reply_text_final += f"\n其他资源指令：全网搜:XX"
                else:
                    reply_text_final = f"{at_name} 搜索内容：{search_content}\n————————————"
                    logger.info(str(response_data))
                    for item in response_data:
                        reply_text_final += f"\n🌐️{item.get('title', '未知标题')}"
                        reply_text_final += f"\n{item.get('url', '未知URL')}"
                        reply_text_final += "\n————————————"
                    if "'is_time': 1" in str(response_data):
                        reply_text_final += "\n⚠资源来源网络，30分钟后删除"
                        reply_text_final += "\n⚠避免失效，请及时保存~💾"
                        reply_text_final += "\n————————————"
                    else:
                        reply_text_final += "\n🎬不是想要的？试试这招：全网搜XX！🔍"
                        reply_text_final += "\n————————————"

                    reply_text_final += "\n👯‍♂️加我或者拉我到群里，就能免费享用啦~🥰"
                wx_send(reply_text_final)

            # 执行搜索
            def perform_search():
                response_data = to_search(search_content) if not msg_content.startswith("全网搜") else []
                if not response_data:
                    # 通知用户深入搜索
                    wx_send(f"{at_name} 🔍正在努力翻找中，请稍等一下下哦~🐾✨")

                    # 启动线程进行第二次搜索
                    # threading.Thread(target=send_build(to_search_all(search_content))).start()
                    threading.Thread(target=send_build(to_search_all_1(search_content))).start()
                else:
                    # 如果第一次搜索找到结果，发送最终回复
                    send_build(response_data)

            # 启动线程执行第一次搜索
            threading.Thread(target=perform_search()).start()

            context["reply"] = None
            context.action = EventAction.BREAK_PASS
            return

    def get_help_text(self, **kwargs):
        return "自定义功能"

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
