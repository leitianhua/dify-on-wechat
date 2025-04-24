# 美女视频插件 (Beauty Video Plugin)

这是一个用于获取美女视频和小姐姐视频的插件，基于sakuraTools插件的相关功能提取而来。

## 功能特点

- 获取随机美女视频
- 获取随机小姐姐视频

## 使用方法

1. 发送关键词 "美女" 获取随机美女视频
2. 发送关键词 "小姐姐" 获取随机小姐姐视频

## 配置说明

在 `config.json` 文件中可以自定义触发关键词：

```json
{
    "young_girl_keyword": ["小姐姐"],
    "beautiful_keyword": ["美女"]
}
```

可以根据需要添加更多关键词。

## 视频来源

- 小姐姐视频来源: https://api.apiopen.top/api/getMiniVideo
- 美女视频来源: https://api.kuleu.com/api/MP4_xiaojiejie

## 依赖库

- Python 3.6+
- requests
- PIL

## 安装方法

1. 将插件目录复制到 `plugins` 目录下
2. 重启程序即可使用

## 注意事项

插件会每天自动清理临时文件，避免占用过多存储空间。

## 作者

- 原始代码: sakura7301
- 修改整理: user 