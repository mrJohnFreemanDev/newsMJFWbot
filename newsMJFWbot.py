import os
import logging
import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime, timedelta
import pytz
import feedparser
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from aiogram import Bot
from asyncio import sleep, gather, create_task
from dotenv import load_dotenv
from urllib.parse import urlparse
from tenacity import retry, wait_fixed, stop_after_attempt

# Загрузка токенов из файла .env
load_dotenv("all.env")

TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

if not TELEGRAM_API_TOKEN:
    raise ValueError("Отсутствует TELEGRAM_API_TOKEN в файле .env")

# Инициализация бота
bot = Bot(token=TELEGRAM_API_TOKEN)

# Локальная временная зона
LOCAL_TIMEZONE = pytz.timezone('Europe/Moscow')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# RSS источники с задержками публикаций
RSS_SOURCES = [
    {"url": "https://lenta.ru/rss/news", "source": "lenta.ru", "delay": 300},  # каждые 5 минут
    {"url": "https://ria.ru/export/rss2/archive/index.xml", "source": "ria.ru", "delay": 600},  # каждые 10 минут
    {"url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", "source": "rbc.ru", "delay": 900}  # каждые 15 минут
]

# Настройки подключения к базе данных
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",  # Укажите пароль
    "database": "newsMJFWbot",
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

# Срок хранения записей в днях
RECORD_RETENTION_DAYS = 30

@retry(wait=wait_fixed(5), stop=stop_after_attempt(3))
def get_db_connection():
    """Устанавливает соединение с базой данных с повторной попыткой."""
    try:
        return pymysql.connect(**DB_CONFIG)
    except pymysql.MySQLError as err:
        logging.error(f"Ошибка подключения к базе данных: {err}")
        raise

def initialize_db():
    """Создаёт таблицу для учёта опубликованных статей, если её нет."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS published_articles (
                id INT AUTO_INCREMENT PRIMARY KEY,
                link VARCHAR(1024) NOT NULL UNIQUE,
                title VARCHAR(512),
                source VARCHAR(256),
                content TEXT,
                publication_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                posted BOOLEAN DEFAULT FALSE
            )
            '''
        )
        conn.commit()
        logging.info("База данных и таблица опубликованных статей готовы.")
    except pymysql.MySQLError as e:
        logging.error(f"Ошибка создания таблицы: {e}")
    finally:
        conn.close()

def clear_old_records():
    """Удаляет устаревшие записи из базы данных."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        threshold_date = datetime.now() - timedelta(days=RECORD_RETENTION_DAYS)
        cursor.execute("DELETE FROM published_articles WHERE publication_date < %s", (threshold_date,))
        conn.commit()
        logging.info(f"Удалены записи старше {RECORD_RETENTION_DAYS} дней.")
    except pymysql.MySQLError as e:
        logging.error(f"Ошибка при удалении устаревших записей: {e}")
    finally:
        conn.close()

def clean_html(raw_html):
    """Удаляет неподдерживаемые теги из HTML."""
    soup = BeautifulSoup(raw_html, 'html.parser')
    allowed_tags = ['b', 'i', 'u', 'a', 'code', 'pre']
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            tag.unwrap()
    return str(soup)

def is_article_published(link):
    """Проверяет, была ли статья уже опубликована."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT posted FROM published_articles WHERE link = %s", (link,))
        result = cursor.fetchone()
        return result and result['posted']
    finally:
        conn.close()

def mark_article_as_published(link):
    """Обновляет статус статьи на опубликованную."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE published_articles SET posted = TRUE WHERE link = %s", (link,))
        conn.commit()
    except pymysql.MySQLError as e:
        logging.error(f"Ошибка при обновлении статуса статьи: {e}")
    finally:
        conn.close()

def add_article_to_db(link, title, source, content):
    """Добавляет статью в таблицу опубликованных."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT IGNORE INTO published_articles (link, title, source, content) VALUES (%s, %s, %s, %s)",
            (link, title, source, content)
        )
        conn.commit()
    except pymysql.MySQLError as e:
        logging.error(f"Ошибка при добавлении статьи в базу данных: {e}")
    finally:
        conn.close()

def is_valid_url(url):
    """Проверяет, является ли URL корректным."""
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)

async def fetch_full_article_with_playwright(article_url):
    """Загружает полный текст статьи и HTML через Playwright."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(article_url, timeout=30000, wait_until="domcontentloaded")
            html = await page.content()
            await browser.close()

        soup = BeautifulSoup(html, 'html.parser')

        selectors = [
            'div.article__text',  # Основной селектор для текста статьи
            'div.content',        # Альтернативный селектор
            'div.topic-body__content'  # Другой возможный селектор
        ]

        for selector in selectors:
            content = soup.select_one(selector)
            if content:
                return content.prettify(), content.get_text(strip=True)

        logging.warning(f"Контент не найден на странице: {article_url}")
        return None, "Контент отсутствует."
    except Exception as e:
        logging.error(f"Ошибка при загрузке статьи {article_url}: {e}")
        return None, ""

async def process_rss_feed(rss_feed):
    """Обрабатывает отдельный RSS-канал."""
    while True:
        try:
            feed = feedparser.parse(rss_feed["url"])
            for entry in feed.entries:
                if not is_valid_url(entry.link):
                    logging.warning(f"Некорректная ссылка: {entry.link}")
                    continue

                if not is_article_published(entry.link):
                    html, full_text = await fetch_full_article_with_playwright(entry.link)
                    if full_text:
                        add_article_to_db(entry.link, entry.title, rss_feed["source"], full_text)
                        header = f"<b><u>{entry.title}</u></b>\n"
                        source_info = f"<i>Источник: {rss_feed['source']}</i>\n"
                        footer = f"\n<a href=\"{entry.link}\">Читать полностью на сайте</a>"
                        truncated_content = full_text[:3072]
                        message = f"{header}{source_info}\n{truncated_content}{footer}"

                        cleaned_message = clean_html(message)

                        await bot.send_message(
                            chat_id=TELEGRAM_CHANNEL_ID,
                            text=cleaned_message,
                            parse_mode="HTML"
                        )
                        logging.info(f"Опубликована статья: {entry.title}")
                        mark_article_as_published(entry.link)
                        break

            await sleep(rss_feed["delay"])
        except Exception as e:
            logging.error(f"Ошибка при обработке RSS {rss_feed['source']}: {e}")

async def periodic_notification():
    """Отправляет сообщение в канал каждые 30 минут."""
    while True:
        try:
            message = (
                "<b>Добро пожаловать!</b>\n"
                "<i>Этот канал создан для демонстрации возможностей Telegram-бота</i> - <b>News MJFW Bot</b>.\n"
                "<i>Связаться с разработчиком можно по адресу:</i> "
                "<a href=\"https://www.mjfw.ru/\">mjfw.ru</a>."
            )
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=message,
                parse_mode="HTML"
            )
            logging.info("Периодическое сообщение отправлено в канал.")
        except Exception as e:
            logging.error(f"Ошибка при отправке периодического сообщения: {e}")
        await sleep(1800)  # Задержка в 30 минут

async def main():
    clear_old_records()
    initialize_db()
    logging.info("Бот запущен.")

    tasks = [
        create_task(process_rss_feed(rss_feed)) for rss_feed in RSS_SOURCES
    ]
    tasks.append(create_task(periodic_notification()))
    await gather(*tasks)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
