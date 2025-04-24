import os
import plugins
import requests
import re
import json
from urllib.parse import urlparse
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *
from datetime import datetime, timedelta

BASE_URL_ALAPI = "https://v2.alapi.cn/api/"

@plugins.register(
    name="Weather",
    desire_priority=88,
    hidden=False,
    desc="一个查询天气的插件",
    version="0.1",
    author="chatgpt",
)
class Weather(Plugin):
    def __init__(self):
        super().__init__()
        try:
            self.conf = super().load_config()
            self.condition_2_and_3_cities = None  # 天气查询，存储重复城市信息
            if not self.conf:
                logger.warn("[Weather] 已初始化，但在配置中找不到alapi_token")
                self.alapi_token = None
            else:
                logger.info("[Weather] 已初始化，成功加载alapi_token")
                self.alapi_token = self.conf["alapi_token"]
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        except Exception as e:
            logger.error(f"[Weather] init failed: {e}")
            raise Exception(f"[Weather] init failed, ignore: {e}")

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return
        content = e_context["context"].content.strip()
        logger.debug("[Weather] on_handle_context. content: %s" % content)

        # 天气查询
        weather_match = re.match(r'^(?:(.{2,7}?)(?:市|县|区|镇)?|(\d{7,9}))(:?今天|明天|后天|7天|七天)?(?:的)?天气$', content)
        if weather_match:
            # 如果匹配成功，提取城市或ID和日期
            city_or_id = weather_match.group(1) or weather_match.group(2)
            date = weather_match.group(3)
            
            if not self.alapi_token:
                reply = self.create_reply(ReplyType.TEXT, "请先配置alapi的token")
            else:
                weather_info = self.get_weather(self.alapi_token, city_or_id, date, content)
                reply = self.create_reply(ReplyType.TEXT, weather_info)
                
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

    def get_help_text(self, verbose=False, **kwargs):
        short_help_text = "发送城市名+天气，如'北京天气'、'广州今天天气'、'上海明天天气'、'深圳后天天气'、'成都七天天气'来查询天气。"

        if not verbose:
            return short_help_text

        help_text = "🌦️ 天气查询插件使用指南\n\n"
        help_text += "📝 使用方法：\n"
        help_text += "  1. 发送'城市名+天气'，如'北京天气'、'广州天气'\n"
        help_text += "  2. 指定时间：'城市名+今天/明天/后天/七天+天气'，如'上海今天天气'、'深圳明天天气'、'成都七天天气'\n"
        help_text += "  3. 对于有重名的城市，可以使用城市ID查询，如'1234567天气'\n\n"
        help_text += "⚠️ 注意：需要配置alapi的token才能使用该插件"

        return help_text

    def get_weather(self, alapi_token, city_or_id: str, date: str, content):
        url = BASE_URL_ALAPI + 'tianqi'
        isFuture = date in ['明天', '后天', '七天', '7天']
        if isFuture:
            url = BASE_URL_ALAPI + 'tianqi/seven'
        # 判断使用id还是city请求api
        if city_or_id.isnumeric():  # 判断是否为纯数字，也即是否为 city_id
            params = {
                'city_id': city_or_id,
                'token': f'{alapi_token}'
            }
        else:
            city_info = self.check_multiple_city_ids(city_or_id)
            if city_info:
                data = city_info['data']
                formatted_city_info = "\n".join(
                    [f"{idx + 1}) {entry['province']}--{entry['leader']}, ID: {entry['city_id']}"
                     for idx, entry in enumerate(data)]
                )
                return f"查询 <{city_or_id}> 具有多条数据：\n{formatted_city_info}\n请使用id查询，发送“id天气”"

            params = {
                'city': city_or_id,
                'token': f'{alapi_token}'
            }
        try:
            weather_data = self.make_request(url, "GET", params=params)
            if isinstance(weather_data, dict) and weather_data.get('code') == 200:
                data = weather_data['data']
                if isFuture:
                    formatted_output = []
                    for num, d in enumerate(data):
                        if num == 0:
                            formatted_output.append(f"🏙️ 城市: {d['city']} ({d['province']})\n")
                        if date == '明天' and num != 1:
                            continue
                        if date == '后天' and num != 2:
                            continue
                        basic_info = [
                            f"🕒 日期: {d['date']}",
                            f"🌦️ 天气: 🌞{d['wea_day']}| 🌛{d['wea_night']}",
                            f"🌡️ 温度: 🌞{d['temp_day']}℃| 🌛{d['temp_night']}℃",
                            f"🌅 日出/日落: {d['sunrise']} / {d['sunset']}",
                        ]
                        for i in d['index']:
                            basic_info.append(f"{i['name']}: {i['level']}")
                        formatted_output.append("\n".join(basic_info) + '\n')
                    return "\n".join(formatted_output)
                update_time = data['update_time']
                dt_object = datetime.strptime(update_time, "%Y-%m-%d %H:%M:%S")
                formatted_update_time = dt_object.strftime("%m-%d %H:%M")
                # Basic Info
                if not city_or_id.isnumeric() and data['city'] not in content:  # 如果返回城市信息不是所查询的城市，重新输入
                    return "输入不规范，请输<国内城市+(今天|明天|后天|七天|7天)+天气>，比如 '广州天气'"
                formatted_output = []
                basic_info = (
                    f"🏙️ 城市: {data['city']} ({data['province']})\n"
                    f"🕒 更新: {formatted_update_time}\n"
                    f"🌦️ 天气: {data['weather']}\n"
                    f"🌡️ 温度: ↓{data['min_temp']}℃| 现{data['temp']}℃| ↑{data['max_temp']}℃\n"
                    f"🌬️ 风向: {data['wind']}\n"
                    f"💦 湿度: {data['humidity']}\n"
                    f"🌅 日出/日落: {data['sunrise']} / {data['sunset']}\n"
                )
                formatted_output.append(basic_info)

                # Clothing Index,处理部分县区穿衣指数返回null
                chuangyi_data = data.get('index', {})[0].get('chuangyi', {})
                if chuangyi_data:
                    chuangyi_level = chuangyi_data.get('level', '未知')
                    chuangyi_content = chuangyi_data.get('content', '未知')
                else:
                    chuangyi_level = '未知'
                    chuangyi_content = '未知'

                chuangyi_info = f"👚 穿衣指数: {chuangyi_level} - {chuangyi_content}\n"
                formatted_output.append(chuangyi_info)
                # Next 7 hours weather
                ten_hours_later = dt_object + timedelta(hours=10)

                future_weather = []
                for hour_data in data['hour']:
                    forecast_time_str = hour_data['time']
                    forecast_time = datetime.strptime(forecast_time_str, "%Y-%m-%d %H:%M:%S")

                    if dt_object < forecast_time <= ten_hours_later:
                        future_weather.append(f"     {forecast_time.hour:02d}:00 - {hour_data['wea']} - {hour_data['temp']}°C")

                future_weather_info = "⏳ 未来10小时的天气预报:\n" + "\n".join(future_weather)
                formatted_output.append(future_weather_info)

                # Alarm Info
                if data.get('alarm'):
                    alarm_info = "⚠️ 预警信息:\n"
                    for alarm in data['alarm']:
                        alarm_info += (
                            f"🔴 标题: {alarm['title']}\n"
                            f"🟠 等级: {alarm['level']}\n"
                            f"🟡 类型: {alarm['type']}\n"
                            f"🟢 提示: \n{alarm['tips']}\n"
                            f"🔵 内容: \n{alarm['content']}\n\n"
                        )
                    formatted_output.append(alarm_info)

                return "\n".join(formatted_output)
            else:
                return self.handle_error(weather_data, "获取失败，请查看服务器log")

        except Exception as e:
            return self.handle_error(e, "获取天气信息失败")

    def make_request(self, url, method="GET", headers=None, params=None, data=None, json_data=None):
        try:
            if method.upper() == "GET":
                response = requests.request(method, url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = requests.request(method, url, headers=headers, data=data, json=json_data)
            else:
                return {"success": False, "message": "Unsupported HTTP method"}

            return response.json()
        except Exception as e:
            return e

    def create_reply(self, reply_type, content):
        reply = Reply()
        reply.type = reply_type
        reply.content = content
        return reply

    def handle_error(self, error, message):
        logger.error(f"{message}，错误信息：{error}")
        return message

    def load_city_conditions(self):
        if self.condition_2_and_3_cities is None:
            try:
                json_file_path = os.path.join(os.path.dirname(__file__), 'duplicate-citys.json')
                if os.path.exists(json_file_path):
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        self.condition_2_and_3_cities = json.load(f)
                else:
                    # 如果文件不存在，使用复制的Apilot文件
                    apilot_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Apilot', 'duplicate-citys.json')
                    if os.path.exists(apilot_path):
                        with open(apilot_path, 'r', encoding='utf-8') as f:
                            self.condition_2_and_3_cities = json.load(f)
                            # 保存到本地
                            with open(json_file_path, 'w', encoding='utf-8') as f2:
                                json.dump(self.condition_2_and_3_cities, f2, ensure_ascii=False, indent=4)
            except Exception as e:
                return self.handle_error(e, "加载城市数据失败")

    def check_multiple_city_ids(self, city):
        self.load_city_conditions()
        if self.condition_2_and_3_cities:
            city_info = self.condition_2_and_3_cities.get(city, None)
            if city_info:
                return city_info
        return None 