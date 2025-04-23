# encoding:utf-8

import json
import os
import re
import requests
import urllib.parse
import time
import uuid
from urllib.parse import quote
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
import plugins
from plugins import *
from config import conf


# 添加Session类用于保存对话历史
class PollinationsSession(object):
    def __init__(self, session_id):
        self.session_id = session_id
        self.messages = []  # 存储对话消息
        self.max_history = 10  # 默认保存最近10条消息
    
    def add_message(self, role, content):
        """添加一条消息到历史记录"""
        self.messages.append({"role": role, "content": content})
        # 如果消息数量超过最大限制，移除最早的消息
        if len(self.messages) > self.max_history:
            self.messages.pop(0)
    
    def get_history(self):
        """获取会话历史"""
        return self.messages
    
    def get_openai_messages(self, system_prompt=None, current_prompt=None):
        """获取符合OpenAI格式的消息历史"""
        messages = []
        
        # 添加系统提示
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # 添加历史消息
        for msg in self.messages:
            messages.append(msg)
        
        # 添加当前提示（如果有）
        if current_prompt:
            messages.append({"role": "user", "content": current_prompt})
            
        return messages
    
    def clear(self):
        """清空会话历史"""
        self.messages = []


# 添加SessionManager类用于管理所有会话
class PollinationsSessionManager(object):
    def __init__(self):
        self.sessions = {}  # 存储所有会话
    
    def get_session(self, session_id):
        """获取会话，如果不存在则创建新会话"""
        if session_id not in self.sessions:
            self.sessions[session_id] = PollinationsSession(session_id)
        return self.sessions[session_id]
    
    def clear_session(self, session_id):
        """清除指定会话的历史记录"""
        if session_id in self.sessions:
            self.sessions[session_id].clear()
    
    def clear_all_sessions(self):
        """清除所有会话的历史记录"""
        for session in self.sessions.values():
            session.clear()


