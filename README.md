# V2EX 激活码监控脚本

这个脚本用于监控 V2EX 论坛上的激活码相关帖子，并在发现新内容时发送通知。

## 功能特点

- 每分钟检查一次 V2EX 最新帖子
- 自动识别包含激活码相关关键词的帖子
- 使用 AI 提取激活码和附言信息
- 支持 Bark 和邮件两种通知方式
- 记录已处理帖子的时间戳，避免重复处理
- 完整的日志记录

## 安装

1. 克隆仓库：
```bash
git clone [repository-url]
cd [repository-name]
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置环境变量：
```bash
cp .env.example .env
```
然后编辑 `.env` 文件，填入相应的配置信息。

## 配置说明

在 `.env` 文件中需要配置以下内容：

- API Keys:
  - `OPENROUTER_API_KEY`: OpenRouter API 密钥
  - `BARK_API_KEY`: Bark 通知 API 密钥（如果使用 Bark 通知）

- API Endpoints:
  - `V2EX_API_URL`: V2EX API 地址
  - `SCRAPE_API_URL`: 内容抓取 API 地址
  - `OPENROUTER_API_URL`: OpenRouter API 地址

- 通知设置：
  - `NOTIFICATION_TYPE`: 通知类型（bark 或 email）
  - 如果使用邮件通知，需要配置邮件服务器相关信息

- 存储设置：
  - `STORAGE_FILE`: 已处理帖子记录文件路径

- 关键词设置：
  - `KEYWORDS`: 监控的关键词，用逗号分隔

## 使用方法

1. 确保所有配置都正确设置
2. 运行脚本：
```bash
python main.py
```

## 日志

脚本运行日志保存在 `v2ex_monitor.log` 文件中。

## 注意事项

- 确保有稳定的网络连接
- 建议使用 screen 或 tmux 等工具在后台运行脚本
- 定期检查日志文件，确保脚本正常运行
