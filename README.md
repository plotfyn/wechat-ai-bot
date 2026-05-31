# WeChat AI Auto-Reply Bot

微信 AI 自动回复机器人，基于 OCR 红点检测 + DeepSeek API，无需触碰微信协议。

## 快速开始

1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 配置 API Key
```bash
copy config.example.json config.json
# 编辑 config.json，填入你的 DeepSeek API Key
```

3. 登录微信，双击 `start.bat` 运行

## 安全说明

- 完全不触碰微信协议，仅使用截图 + 模拟输入
