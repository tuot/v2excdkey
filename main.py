import os
import json
import time
import requests
import logging
from datetime import datetime
from newspaper import Article
from dotenv import load_dotenv
from typing import Dict, List, Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),  # 输出到标准输出
    ],
)


class V2EXMonitor:
    def __init__(self):
        load_dotenv()
        self.storage_file = os.getenv("STORAGE_FILE", "processed_posts.json")
        self.keywords = os.getenv("KEYWORDS", "送,码,兑换码,激活码").split(",")
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
            response = requests.get(os.getenv("V2EX_API_URL"))
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error("获取最新帖子失败: %s", e)
            return []

    def _scrape_content(self, url: str) -> Optional[str]:
        """抓取帖子内容"""
        try:
            response = requests.post(
                os.getenv("SCRAPE_API_URL"), json={"formats": ["markdown"], "url": url}
            )
            response.raise_for_status()
            return response.json()["data"]["markdown"]
        except Exception as e:
            logging.error("抓取内容失败: %s", e)
            return None

    def _extract_codes_with_ai(self, content: str) -> Optional[Dict]:
        """使用AI提取激活码和附言信息"""
        try:
            response = requests.post(
                os.getenv("OPENROUTER_API_URL"),
                headers={
                    "Authorization": "Bearer %s" % os.getenv("OPENROUTER_API_KEY"),
                    "Content-Type": "application/json",
                },
                json={
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                    "messages": [
                        {
                            "role": "system",
                            "content": "请从文本中提取激活码和附言信息。如果有激活码，请提取出来；如果有附言，请提取时间和其中的激活码。返回的数据不要是 markdown 格式，就是纯文本信息，每行只包含激活码，每行一个。如果有附言，附言中的激活码也是每一行一个。",
                        },
                        {"role": "user", "content": content},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
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
                datetime.fromtimestamp(last_modified).strftime("%Y-%m-%d %H:%M:%S"),
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
            extracted_info = self._extract_codes_with_ai(content)
            if not extracted_info:
                continue

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
                    "检查V2EX帖子 %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
