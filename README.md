# 微信 AI 自动回复机器人

基于 pywinauto + DeepSeek 的纯 UI 自动化方案，零 Hook、零注入、零激活码。

## 原理

`
微信消息 → pywinauto 读取 UI 文本 → DeepSeek 生成回复 → pyautogui 模拟输入 → 微信发送
`

完全模拟人类操作：读取屏幕上的文字，然后模拟键盘打字发送回复。
微信无法判断是人在操作还是程序在操作。

## 快速开始

### 1. 安装 Python 3.10+

如果还没装 Python，去 https://www.python.org/downloads/ 下载安装。
安装时勾选 "Add Python to PATH"。

### 2. 安装依赖

`ash
cd wechat-bot-v2
pip install -r requirements.txt
`

### 3. 配置 DeepSeek API Key

编辑 config.json，把 deepseek_api_key 改成你的 Key:

`json
{
    "deepseek_api_key": "sk-xxxxxxxxxxxxxxxx",
    ...
}
`

获取 API Key: https://platform.deepseek.com/api_keys
(DeepSeek 很便宜，日常聊天一个月几块钱)

### 4. 启动

`ash
# 方式1: 双击 start.bat
# 方式2: 命令行
python wechat_bot.py
`

启动前确保：
- 微信电脑版已登录
- 微信窗口可见 (不要最小化到系统托盘)
- 打开你想让机器人监控的聊天窗口

### 5. 使用

- 机器人会监控当前打开的聊天窗口
- 有新消息时自动调用 DeepSeek 生成回复
- 按 Ctrl+C 停止

## 配置说明

| 配置项 | 说明 |
|--------|------|
| whitelist_contacts | 私聊白名单，如 ["张三", "李四"]。留空=回复所有人 |
| whitelist_groups | 群聊白名单，如 ["工作群", "家人群"]。留空=不回复群聊 |
| uto_reply_prefix | 回复前缀，如 "[AI]"，留空=不加前缀 |
| poll_interval | 检测间隔(秒)，默认3秒 |
| system_prompt | 机器人的人设，可自定义 |

## 文件说明

`
wechat-bot-v2/
├── wechat_bot.py      # 主程序
├── config.json        # 配置文件 (填API Key)
├── requirements.txt   # Python依赖
└── start.bat          # 一键启动
