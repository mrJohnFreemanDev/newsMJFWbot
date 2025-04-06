# 📰 newsMJFWbot

A Telegram bot that automatically fetches and publishes news from major Russian RSS feeds to a Telegram channel. Designed specifically for the Russian news segment.

## 🧩 Features

- Parses and publishes news from:
  - Lenta.ru
  - RIA Novosti
  - RBC
- Uses Playwright to fetch full article content
- Sends rich HTML-formatted posts to Telegram channel
- Avoids reposting already published articles
- Cleans up old records from database
- Periodic messages to keep the channel alive

## ⚙️ Tech Stack

- Python 3.10+
- Aiogram (Telegram Bot API)
- feedparser
- Playwright (for full-text loading)
- BeautifulSoup
- pymysql (MariaDB)
- dotenv
- Logging with rotation

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/newsMJFWbot.git
cd newsMJFWbot
```

### 2. Create `.env` file

```env
TELEGRAM_API_TOKEN=your_telegram_bot_token
TELEGRAM_CHANNEL_ID=@your_channel_username
```

### 3. Configure MySQL

Ensure you have a MySQL database set up with the following details:
- host: localhost
- user: root
- password: (your password)
- database: newsMJFWbot

### 4. Install dependencies

```bash
pip install -r requirements.txt
playwright install
```

### 5. Run the bot

```bash
python newsMJFWbot.py
```

## 📬 Contact

- Telegram: [@Mr_John_Freeman_works](https://t.me/Mr_John_Freeman_works)
- Email: [mr.john.freeman.works.rus@gmail.com](mailto:mr.john.freeman.works.rus@gmail.com)

---

📰 Created with care by Ivan Mudriakov — your silent newsroom ninja.