@plugins.register(
    name="PollinationsChat",
    desire_priority=0,
    hidden=False,
    desc="一个集成Pollinations.AI的聊天插件，支持文本和语音回复",
    version="0.1",
    author="AI Assistant",
    namecn="Pollinations聊天"
)
class PollinationsChat(Plugin):
    def __init__(self):
        super().__init__()
        try:
            # 加载配置
            self.config = super().load_config()
            if not self.config:
                self.config = self._load_config_template()
                
            # 功能前缀配置
            self.chat_prefix = self.config.get("chat_prefix", ["p问", "p聊"])
            self.voice_toggle_prefix = self.config.get("voice_toggle_prefix", ["p语音开关"])
            self.voice_set_prefix = self.config.get("voice_set_prefix", ["p设置语音"])
            self.clear_memory_prefix = self.config.get("clear_memory_prefix", ["p清除记忆"])
            
            # 默认设置
            self.enable_voice = self.config.get("enable_voice", False)
            self.default_voice = self.config.get("default_voice", "alloy")
            self.enable_memory = self.config.get("enable_memory", True)
            self.max_history = self.config.get("max_history", 10)
            
            # API参数配置 - 只保留model和system参数
            self.api_params = self.config.get("api_params", {
                "model": "openai",
                "system": "你是个乐于助人的ai助手"
            })
            
            # 请求默认设置
            self.default_headers = {
                "Accept": "*/*",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
                "Referer": "https://pollinations.ai/"
            }
            
            # API基础URL - 使用OpenAI兼容接口
            self.openai_api_url = "https://text.pollinations.ai/openai"
            self.text_models_url = "https://text.pollinations.ai/models"
            
            # 可用的语音选项
            self.available_voices = [
                "alloy", "echo", "fable", "onyx", "nova", "shimmer"
            ]
            
            # 初始化会话管理器
            self.session_manager = PollinationsSessionManager()
            
            # 注册事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            
            logger.info("[Pollinations聊天] 插件初始化成功")
        except Exception as e:
            logger.error(f"[Pollinations聊天] 插件初始化失败: {e}")

    def on_handle_context(self, e_context: EventContext):
        """处理上下文事件"""
        if e_context["context"].type != ContextType.TEXT:
            return
            
        content = e_context["context"].content
        logger.debug(f"[Pollinations聊天] 收到消息: {content}")
        
        # 获取会话ID
        session_id = self._get_session_id(e_context["context"])
        
        # 检查是否是插件命令
        if self._is_command(content):
            reply = None
            
            # 处理清除记忆命令
            if self._check_prefix(content, self.clear_memory_prefix):
                logger.info("[Pollinations聊天] 处理清除记忆命令")
                reply = self._handle_clear_memory(content, session_id)
            
            # 当chat_prefix为空时，优先处理聊天功能
            elif not self.chat_prefix or self._check_prefix(content, self.chat_prefix):
                logger.info("[Pollinations聊天] 处理聊天命令")
                reply = self._handle_chat(content, session_id, e_context["context"])
            
            # 处理语音开关命令
            elif self._check_prefix(content, self.voice_toggle_prefix):
                logger.info("[Pollinations聊天] 处理语音开关命令")
                reply = self._handle_voice_toggle(content)
            
            # 处理设置语音命令
            elif self._check_prefix(content, self.voice_set_prefix):
                logger.info("[Pollinations聊天] 处理设置语音命令")
                reply = self._handle_voice_set(content)
                
            # 如果有回复，则设置并结束事件处理
            if reply:
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
    
    def _get_session_id(self, context):
        """获取会话ID，区分私聊和群聊"""
        if not context.get("session_id"):
            # 如果没有session_id，尝试从消息中获取
            if context.get("isgroup", False):
                # 群聊：使用群ID和发送者ID组合作为会话ID，除非是共享会话群
                if context.get("is_shared_session_group", False):
                    # 共享会话群，直接使用群ID
                    return f"group_{context['msg'].other_user_id}"
                else:
                    # 非共享会话群，使用发送者ID和群ID组合
                    return f"group_{context['msg'].actual_user_id}_{context['msg'].other_user_id}"
            else:
                # 私聊：使用发送者ID作为会话ID
                return f"private_{context['msg'].other_user_id}"
        return context.get("session_id")
    
    def _is_command(self, content):
        """检查消息是否是插件命令"""
        # 如果chat_prefix为空列表，则所有消息都认为是聊天命令
        if not self.chat_prefix:
            return True
            
        if content.startswith(tuple(self.chat_prefix)) or \
           content.startswith(tuple(self.voice_toggle_prefix)) or \
           content.startswith(tuple(self.voice_set_prefix)) or \
           content.startswith(tuple(self.clear_memory_prefix)):
            return True
        return False
    
    def _check_prefix(self, content, prefix_list):
        """检查消息是否以指定前缀开始"""
        # 如果是空前缀列表且是在检查chat_prefix，则返回空字符串作为前缀
        if not prefix_list and prefix_list is self.chat_prefix:
            return ""
            
        for prefix in prefix_list:
            if content.startswith(prefix):
                return prefix
        return None
    
    def _extract_prompt(self, content, prefix):
        """从消息中提取提示词"""
        prompt = content[len(prefix):].strip()
        return prompt
    
    def _call_text_api(self, prompt, session):
        """调用文本生成API"""
        # 构建消息历史
        messages = []
        
        # 添加系统提示
        if self.api_params.get("system"):
            messages.append({
                "role": "system",
                "content": self.api_params.get("system")
            })
        
        # 添加历史消息(如果启用了记忆功能)
        if self.enable_memory and session.messages:
            messages.extend(session.messages)
        else:
            # 如果没有启用记忆，或没有历史消息，直接添加当前提示
            messages.append({
                "role": "user",
                "content": prompt
            })
        
        # 如果启用了记忆但当前用户消息不在历史记录中，添加它
        if self.enable_memory and messages[-1]["role"] != "user" or messages[-1]["content"] != prompt:
            messages.append({
                "role": "user",
                "content": prompt
            })
        
        # 构建API请求数据
        payload = {
            "model": self.api_params.get("model", "openai"),
            "messages": messages,
            "private": True  # 默认为私有，防止显示在公共源
        }
        
        # 发送请求
        try:
            logger.debug(f"[Pollinations聊天] 发送文本请求: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(
                self.openai_api_url,
                headers=self.default_headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                response_data = response.json()
                logger.debug(f"[Pollinations聊天] 收到响应: {json.dumps(response_data, ensure_ascii=False)}")
                
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    message = response_data["choices"][0]["message"]
                    if "content" in message:
                        return message["content"]
            
            logger.error(f"[Pollinations聊天] API请求失败: 状态码={response.status_code}, 响应={response.text}")
            return f"API请求失败: {response.status_code}"
            
        except Exception as e:
            logger.error(f"[Pollinations聊天] API请求异常: {str(e)}")
            return f"API请求异常: {str(e)}"
    
    def _call_voice_api(self, prompt):
        """调用语音生成API"""
        # 构建API请求数据
        payload = {
            "model": "openai-audio",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "voice": self.default_voice,
            "private": True  # 默认为私有，防止显示在公共源
        }
        
        # 发送请求
        try:
            logger.debug(f"[Pollinations聊天] 发送语音请求: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(
                self.openai_api_url,
                headers=self.default_headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                # 保存语音文件
                import tempfile
                temp_dir = tempfile.gettempdir()
                filename = f"pollinations_voice_{int(time.time())}_{uuid.uuid4().hex[:8]}.mp3"
                filepath = os.path.join(temp_dir, filename)
                
                with open(filepath, "wb") as f:
                    f.write(response.content)
                
                return filepath
                
            logger.error(f"[Pollinations聊天] 语音API请求失败: 状态码={response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"[Pollinations聊天] 语音API请求异常: {str(e)}")
            return None
    
    def _handle_chat(self, content, session_id, context):
        """处理聊天命令"""
        prefix = self._check_prefix(content, self.chat_prefix)
        if prefix is None:
            return None
            
        # 提取问题
        prompt = self._extract_prompt(content, prefix)
        if not prompt and prefix != "":  # 空前缀情况下不需要检查prompt是否为空
            return None
        
        # 如果前缀为空字符串，使用整个内容作为prompt
        if prefix == "":
            prompt = content.strip()
        
        try:
            # 获取会话对象
            session = self.session_manager.get_session(session_id)
            session.max_history = self.max_history  # 设置最大历史记录数
            
            # 添加用户消息到会话历史
            if self.enable_memory:
                session.add_message("user", prompt)
            
            if self.enable_voice:
                # 调用语音API
                voice_path = self._call_voice_api(prompt)
                
                if voice_path:
                    # 创建音频回复
                    reply = Reply()
                    reply.type = ReplyType.VOICE
                    reply.content = voice_path
                    return reply
                else:
                    return self._create_text_reply("语音生成失败，尝试文本回复...")
            
            # 调用文本API
            response_text = self._call_text_api(prompt, session)
            
            # 添加AI回复到会话历史
            if self.enable_memory:
                session.add_message("assistant", response_text)
            
            # 检查是否需要在群聊中添加@
            if context.get("isgroup", False) and not context.get("is_shared_session_group", False):
                # 在群聊中，添加@用户的前缀
                user_nickname = context["msg"].actual_user_nickname
                response_text = f"@{user_nickname} {response_text}"
            
            return self._create_text_reply(response_text)
                
        except Exception as e:
            logger.error(f"[Pollinations聊天] 处理聊天命令失败: {e}")
            return self._create_text_reply(f"处理失败: {str(e)}")
    
    def _handle_voice_toggle(self, content):
        """处理语音开关命令"""
        prefix = self._check_prefix(content, self.voice_toggle_prefix)
        if not prefix:
            return None
            
        # 提取参数
        param = self._extract_prompt(content, prefix).strip().lower()
        
        if param in ["on", "开", "开启", "true", "1"]:
            self.enable_voice = True
            return self._create_text_reply(f"语音回复已开启，当前语音类型: {self.default_voice}")
        elif param in ["off", "关", "关闭", "false", "0"]:
            self.enable_voice = False
            return self._create_text_reply("语音回复已关闭，将使用文本回复")
        else:
            current_status = "开启" if self.enable_voice else "关闭"
            return self._create_text_reply(f"当前语音回复状态: {current_status}\n\n使用命令开启: p语音开关 开\n使用命令关闭: p语音开关 关")
    
    def _handle_voice_set(self, content):
        """处理设置语音命令"""
        prefix = self._check_prefix(content, self.voice_set_prefix)
        if not prefix:
            return None
            
        # 提取语音类型
        voice_type = self._extract_prompt(content, prefix).strip().lower()
        
        if not voice_type:
            available_voices = ", ".join(self.available_voices)
            return self._create_text_reply(f"当前语音类型: {self.default_voice}\n\n可用的语音类型: {available_voices}\n\n使用示例: p设置语音 nova")
        
        if voice_type in self.available_voices:
            self.default_voice = voice_type
            return self._create_text_reply(f"语音类型已设置为: {voice_type}")
        else:
            available_voices = ", ".join(self.available_voices)
            return self._create_text_reply(f"无效的语音类型: {voice_type}\n\n可用的语音类型: {available_voices}")
    
    def _handle_clear_memory(self, content, session_id):
        """处理清除记忆命令"""
        prefix = self._check_prefix(content, self.clear_memory_prefix)
        if not prefix:
            return None
        
        param = self._extract_prompt(content, prefix).strip().lower()
        
        if param == "all" or param == "所有":
            # 清除所有会话的记忆
            self.session_manager.clear_all_sessions()
            return self._create_text_reply("已清除所有会话记忆")
        else:
            # 清除当前会话的记忆
            self.session_manager.clear_session(session_id)
            return self._create_text_reply("已清除当前会话记忆")
    
    def _create_text_reply(self, text):
        """创建文本回复"""
        reply = Reply()
        reply.type = ReplyType.TEXT
        reply.content = text
        return reply
    
    def get_help_text(self, **kwargs):
        """获取帮助文本"""
        help_text = "🌸 Pollinations AI 聊天插件使用指南 🌸\n\n"
        
        help_text += "💬 聊天交流：\n"
        if self.chat_prefix:
            for prefix in self.chat_prefix:
                help_text += f"  {prefix} [问题内容]\n"
        else:
            help_text += "  当前配置为处理所有消息，无需前缀\n"
        
        help_text += "\n🔊 语音控制：\n"
        help_text += "  • 开启/关闭语音回复：\n"
        for prefix in self.voice_toggle_prefix:
            help_text += f"    {prefix} 开/关\n"
        
        help_text += "  • 设置语音类型：\n"
        for prefix in self.voice_set_prefix:
            help_text += f"    {prefix} [语音类型]\n"
        
        help_text += "\n💭 记忆管理：\n"
        help_text += "  • 清除当前会话记忆：\n"
        for prefix in self.clear_memory_prefix:
            help_text += f"    {prefix}\n"
        help_text += "  • 清除所有会话记忆：\n"
        for prefix in self.clear_memory_prefix:
            help_text += f"    {prefix} all\n"
        
        help_text += f"\n当前设置：\n"
        help_text += f"  • 语音回复: {'开启' if self.enable_voice else '关闭'}\n"
        help_text += f"  • 语音类型: {self.default_voice}\n"
        help_text += f"  • 上下文记忆: {'开启' if self.enable_memory else '关闭'}\n"
        help_text += f"  • 最大记忆条数: {self.max_history}\n"
        help_text += f"  • 使用模型: {self.api_params.get('model', 'openai')}\n"
        
        help_text += "\n可用的语音类型：\n"
        help_text += "  • alloy - 全能型中性语音\n"
        help_text += "  • echo - 低沉深邃的语音\n"
        help_text += "  • fable - 平静温暖的语音\n"
        help_text += "  • onyx - 坚定有力的语音\n"
        help_text += "  • nova - 友好精力充沛的语音\n"
        help_text += "  • shimmer - 轻快愉悦的语音\n"
        
        help_text += "\n示例：\n"
        if self.chat_prefix:
            help_text += f"  {self.chat_prefix[0] if self.chat_prefix else ''} 介绍一下Pollinations AI\n"
        else:
            help_text += "  介绍一下Pollinations AI\n"
        help_text += "  p语音开关 开\n"
        help_text += "  p设置语音 nova\n"
        help_text += "  p清除记忆\n"
        
        return help_text
    
    def _load_config_template(self):
        """加载配置模板"""
        logger.debug("[Pollinations聊天] 加载配置模板")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
            else:
                logger.warning(f"[Pollinations聊天] 配置模板文件不存在: {plugin_config_path}")
                return {}
        except Exception as e:
            logger.exception(f"[Pollinations聊天] 加载配置模板异常: {e}")
            return {} 