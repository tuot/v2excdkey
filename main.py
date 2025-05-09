import os
import json
import time
import requests
import pytz
import logging
from datetime import datetime
from newspaper import Article
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sys
from openai import OpenAI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),  # 输出到标准输出
    ],
)


PROMPT = """
Please act as an information extraction assistant to process the forum post content I provide, which is in Markdown format and includes:

- The original post content by the thread starter (OP)
- Any postscript (PS) or additional notes by the OP
- Replies from other users

The post involves distribution of activation codes or redemption codes. Please complete the following tasks:

1. Extract **all activation codes and redemption codes** from the OP’s main post and any postscript. The codes may have various formats (letters, numbers, mixed, possibly with separators) and usually look like serial keys.

2. **Exclude any activation or redemption codes mentioned as used or redeemed** in other users’ replies, i.e., if a reply states a code is "used," "redeemed," "invalid," or similar, exclude that code.

3. Output all activation or redemption codes that are **originally posted by the OP and not confirmed as used**, each code on its own line.

4. Ignore any text unrelated to activation or redemption codes and do not output anything else.

Example output format:
```
CODE-123-ABCD
ACTIVATE-XYZ-7890
FREEKEY-000111
```

Please ensure that only codes issued by the OP and not confirmed as used are included.
"""


class Crawl4Ai:
    def __init__(self, base_url: str = "http://localhost:11235"):
        self.base_url = base_url

    def submit_and_wait(
        self, request_data: Dict[str, Any], timeout: int = 60
    ) -> Dict[str, Any]:
        # Submit crawl job
        response = requests.post(f"{self.base_url}/crawl", json=request_data)
        if response.status_code == 200:
            return response.json()
        raise Exception(f"Failed to submit crawl job: {response.text}")


class V2EXMonitor:
    def __init__(self):
        load_dotenv()
        self.storage_file = os.getenv("STORAGE_FILE", "processed_posts.json")
        self.keywords = os.getenv("KEYWORDS", "送码,兑换码,激活码").split(",")
        self.processed_posts = self._load_processed_posts()

    def _load_processed_posts(self) -> Dict:
        """加载已处理的帖子记录"""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logging.error("加载已处理帖子记录失败: %s", e)
            return {}

    def _save_processed_posts(self):
        """保存已处理的帖子记录"""
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.processed_posts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error("保存已处理帖子记录失败: %s", e)

    def _check_keywords(self, text: str) -> bool:
        """检查文本是否包含关键词"""
        return any(keyword in text for keyword in self.keywords)

    def _get_latest_posts(self) -> List[Dict]:
        """获取最新的帖子"""
        try:
            url = os.getenv("V2EX_API_URL")
            url = f"{url}?t={int(time.time() * 1000)}"
            response = requests.get(
                os.getenv("V2EX_API_URL"),
                headers={
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error("获取最新帖子失败: %s", e)
            return []

    def _scrape_content(self, url: str) -> Optional[str]:
        """抓取帖子内容"""
        tester = Crawl4Ai(os.getenv("CRAWL4AI_BASE_URL"))
        try:
            request = {"urls": [url], "priority": 10}
            result = tester.submit_and_wait(request)
            return result["results"][0]["markdown"]["raw_markdown"]
        except Exception as e:
            logging.error("抓取内容失败: %s", e)
            return None

    def _extract_codes_with_ai(self, content: str) -> Optional[Dict]:
        """使用AI提取激活码和附言信息"""
        try:
            client = OpenAI(
                base_url=os.getenv("AI_API_URL"),
                api_key=os.getenv("AI_API_KEY"),
            )
            response = client.chat.completions.create(
                model=os.getenv("AI_MODEL"),
                messages=[
                    {
                        "role": "system",
                        "content": PROMPT,
                    },
                    {"role": "user", "content": content},
                ],
                temperature=0.8,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error("AI提取信息失败: %s", e)
            return None

    def _send_notification(self, title: str, content: str):
        """发送通知"""
        notification_type = os.getenv("NOTIFICATION_TYPE", "bark")

        if notification_type == "bark":
            self._send_bark_notification(title, content)
        elif notification_type == "email":
            self._send_email_notification(title, content)

    def _send_bark_notification(self, title: str, content: str):
        """发送Bark通知"""
        try:
            url = "https://api.day.app/%s" % os.getenv("BARK_API_KEY")
            requests.post(
                url,
                json={
                    "title": title,
                    "body": content,
                },
            )
        except Exception as e:
            logging.error("发送Bark通知失败: %s", e)

    def _send_email_notification(self, title: str, content: str):
        """发送邮件通知"""
        try:
            msg = MIMEMultipart()
            msg["From"] = os.getenv("EMAIL_USERNAME")
            msg["To"] = os.getenv("EMAIL_RECIPIENT")
            msg["Subject"] = title

            msg.attach(MIMEText(content, "plain"))

            server = smtplib.SMTP(
                os.getenv("EMAIL_SMTP_SERVER"), int(os.getenv("EMAIL_SMTP_PORT"))
            )
            server.starttls()
            server.login(os.getenv("EMAIL_USERNAME"), os.getenv("EMAIL_PASSWORD"))
            server.send_message(msg)
            server.quit()
        except Exception as e:
            logging.error("发送邮件通知失败: %s", e)

    def process_posts(self):
        """处理帖子"""
        posts = self._get_latest_posts()
        for post in posts:
            post_id = str(post["id"])
            last_modified = post["last_modified"]

            # 检查是否包含关键词
            if not (
                self._check_keywords(post["title"])
                or self._check_keywords(post["content"])
            ):
                continue

            # 检查是否需要处理
            if post_id in self.processed_posts:
                if last_modified <= self.processed_posts[post_id]["last_modified"]:
                    continue

            logging.info(
                "处理帖子, 更新时间： %s, Title: %s, Url: %s",
                datetime.fromtimestamp(
                    last_modified,
                    pytz.timezone("Asia/Shanghai"),
                ).strftime("%Y-%m-%d %H:%M:%S"),
                post["title"],
                post["url"],
            )
            # 抓取内容
            content = self._scrape_content(post["url"])
            if not content:
                article = Article(post["url"], fetch_images=False)
                article.download()
                article.parse()
                if article.text:
                    content = article.text
                else:
                    logging.error("无法抓取内容")
                    continue

            # 提取信息
            extracted_info = self._extract_codes_with_ai(content) or ""

            # 发送通知
            logging.info("发现新激活码: %s", extracted_info)
            self._send_notification(
                "V2EX新激活码: %s" % post["title"],
                "链接: %s\n\n提取信息:\n%s"
                % (
                    post["url"],
                    extracted_info.replace("*", ""),
                ),
            )

            # 更新处理记录
            self.processed_posts[post_id] = {
                "last_modified": last_modified,
                "title": post["title"],
                "url": post["url"],
            }
            self._save_processed_posts()

    def run(self):
        """运行监控"""
        logging.info("开始监控V2EX帖子...")
        CRAWL_TIMEOUT = int(os.getenv("CRAWL_TIMEOUT", 60))
        while True:
            try:
                logging.info(
                    "检查V2EX帖子 %s",
                    datetime.now(tz=pytz.timezone("Asia/Shanghai")).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                )
                self.process_posts()
                logging.info("检查V2EX帖子完成")
                time.sleep(CRAWL_TIMEOUT)  # 每分钟检查一次
            except Exception as e:
                logging.error("监控过程出错: %s", e)
                time.sleep(CRAWL_TIMEOUT)


if __name__ == "__main__":
    monitor = V2EXMonitor()
    monitor.run()
