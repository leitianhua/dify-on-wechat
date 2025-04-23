# Pollinations AI 聊天插件

一个集成 Pollinations.AI API 的聊天插件，支持文本交流、语音回复和上下文记忆功能。使用OpenAI兼容接口实现更强大的对话能力。

## 功能

- 文本聊天：调用 Pollinations 的 OpenAI 兼容接口进行对话
- 语音回复：支持将AI回复转为语音输出
- 语音设置：可调整语音开关和选择不同语音类型
- 上下文记忆：支持记住对话历史记录，提供连续对话体验
- 区分对话场景：自动区分私聊和群聊的上下文管理
- 自定义AI模型和系统提示：支持配置不同的模型和提示
- 支持长文本：使用 POST 请求处理更长的文本内容

## 使用方法

### 文本聊天

使用以下前缀命令进行聊天：
```
p问 [问题内容]
p聊 [问题内容]
```

示例：
```
p问 介绍一下Pollinations AI
p聊 解释一下量子计算机的原理
```

### 语音开关控制

使用以下命令开启或关闭语音回复：
```
p语音开关 开
p语音开关 关
```

### 设置语音类型

使用以下命令更改语音类型：
```
p设置语音 [语音类型]
```

例如：
```
p设置语音 nova
```

### 管理对话记忆

清除当前会话的记忆：
```
p清除记忆
```

清除所有会话的记忆：
```
p清除记忆 all
p清除记忆 所有
```

## 可用语音类型

插件支持以下语音类型：
- `alloy` - 全能型中性语音
- `echo` - 低沉深邃的语音
- `fable` - 平静温暖的语音
- `onyx` - 坚定有力的语音
- `nova` - 友好精力充沛的语音
- `shimmer` - 轻快愉悦的语音

## 上下文记忆说明

- 私聊模式：每个用户有独立的对话记忆
- 群聊模式：
  - 非共享会话群：每个用户在每个群有独立的对话记忆
  - 共享会话群：整个群共享一个对话记忆
- 默认记忆最近10条消息，超出会自动删除最早的记录
- 可通过配置开启/关闭记忆功能以及调整记忆条数

## 技术说明

本插件使用 Pollinations.AI 的 OpenAI 兼容接口 (`https://text.pollinations.ai/openai`)，支持：

- 使用 POST 请求处理更长的对话内容
- 按 OpenAI 格式构建消息历史
- 支持文本和语音生成
- 自动设置 private 参数保护隐私

## API 参数说明

通过 `config.json` 中的 `api_params` 配置项，可以自定义 AI 的行为：

- `model`: 生成模型，默认为 "openai"，可选如 "mistral" 等
- `system`: 系统提示词，用于指导AI行为，默认为 "你是个乐于助人的ai助手"

其他参数如 private 等由插件自动设置为合适的值。

## 配置说明

在 `config.json` 中可以配置以下内容：

```json
{
    "chat_prefix": ["p问", "p聊"],
    "voice_toggle_prefix": ["p语音开关"],
    "voice_set_prefix": ["p设置语音"],
    "clear_memory_prefix": ["p清除记忆"],
    "enable_voice": false,
    "default_voice": "alloy",
    "enable_memory": true,
    "max_history": 10,
    "api_params": {
        "model": "openai",
        "system": "你是个乐于助人的ai助手"
    }
}
```

- `chat_prefix`: 聊天命令前缀 (设为空数组[]会处理所有消息)
- `voice_toggle_prefix`: 语音开关命令前缀
- `voice_set_prefix`: 语音设置命令前缀
- `clear_memory_prefix`: 清除记忆命令前缀
- `enable_voice`: 是否默认启用语音回复
- `default_voice`: 默认使用的语音类型
- `enable_memory`: 是否启用上下文记忆功能
- `max_history`: 每个会话保存的最大历史消息数量
- `api_params`: Pollinations API 参数配置，包含 model 和 system 两个配置项