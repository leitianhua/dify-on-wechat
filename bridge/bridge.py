from bot.bot_factory import create_bot
from bridge.context import Context
from bridge.reply import Reply
from common import const
from common.log import logger
from common.singleton import singleton
from config import conf
from translate.factory import create_translator
from voice.factory import create_voice


@singleton
class Bridge(object):
    def __init__(self):
        self.btype = {
            "chat": const.CHATGPT,
            "voice_to_text": conf().get("voice_to_text", "openai"),
            "text_to_voice": conf().get("text_to_voice", "google"),
            "translate": conf().get("translate", "baidu"),
        }
        
        # 标识是否有有效的聊天模型配置
        self.has_valid_chat_model = True

        # 这边取配置的模型
        bot_type = conf().get("bot_type")
        if bot_type:
            self.btype["chat"] = bot_type
        else:
            model_type = conf().get("model") or const.GPT35
            if model_type in ["text-davinci-003"]:
                self.btype["chat"] = const.OPEN_AI
            if conf().get("use_azure_chatgpt", False):
                self.btype["chat"] = const.CHATGPTONAZURE
            if model_type in ["wenxin", "wenxin-4"]:
                self.btype["chat"] = const.BAIDU
            if model_type in ["xunfei"]:
                self.btype["chat"] = const.XUNFEI
            if model_type in [const.QWEN]:
                self.btype["chat"] = const.QWEN
            if model_type in [const.QWEN_TURBO, const.QWEN_PLUS, const.QWEN_MAX]:
                self.btype["chat"] = const.QWEN_DASHSCOPE
            if model_type and model_type.startswith("gemini"):
                self.btype["chat"] = const.GEMINI
            if model_type in [const.DIFY]:
                self.btype["chat"] = const.DIFY
            if model_type and model_type.startswith("glm"):
                self.btype["chat"] = const.ZHIPU_AI
            if model_type in [const.COZE]:
                self.btype["chat"] = const.COZE
            if model_type and model_type.startswith("claude-3"):
                self.btype["chat"] = const.CLAUDEAPI
            if model_type and model_type.startswith("deepseek-"):
                self.btype["chat"] = const.DEEPSEEK

            if model_type in ["claude"]:
                self.btype["chat"] = const.CLAUDEAI

            if model_type in [const.MOONSHOT, "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]:
                self.btype["chat"] = const.MOONSHOT

            if model_type in ["abab6.5-chat"]:
                self.btype["chat"] = const.MiniMax
            
            if conf().get("use_linkai") and conf().get("linkai_api_key"):
                self.btype["chat"] = const.LINKAI
                if not conf().get("voice_to_text") or conf().get("voice_to_text") in ["openai"]:
                    self.btype["voice_to_text"] = const.LINKAI
                if not conf().get("text_to_voice") or conf().get("text_to_voice") in ["openai", const.TTS_1, const.TTS_1_HD]:
                    self.btype["text_to_voice"] = const.LINKAI
        
        # 检查是否有有效的聊天模型配置
        if not conf().get("model") and not conf().get("bot_type"):
            self.has_valid_chat_model = False
            logger.warning("[Bridge] No chat model configured")
        else:
            # 检查API密钥是否配置
            model_type = self.btype.get("chat")
            if model_type == const.OPEN_AI and not conf().get("open_ai_api_key"):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for OpenAI")
            elif model_type == const.BAIDU and (not conf().get("baidu_wenxin_api_key") or not conf().get("baidu_wenxin_secret_key")):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for Baidu Wenxin")
            elif model_type == const.XUNFEI and (not conf().get("xunfei_app_id") or not conf().get("xunfei_api_key") or not conf().get("xunfei_api_secret")):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for Xunfei")
            elif model_type == const.QWEN and (not conf().get("qwen_access_key_id") or not conf().get("qwen_access_key_secret")):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for Qwen")
            elif model_type == const.QWEN_DASHSCOPE and not conf().get("dashscope_api_key"):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for Qwen Dashscope")
            elif model_type == const.GEMINI and not conf().get("gemini_api_key"):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for Gemini")
            elif model_type == const.DIFY and not conf().get("dify_api_key"):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for Dify")
            elif model_type == const.ZHIPU_AI and not conf().get("zhipu_ai_api_key"):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for Zhipu AI")
            elif model_type == const.COZE and (not conf().get("coze_api_key") or not conf().get("coze_bot_id")):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for Coze")
            elif model_type == const.MOONSHOT and not conf().get("moonshot_api_key"):
                self.has_valid_chat_model = False
                logger.warning(f"[Bridge] Missing API key for Moonshot")

        self.bots = {}
        self.chat_bots = {}

    # 模型对应的接口
    def get_bot(self, typename):
        if self.bots.get(typename) is None:
            # 如果是聊天模型且没有有效配置，则直接返回None
            if typename == "chat" and not self.has_valid_chat_model:
                logger.warning("[Bridge] No valid chat model configured, cannot create bot instance")
                return None
                
            # 检查其他类型模型的配置
            if typename == "voice_to_text":
                voice_type = self.btype.get(typename)
                if voice_type == "openai" and not conf().get("open_ai_api_key"):
                    logger.warning("[Bridge] Missing API key for OpenAI voice to text")
                    return None
                elif voice_type == "baidu" and (not conf().get("baidu_api_key") or not conf().get("baidu_secret_key")):
                    logger.warning("[Bridge] Missing API key for Baidu voice to text")
                    return None
                elif voice_type == "azure" and not conf().get("azure_voice_api_key"):
                    logger.warning("[Bridge] Missing API key for Azure voice to text")
                    return None
            elif typename == "text_to_voice":
                voice_type = self.btype.get(typename)
                if voice_type == "openai" and not conf().get("open_ai_api_key"):
                    logger.warning("[Bridge] Missing API key for OpenAI text to voice")
                    return None
                elif voice_type == "baidu" and (not conf().get("baidu_api_key") or not conf().get("baidu_secret_key")):
                    logger.warning("[Bridge] Missing API key for Baidu text to voice")
                    return None
                elif voice_type == "azure" and not conf().get("azure_voice_api_key"):
                    logger.warning("[Bridge] Missing API key for Azure text to voice")
                    return None
                
            logger.info("create bot {} for {}".format(self.btype[typename], typename))
            try:
                if typename == "text_to_voice":
                    self.bots[typename] = create_voice(self.btype[typename])
                elif typename == "voice_to_text":
                    self.bots[typename] = create_voice(self.btype[typename])
                elif typename == "chat":
                    self.bots[typename] = create_bot(self.btype[typename])
                elif typename == "translate":
                    self.bots[typename] = create_translator(self.btype[typename])
            except Exception as e:
                logger.error(f"[Bridge] Failed to create {typename} bot: {str(e)}")
                return None
        return self.bots[typename]

    def get_bot_type(self, typename):
        return self.btype[typename]

    def fetch_reply_content(self, query, context: Context) -> Reply:
        # 检查是否有有效的聊天模型配置
        if not self.has_valid_chat_model:
            logger.warning("[Bridge] No valid chat model configured, skipping model call")
            # 直接返回None，这样上层调用时不会发送任何回复
            return None
            
        # 如果一切正常，调用模型
        bot = self.get_bot("chat")
        if bot is None:
            logger.warning("[Bridge] Failed to create bot instance, skipping model call")
            # 直接返回None，这样上层调用时不会发送任何回复
            return None
            
        return bot.reply(query, context)

    def fetch_voice_to_text(self, voiceFile) -> Reply:
        voice_bot = self.get_bot("voice_to_text")
        if voice_bot is None:
            logger.warning("[Bridge] No valid voice_to_text model configured, skipping voice to text conversion")
            return None
        return voice_bot.voiceToText(voiceFile)

    def fetch_text_to_voice(self, text) -> Reply:
        voice_bot = self.get_bot("text_to_voice")
        if voice_bot is None:
            logger.warning("[Bridge] No valid text_to_voice model configured, skipping text to voice conversion")
            return None
        return voice_bot.textToVoice(text)

    def fetch_translate(self, text, from_lang="", to_lang="en") -> Reply:
        translate_bot = self.get_bot("translate")
        if translate_bot is None:
            logger.warning("[Bridge] No valid translate model configured, skipping translation")
            return None
        return translate_bot.translate(text, from_lang, to_lang)

    def find_chat_bot(self, bot_type: str):
        if self.chat_bots.get(bot_type) is None:
            self.chat_bots[bot_type] = create_bot(bot_type)
        return self.chat_bots.get(bot_type)

    def reset_bot(self):
        """
        重置bot路由
        """
        self.__init__()
