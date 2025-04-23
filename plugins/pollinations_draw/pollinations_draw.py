# encoding:utf-8

import json
import os
import re
import requests
import urllib.parse
from urllib.parse import quote
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
import plugins
from plugins import *
from config import conf


@plugins.register(
    name="PollinationsDraw",
    desire_priority=0,
    hidden=False,
    desc="一个集成Pollinations.AI的画图插件，支持自定义参数和模型切换",
    version="0.2",
    author="AI Assistant",
    namecn="Pollinations绘图"
)
class PollinationsDraw(Plugin):
    def __init__(self):
        super().__init__()
        try:
            # 加载配置
            self.config = super().load_config()
            if not self.config:
                self.config = self._load_config_template()
                
            # 功能前缀配置
            self.image_prompt_prefix = self.config.get("image_prompt_prefix", ["p画", "p生成图片"])
            self.list_models_prefix = self.config.get("list_models_prefix", ["p模型"])
            self.model_switch_prefix = self.config.get("model_switch_prefix", ["p切换模型"])
            
            # 随机生成功能开关
            self.random_generation_enabled = self.config.get("random_generation_enabled", True)
            
            # 默认图片设置
            self.default_image_model = self.config.get("default_image_model", "flux")
            self.default_width = self.config.get("default_width", 704)
            self.default_height = self.config.get("default_height", 704)
            self.default_seed = self.config.get("default_seed", 43)
            self.nologo = self.config.get("nologo", True)
            
            # 显示选项
            self.show_prompt_in_image_result = self.config.get("show_prompt_in_image_result", True)
            
            # 请求默认设置
            self.default_headers = {
                "Accept": "*/*",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
                "Referer": "https://pollinations.ai/"
            }
            
            # API基础URL
            self.image_api_url = "https://image.pollinations.ai/prompt/{}"
            self.image_models_url = "https://image.pollinations.ai/models"
            
            # 注册事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            
            logger.info("[Pollinations绘图] 插件初始化成功")
        except Exception as e:
            logger.error(f"[Pollinations绘图] 插件初始化失败: {e}")

    def on_handle_context(self, e_context: EventContext):
        """处理上下文事件"""
        if e_context["context"].type != ContextType.TEXT:
            return
            
        content = e_context["context"].content
        logger.debug(f"[Pollinations绘图] 收到消息: {content}")
        
        # 检查是否是插件命令
        if self._is_command(content):
            reply = None
            
            # 处理模型列表命令
            if self._check_prefix(content, self.list_models_prefix):
                logger.info("[Pollinations绘图] 处理模型列表命令")
                reply = self._handle_list_models(content)
            
            # 处理切换模型命令
            elif self._check_prefix(content, self.model_switch_prefix):
                logger.info("[Pollinations绘图] 处理切换模型命令")
                reply = self._handle_switch_model(content)
            
            # 处理图像生成命令
            elif self._check_prefix(content, self.image_prompt_prefix):
                logger.info("[Pollinations绘图] 处理图像生成命令")
                reply = self._handle_image_generation(content)
                
            # 如果有回复，则设置并结束事件处理
            if reply:
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
    
    def _is_command(self, content):
        """检查消息是否是插件命令"""
        if content.startswith(tuple(self.image_prompt_prefix)) or \
           content.startswith(tuple(self.list_models_prefix)) or \
           content.startswith(tuple(self.model_switch_prefix)):
            return True
        return False
    
    def _check_prefix(self, content, prefix_list):
        """检查消息是否以指定前缀开始"""
        for prefix in prefix_list:
            if content.startswith(prefix):
                return prefix
        return None
    
    def _extract_prompt(self, content, prefix):
        """从消息中提取提示词"""
        prompt = content[len(prefix):].strip()
        return prompt
    
    def _handle_image_generation(self, content):
        """处理图像生成命令"""
        prefix = self._check_prefix(content, self.image_prompt_prefix)
        if not prefix:
            return None
            
        # 提取提示词
        prompt = self._extract_prompt(content, prefix)
        if not prompt:
            return self._create_text_reply("请提供图像生成的提示词！")
        
        # 初始化参数
        import random
        
        # 随机生成参数（如果启用）
        if self.random_generation_enabled:
            models = self._get_available_models()
            params = {
                "model": random.choice(models) if models else "flux",
                "width": random.choice([512, 640, 704, 768, 1024]),
                "height": random.choice([512, 640, 704, 768, 1024]),
                "seed": random.randint(1, 9999),
                "nologo": True
            }
        else:
            params = {
                "model": self.default_image_model,
                "width": self.default_width,
                "height": self.default_height,
                "seed": self.default_seed,
                "nologo": self.nologo
            }
        
        # 提取参数
        # 模型参数
        model_match = re.search(r"模型[:：]([^\s]+)", prompt)
        if model_match:
            params["model"] = model_match.group(1)
            prompt = re.sub(r"模型[:：][^\s]+", "", prompt).strip()
        
        # 宽度参数
        width_match = re.search(r"宽度[:：](\d+)", prompt)
        if width_match:
            params["width"] = int(width_match.group(1))
            prompt = re.sub(r"宽度[:：]\d+", "", prompt).strip()
        
        # 高度参数
        height_match = re.search(r"高度[:：](\d+)", prompt)
        if height_match:
            params["height"] = int(height_match.group(1))
            prompt = re.sub(r"高度[:：]\d+", "", prompt).strip()
        
        # 随机种子参数
        seed_match = re.search(r"随机种子[:：](\d+)", prompt)
        if seed_match:
            params["seed"] = int(seed_match.group(1))
            prompt = re.sub(r"随机种子[:：]\d+", "", prompt).strip()
        
        # 无水印参数
        nologo_match = re.search(r"无水印[:：](true|false)", prompt, re.IGNORECASE)
        if nologo_match:
            params["nologo"] = nologo_match.group(1).lower() == "true"
            prompt = re.sub(r"无水印[:：](true|false)", "", prompt, flags=re.IGNORECASE).strip()
        
        try:
            # 构建请求URL
            quoted_prompt = quote(prompt)
            url = self.image_api_url.format(quoted_prompt)
            
            # 添加参数
            param_str = []
            for key, value in params.items():
                param_str.append(f"{key}={value}")
            
            if param_str:
                url += "?" + "&".join(param_str)
            
            # 创建回复
            reply = Reply()
            reply.type = ReplyType.IMAGE_URL
            reply.content = url
            
            # 增加额外信息的响应
            processed_prompt = f"生成图像: {prompt}\n模型: {params['model']}, 尺寸: {params['width']}x{params['height']}, 种子: {params['seed']}\n请稍等片刻..."
            self._create_text_reply(processed_prompt).content
            
            return reply
        except Exception as e:
            logger.error(f"[Pollinations绘图] 图像生成失败: {e}")
            return self._create_text_reply(f"图像生成失败: {str(e)}")
    
    def _handle_list_models(self, content):
        """处理列出模型命令"""
        prefix = self._check_prefix(content, self.list_models_prefix)
        if not prefix:
            return None
        
        query = self._extract_prompt(content, prefix).strip().lower()
        
        try:
            # 获取图像模型列表
            response = requests.get(self.image_models_url, headers=self.default_headers)
            
            if response.status_code == 200:
                models = response.json()
                
                # 如果有查询参数，过滤模型
                if query:
                    filtered_models = []
                    for model in models:
                        if query.lower() in model.lower():
                            filtered_models.append(model)
                    
                    if filtered_models:
                        result = f"当前默认模型: {self.default_image_model}\n\n找到匹配 '{query}' 的模型：\n" + "\n".join(filtered_models)
                    else:
                        result = f"当前默认模型: {self.default_image_model}\n\n没有找到匹配 '{query}' 的模型。\n所有可用的模型：\n" + "\n".join(models)
                else:
                    result = f"当前默认模型: {self.default_image_model}\n\n可用的图像模型：\n" + "\n".join(models)
                
                return self._create_text_reply(result)
            else:
                return self._create_text_reply(f"获取模型列表失败，状态码: {response.status_code}")
                
        except Exception as e:
            logger.error(f"[Pollinations绘图] 获取模型列表失败: {e}")
            return self._create_text_reply(f"获取模型列表失败: {str(e)}")
    
    def _handle_switch_model(self, content):
        """处理切换模型的命令"""
        prefix = self._check_prefix(content, self.model_switch_prefix)
        if not prefix:
            return None
            
        # 提取模型名称
        model_name = self._extract_prompt(content, prefix).strip()
        if not model_name:
            return self._create_text_reply(f"请指定要切换的模型名称！当前默认模型是: {self.default_image_model}")
        
        try:
            # 获取可用模型列表
            available_models = self._get_available_models()
            
            # 检查指定的模型是否可用
            model_found = False
            matched_model = None
            
            # 精确匹配
            if model_name in available_models:
                model_found = True
                matched_model = model_name
            else:
                # 模糊匹配 - 检查模型名称是否是可用模型的一部分
                for model in available_models:
                    if model_name.lower() in model.lower():
                        if matched_model is None:  # 取第一个匹配的
                            matched_model = model
                            model_found = True
            
            if model_found and matched_model:
                # 更新默认模型（仅在内存中）
                old_model = self.default_image_model
                self.default_image_model = matched_model
                
                return self._create_text_reply(f"默认模型已从 {old_model} 切换为 {matched_model}。")
            else:
                available_models_text = "\n".join(available_models[:10])  # 只显示前10个，避免消息过长
                return self._create_text_reply(f"未找到模型 '{model_name}'。\n可用的模型有：\n{available_models_text}\n...\n使用 'p模型' 查看完整列表。")
                
        except Exception as e:
            logger.error(f"[Pollinations绘图] 切换模型失败: {e}")
            return self._create_text_reply(f"切换模型失败: {str(e)}")
    
    def _get_available_models(self):
        """获取可用的模型列表"""
        try:
            response = requests.get(self.image_models_url, headers=self.default_headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"[Pollinations绘图] 获取模型列表失败，状态码: {response.status_code}")
                return ["flux", "sdxl", "kandinsky", "playground"]
        except Exception as e:
            logger.error(f"[Pollinations绘图] 获取模型列表失败: {e}")
            return ["flux", "sdxl", "kandinsky", "playground"]
    
    def _create_text_reply(self, text):
        """创建文本回复"""
        reply = Reply()
        reply.type = ReplyType.TEXT
        reply.content = text
        return reply
    
    def get_help_text(self, **kwargs):
        """获取帮助文本"""
        help_text = "🌸 Pollinations AI 绘图插件使用指南 🌸\n\n"
        
        help_text += "📷 生成图像：\n"
        for prefix in self.image_prompt_prefix:
            help_text += f"  {prefix} [提示词]\n"
        
        help_text += "\n支持的参数：\n"
        help_text += "  模型:xxx - 设置使用的模型\n"
        help_text += "  宽度:xxx - 设置图像宽度\n"
        help_text += "  高度:xxx - 设置图像高度\n"
        help_text += "  随机种子:xxx - 设置随机种子\n"
        help_text += "  无水印:true/false - 是否去除水印\n"
        
        if self.random_generation_enabled:
            help_text += "\n⚡ 随机生成功能已启用 ⚡\n"
            help_text += "当您未指定模型、尺寸或随机种子时，系统将随机选择这些参数。\n"
        
        help_text += "\n📋 查看模型列表：\n"
        for prefix in self.list_models_prefix:
            help_text += f"  {prefix} [可选:关键词搜索]\n"
        
        help_text += "\n🔄 切换默认模型：\n"
        for prefix in self.model_switch_prefix:
            help_text += f"  {prefix} [模型名称]\n"
        help_text += f"  当前默认模型: {self.default_image_model}\n"
        
        help_text += "\n示例：\n"
        help_text += "  p画 一只可爱的猫咪\n"
        help_text += "  p画 一只可爱的猫咪 模型:flux 宽度:512 高度:768 随机种子:42\n"
        help_text += "  p模型        # 列出所有模型\n"
        help_text += "  p模型 sd     # 搜索包含sd的模型\n"
        help_text += "  p切换模型 kandinsky  # 将默认模型切换为kandinsky\n"
        
        return help_text
    
    def _load_config_template(self):
        """加载配置模板"""
        logger.debug("[Pollinations绘图] 加载配置模板")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
            else:
                logger.warning(f"[Pollinations绘图] 配置模板文件不存在: {plugin_config_path}")
                return {}
        except Exception as e:
            logger.exception(f"[Pollinations绘图] 加载配置模板异常: {e}")
            return {} 