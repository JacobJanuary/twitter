#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os
import datetime
import re
# BeautifulSoup и requests больше не нужны для скачивания изображений
# import requests
# from bs4 import BeautifulSoup
# hashlib и urllib.parse больше не нужны для изображений
# import hashlib
# import urllib.parse
import mysql.connector
from mysql.connector import Error

# Глобальная настройка отладки
DEBUG = True

# Директории для хранения данных
CACHE_DIR = "twitter_cache"
# IMAGES_DIR больше не нужен
# IMAGES_DIR = "twitter_images"
os.makedirs(CACHE_DIR, exist_ok=True)
# os.makedirs(IMAGES_DIR, exist_ok=True) # Удалено


def debug_print(*args, **kwargs):
    """Функция для вывода отладочной информации"""
    if DEBUG:
        print("[ОТЛАДКА]", *args, **kwargs)


def initialize_mysql(config):
    """Инициализирует подключение к MySQL и создает необходимые таблицы"""
    try:
        connection = mysql.connector.connect(**config)

        if connection.is_connected():
            cursor = connection.cursor()

            # Создаем таблицу для пользователей
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                name VARCHAR(255),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            # Создаем таблицу для твитов
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tweets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tweet_id VARCHAR(255) UNIQUE,
                user_id INT,
                tweet_text TEXT,
                created_at DATETIME,
                url VARCHAR(255),
                likes INT DEFAULT 0,
                retweets INT DEFAULT 0,
                replies INT DEFAULT 0,
                is_retweet BOOLEAN DEFAULT FALSE,
                original_author VARCHAR(255),
                inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_created_at (created_at),
                INDEX idx_user_id (user_id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            # --- Удалено создание таблиц images, articles, tweet_links, article_links ---
            # # Создаем таблицу для изображений (УДАЛЕНО)
            # cursor.execute("""
            # CREATE TABLE IF NOT EXISTS images (
            #     id INT AUTO_INCREMENT PRIMARY KEY,
            #     tweet_id INT,
            #     image_url VARCHAR(1024),
            #     local_path VARCHAR(1024),
            #     image_hash VARCHAR(32),
            #     FOREIGN KEY (tweet_id) REFERENCES tweets(id) ON DELETE CASCADE,
            #     INDEX idx_tweet_id (tweet_id),
            #     INDEX idx_image_hash (image_hash)
            # ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            # """)
            #
            # # Создаем таблицу для статей (УДАЛЕНО)
            # cursor.execute("""
            # CREATE TABLE IF NOT EXISTS articles (
            #     id INT AUTO_INCREMENT PRIMARY KEY,
            #     tweet_id INT,
            #     article_url VARCHAR(1024),
            #     title TEXT,
            #     author VARCHAR(255),
            #     published_date VARCHAR(255),
            #     source_domain VARCHAR(255),
            #     content LONGTEXT,
            #     inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            #     FOREIGN KEY (tweet_id) REFERENCES tweets(id) ON DELETE CASCADE,
            #     INDEX idx_tweet_id (tweet_id),
            #     INDEX idx_source_domain (source_domain)
            # ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            # """)
            #
            # # Создаем таблицу для ссылок из твитов (УДАЛЕНО)
            # cursor.execute("""
            # CREATE TABLE IF NOT EXISTS tweet_links (
            #     id INT AUTO_INCREMENT PRIMARY KEY,
            #     tweet_id INT,
            #     url VARCHAR(1024),
            #     link_type ENUM('external', 'mention', 'hashtag', 'media'),
            #     inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            #     FOREIGN KEY (tweet_id) REFERENCES tweets(id) ON DELETE CASCADE,
            #     INDEX idx_tweet_id (tweet_id),
            #     INDEX idx_link_type (link_type)
            # ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            # """)
            #
            # # Создаем таблицу для ссылок из статей (УДАЛЕНО)
            # cursor.execute("""
            # CREATE TABLE IF NOT EXISTS article_links (
            #     id INT AUTO_INCREMENT PRIMARY KEY,
            #     article_id INT,
            #     url VARCHAR(1024),
            #     inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            #     FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
            #     INDEX idx_article_id (article_id)
            # ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            # """)

            connection.commit()
            debug_print("База данных успешно инициализирована (таблицы users, tweets)")
            return connection

    except Error as e:
        print(f"Ошибка при подключении к MySQL: {e}")
        return None


def save_user_to_db(connection, username, name):
    """Сохраняет или обновляет пользователя в базе данных"""
    try:
        cursor = connection.cursor()

        # Проверяем, существует ли пользователь
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        result = cursor.fetchone()

        if result:
            # Обновляем имя, если пользователь существует
            user_id = result[0]
            cursor.execute("UPDATE users SET name = %s WHERE id = %s", (name, user_id))
        else:
            # Добавляем нового пользователя
            cursor.execute("INSERT INTO users (username, name) VALUES (%s, %s)", (username, name))
            user_id = cursor.lastrowid

        connection.commit()
        return user_id

    except Error as e:
        print(f"Ошибка при сохранении пользователя {username}: {e}")
        return None


def save_tweet_to_db(connection, user_id, tweet_data):
    """Сохраняет твит в базу данных (без изображений и ссылок)"""
    try:
        cursor = connection.cursor()

        # Проверяем, существует ли твит (по URL или ID)
        tweet_id = tweet_data.get("url", "").split("/")[-1] if tweet_data.get("url") else None

        if not tweet_id:
            print("Пропускаем твит без идентификатора")
            return None

        cursor.execute("SELECT id FROM tweets WHERE tweet_id = %s", (tweet_id,))
        result = cursor.fetchone()

        if result:
            # Твит уже существует
            tweet_db_id = result[0]
            # Обновляем статистику
            cursor.execute("""
                UPDATE tweets
                SET likes = %s, retweets = %s, replies = %s
                WHERE id = %s
                """,
                           (tweet_data.get("stats", {}).get("likes", 0),
                            tweet_data.get("stats", {}).get("retweets", 0),
                            tweet_data.get("stats", {}).get("replies", 0),
                            tweet_db_id))
        else:
            # Создаем новый твит
            created_at = parse_twitter_date(tweet_data.get("created_at", ""))
            created_at_str = created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else None

            cursor.execute("""
                INSERT INTO tweets
                (tweet_id, user_id, tweet_text, created_at, url, likes, retweets, replies, is_retweet, original_author)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                           (tweet_id,
                            user_id,
                            tweet_data.get("text", ""),
                            created_at_str,
                            tweet_data.get("url", ""),
                            tweet_data.get("stats", {}).get("likes", 0),
                            tweet_data.get("stats", {}).get("retweets", 0),
                            tweet_data.get("stats", {}).get("replies", 0),
                            tweet_data.get("is_retweet", False),
                            tweet_data.get("original_author", None)))

            tweet_db_id = cursor.lastrowid

        connection.commit()

        # --- Удалено сохранение изображений ---
        # # Сохраняем изображения
        # for image_path in tweet_data.get("images", []):
        #     save_image_to_db(connection, tweet_db_id, image_path)

        return tweet_db_id

    except Error as e:
        print(f"Ошибка при сохранении твита: {e}")
        return None

# --- Функция save_image_to_db удалена ---
# def save_image_to_db(connection, tweet_db_id, image_path, image_url=None):
#     """Сохраняет информацию об изображении в базу данных"""
#     # ... (код функции удален) ...


def parse_twitter_date(date_str):
    """
    Парсит дату из различных форматов Twitter
    Возвращает объект datetime с учетом часового пояса
    """
    if not date_str:
        return None

    # Пробуем различные форматы даты
    try:
        # Формат ISO с Z (UTC)
        if "Z" in date_str:
            return datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))

        # Формат ISO без Z
        if "T" in date_str and ('+' in date_str or '-' in date_str.split('T')[1]):
            return datetime.datetime.fromisoformat(date_str)

        # Стандартный формат Twitter "Wed Apr 23 15:24:13 +0000 2014"
        formats = [
            "%a %b %d %H:%M:%S %z %Y",  # Стандартный Twitter
            "%Y-%m-%d %H:%M:%S %z",  # Вариант ISO с пробелом
            "%Y-%m-%dT%H:%M:%S",  # ISO без часового пояса
            "%Y-%m-%d"  # Только дата
        ]

        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(date_str, fmt)
                # Если нет часового пояса, предполагаем UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                return dt
            except ValueError:
                continue
    except Exception as e:
        debug_print(f"Ошибка при парсинге даты '{date_str}': {e}")

    # Если не удалось распарсить дату, пытаемся интерпретировать её вручную
    try:
        # Самый распространённый формат Twitter для JavaScript: "2023-04-15T12:34:56.000Z"
        if "T" in date_str and "." in date_str and date_str.endswith("Z"):
            parts = date_str.split(".")
            date_without_ms = parts[0]
            dt = datetime.datetime.fromisoformat(date_without_ms)
            return dt.replace(tzinfo=datetime.timezone.utc)

        # Проверяем, является ли дата временной меткой Unix
        if date_str.isdigit():
            return datetime.datetime.fromtimestamp(int(date_str), tz=datetime.timezone.utc)
    except Exception as e:
        debug_print(f"Дополнительная ошибка при парсинге даты '{date_str}': {e}")

    # В случае неудачи, возвращаем текущее время
    now = datetime.datetime.now(datetime.timezone.utc)
    debug_print(f"Не удалось разобрать дату '{date_str}'. Используем текущее время.")
    return now


def filter_recent_tweets(tweets, hours=24):
    """Фильтрует твиты, оставляя только опубликованные за последние N часов"""
    if not tweets:
        return []

    current_time = datetime.datetime.now(datetime.timezone.utc)
    cutoff_time = current_time - datetime.timedelta(hours=hours)

    recent_tweets = []

    for tweet in tweets:
        if not tweet.get("created_at"):
            continue

        try:
            # Преобразуем строку даты в datetime объект
            tweet_time = parse_twitter_date(tweet["created_at"])

            if not tweet_time:
                continue

            # Проверяем, что твит опубликован в течение указанного периода
            if tweet_time >= cutoff_time:
                recent_tweets.append(tweet)
                debug_print(
                    f"Свежий твит: {tweet_time.isoformat()}, {(current_time - tweet_time).total_seconds() / 3600:.1f}ч назад")
            else:
                debug_print(
                    f"Старый твит: {tweet_time.isoformat()}, {(current_time - tweet_time).total_seconds() / 3600:.1f}ч назад")
        except Exception as e:
            debug_print(f"Ошибка при обработке даты твита: {e}")

    return recent_tweets


def format_time_ago(iso_time_str):
    """Форматирует время в человеко-читаемый вид (сколько времени прошло)"""
    try:
        if not iso_time_str:
            return "неизвестно"

        tweet_time = parse_twitter_date(iso_time_str)
        if not tweet_time:
            return iso_time_str

        now = datetime.datetime.now(datetime.timezone.utc)
        diff = now - tweet_time

        # Форматируем разницу во времени
        if diff.days > 0:
            return f"{diff.days} д. назад"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours} ч. назад"
        minutes = (diff.seconds % 3600) // 60
        if minutes > 0:
            return f"{minutes} мин. назад"
        return "только что"
    except Exception:
        # Если не удалось форматировать, возвращаем оригинальное время
        if iso_time_str and "T" in iso_time_str:
            return iso_time_str.split("T")[1][:8]
        return iso_time_str


def initialize_browser(chrome_profile_path=None):
    """Инициализирует и возвращает браузер Chrome"""
    # Настройка Selenium
    options = Options()
    options.add_argument("--window-size=1920,1080")

    # Если указан путь к профилю Chrome, используем его
    if chrome_profile_path:
        if os.path.exists(chrome_profile_path):
            options.add_argument(f"user-data-dir={chrome_profile_path}")
            print(f"Используется профиль Chrome: {chrome_profile_path}")
        else:
            print(f"ВНИМАНИЕ: Указанный профиль Chrome не найден: {chrome_profile_path}")
            print("Будет использован временный профиль")

    # Дополнительные настройки для стабильности
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")

    # Добавляем обход обнаружения автоматизации
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        driver = webdriver.Chrome(options=options)
        # Обход обнаружения Selenium
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.set_page_load_timeout(60)  # Увеличенный таймаут загрузки страницы

        # Дополнительные настройки для улучшения стабильности
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        return driver
    except Exception as e:
        print(f"Ошибка при инициализации браузера: {e}")
        return None


def manual_auth_with_prompt(driver):
    """Открывает страницу авторизации Twitter и ждет, пока пользователь не нажмет Enter в консоли"""
    try:
        print("\n=== АВТОРИЗАЦИЯ В TWITTER ===")
        print("Сейчас откроется страница входа в Twitter.")
        print("Пожалуйста, войдите в свой аккаунт, и после завершения авторизации нажмите Enter в этой консоли.")

        # Открываем страницу авторизации
        driver.get("https://twitter.com/login")

        # Ждем, пока пользователь нажмет Enter
        input("\nПосле завершения авторизации нажмите Enter для продолжения...")

        # Проверяем, авторизован ли пользователь
        if "Log in" in driver.page_source and "Sign up" in driver.page_source:
            print("ВНИМАНИЕ: Признаки авторизации не обнаружены. Продолжаем с текущим состоянием.")
            return False
        else:
            print("Признаки авторизации обнаружены. Продолжаем работу.")
            return True
    except Exception as e:
        print(f"Ошибка при авторизации: {e}")
        return False

# --- Функция download_image удалена ---
# def download_image(url, username):
#     """Скачивает изображение и сохраняет его в папку с изображениями"""
#     # ... (код функции удален) ...

# --- Функция extract_images_from_tweet удалена ---
# def extract_images_from_tweet(tweet_element, username):
#     """Извлекает изображения из твита и скачивает их"""
#     # ... (код функции удален) ...


def extract_retweet_info(tweet_element):
    """Улучшенная функция для извлечения информации о ретвите"""
    # Эта функция остается, так как она не связана с изображениями/ссылками/статьями
    result = {
        "is_retweet": False,
        "original_author": None
    }

    try:
        # Помечаем начало проверки для отладки
        debug_print("Начало проверки на ретвит...") # Используем debug_print

        # МЕТОД 1: Проверка по специфическим тегам для ретвитов
        retweet_indicators = [
            "retweeted", "reposted", "ретвитнул", "ретвитнула",
            "повторно опубликовал", "повторно опубликовала",
            "quote", "цитирует", "отметил", "отметила"
        ]

        try:
            social_context = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"]')
            if social_context:
                context_text = social_context[0].text.lower()
                debug_print(f"Найден socialContext: '{context_text}'") # Используем debug_print

                for indicator in retweet_indicators:
                    if indicator.lower() in context_text:
                        debug_print(f"Найден индикатор ретвита: '{indicator}'") # Используем debug_print
                        result["is_retweet"] = True
                        break
        except Exception as e:
            debug_print(f"Ошибка при проверке socialContext: {e}") # Используем debug_print

        # МЕТОД 2: Поиск иконки ретвита
        if not result["is_retweet"]:
            try:
                retweet_icon = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"] svg')
                if retweet_icon:
                    debug_print("Найдена иконка в socialContext") # Используем debug_print
                    result["is_retweet"] = True
            except Exception as e:
                debug_print(f"Ошибка при поиске иконки ретвита: {e}") # Используем debug_print

        # МЕТОД 3: Проверка на наличие двух разных имен пользователей в твите
        if not result["is_retweet"]:
            try:
                user_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[role="link"][href*="/"]')
                usernames = set()

                for link in user_links:
                    href = link.get_attribute('href')
                    if href and '/status/' not in href:
                        username = href.split('/')[-1]
                        if username and len(username) > 1:
                            usernames.add(username)

                debug_print(f"Найдено уникальных имен пользователей: {len(usernames)}") # Используем debug_print
                if len(usernames) >= 2:
                    debug_print("Обнаружено несколько имен пользователей, возможно это ретвит") # Используем debug_print
                    result["is_retweet"] = True
            except Exception as e:
                debug_print(f"Ошибка при проверке нескольких имен пользователей: {e}") # Используем debug_print

        # Если определили, что это ретвит, ищем оригинального автора
        if result["is_retweet"]:
            try:
                # МЕТОД 1: Поиск автора через socialContext
                social_context_links = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"] a')
                if social_context_links:
                    for link in social_context_links:
                        href = link.get_attribute('href')
                        if href and '/status/' not in href:
                            original_author = href.split('/')[-1]
                            debug_print(f"Найден оригинальный автор через socialContext: {original_author}") # Используем debug_print
                            result["original_author"] = original_author
                            break

                # МЕТОД 2: Поиск по User-Name элементам
                if not result["original_author"]:
                    user_name_elements = tweet_element.find_elements(By.CSS_SELECTOR,
                                                                     '[data-testid="User-Name"] a[role="link"]')
                    if len(user_name_elements) >= 2:
                        href = user_name_elements[1].get_attribute('href')
                        if href and '/status/' not in href:
                            original_author = href.split('/')[-1]
                            debug_print(f"Найден оригинальный автор через User-Name: {original_author}") # Используем debug_print
                            result["original_author"] = original_author

                # МЕТОД 3: Поиск имен пользователей в порядке появления
                if not result["original_author"]:
                    user_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[role="link"][href*="/"]')
                    usernames = []

                    for link in user_links:
                        href = link.get_attribute('href')
                        if href and '/status/' not in href:
                            username = href.split('/')[-1]
                            if username and len(username) > 1 and username not in usernames:
                                usernames.append(username)

                    debug_print(f"Найдено имен пользователей в порядке: {usernames}") # Используем debug_print
                    if len(usernames) >= 2:
                        result["original_author"] = usernames[1]
                        debug_print(f"Использовано второе имя как оригинальный автор: {result['original_author']}") # Используем debug_print
            except Exception as e:
                debug_print(f"Ошибка при поиске оригинального автора: {e}") # Используем debug_print

        debug_print(f"Результат определения ретвита: {result}") # Используем debug_print
        return result

    except Exception as e:
        debug_print(f"Общая ошибка при определении ретвита: {e}") # Используем debug_print
        return result


def extract_tweet_stats(tweet_element):
    """Извлекает статистику твита (лайки, ретвиты, ответы)"""
    # Эта функция остается, так как она не связана с изображениями/ссылками/статьями
    stats = {"likes": 0, "retweets": 0, "replies": 0}

    # МЕТОД 0: "Старая надежная" техника извлечения replies
    try:
        reply_elements = tweet_element.find_elements(By.CSS_SELECTOR, 'div[data-testid="reply"]')
        debug_print(f"Найдено элементов reply: {len(reply_elements)}") # Используем debug_print

        for reply_el in reply_elements:
            all_text = reply_el.text
            debug_print(f"Текст элемента reply: '{all_text}'") # Используем debug_print

            numbers = re.findall(r'\d+', all_text)
            if numbers:
                stats["replies"] = int(numbers[0])
                debug_print(f"МЕТОД 0: Извлечено replies: {stats['replies']}") # Используем debug_print
    except Exception as e:
        debug_print(f"Ошибка в методе 0: {e}") # Используем debug_print

    # МЕТОД 1: Прямой поиск по data-testid
    for stat_type, stat_key in [("reply", "replies"), ("retweet", "retweets"), ("like", "likes")]:
        try:
            selector = f'div[data-testid="{stat_type}"]'
            elements = tweet_element.find_elements(By.CSS_SELECTOR, selector)
            debug_print(f"Найдено {len(elements)} элементов с селектором '{selector}'") # Используем debug_print

            for element in elements:
                full_text = element.text
                debug_print(f"Текст элемента {stat_type}: '{full_text}'") # Используем debug_print

                if full_text:
                    numbers = re.findall(r'(\d+)', full_text)
                    if numbers:
                        value = int(numbers[0])
                        stats[stat_key] = value
                        debug_print(f"МЕТОД 1: Извлечено {stat_key}: {value}") # Используем debug_print
                        continue

                spans = element.find_elements(By.TAG_NAME, 'span')
                for span in spans:
                    text = span.text.strip()
                    if text and re.search(r'\d', text):
                        numbers = re.findall(r'(\d+)', text)
                        if numbers:
                            value = int(numbers[0])
                            stats[stat_key] = value
                            debug_print(f"МЕТОД 1 (spans): Извлечено {stat_key}: {value}") # Используем debug_print
                            break
        except Exception as e:
            debug_print(f"Ошибка при извлечении {stat_type}: {e}") # Используем debug_print

    # МЕТОД 2: Поиск в aria-label
    try:
        buttons = tweet_element.find_elements(By.CSS_SELECTOR, 'div[role="button"][aria-label]')
        debug_print(f"Найдено {len(buttons)} кнопок с aria-label") # Используем debug_print

        for button in buttons:
            try:
                aria_label = button.get_attribute('aria-label')
                if not aria_label:
                    continue

                debug_print(f"Проверяем aria-label: '{aria_label}'") # Используем debug_print

                numbers = re.findall(r'(\d+)', aria_label)
                if not numbers:
                    continue

                value = int(numbers[0])

                if re.search(r'repl|comment|ответ', aria_label.lower()):
                    stats["replies"] = value
                    debug_print(f"МЕТОД 2: Извлечено replies: {value}") # Используем debug_print
                elif re.search(r'retweet|ретвит|repost', aria_label.lower()):
                    stats["retweets"] = value
                    debug_print(f"МЕТОД 2: Извлечено retweets: {value}") # Используем debug_print
                elif re.search(r'like|нрав|лайк', aria_label.lower()):
                    stats["likes"] = value
                    debug_print(f"МЕТОД 2: Извлечено likes: {value}") # Используем debug_print
            except Exception as e:
                debug_print(f"Ошибка при обработке кнопки: {e}") # Используем debug_print
    except Exception as e:
        debug_print(f"Ошибка в методе 2: {e}") # Используем debug_print

    # МЕТОД 3: Поиск по порядку расположения кнопок в группе
    try:
        groups = tweet_element.find_elements(By.CSS_SELECTOR, 'div[role="group"]')
        for group in groups:
            buttons = group.find_elements(By.CSS_SELECTOR, 'div[role="button"]')
            debug_print(f"Найдено {len(buttons)} кнопок в группе") # Используем debug_print

            for i, button in enumerate(buttons):
                text_elements = button.find_elements(By.TAG_NAME, 'span')
                for elem in text_elements:
                    text = elem.text.strip()
                    debug_print(f"Текст в кнопке {i}: '{text}'") # Используем debug_print

                    if text and text.isdigit():
                        value = int(text)
                        if i == 0 and stats["replies"] == 0:
                            stats["replies"] = value
                            debug_print(f"МЕТОД 3: Извлечено replies по позиции: {value}") # Используем debug_print
                        elif i == 1 and stats["retweets"] == 0:
                            stats["retweets"] = value
                            debug_print(f"МЕТОД 3: Извлечено retweets по позиции: {value}") # Используем debug_print
                        elif i == 2 and stats["likes"] == 0:
                            stats["likes"] = value
                            debug_print(f"МЕТОД 3: Извлечено likes по позиции: {value}") # Используем debug_print
                        break
    except Exception as e:
        debug_print(f"Ошибка в методе 3: {e}") # Используем debug_print

    # МЕТОД 4: Изучение всех span-элементов в твите
    try:
        all_spans = tweet_element.find_elements(By.TAG_NAME, 'span')
        number_spans = []

        for span in all_spans:
            text = span.text.strip()
            if text and text.isdigit():
                number_spans.append((span, int(text)))
                debug_print(f"Найден span с числом: {text}") # Используем debug_print

        if len(number_spans) >= 3 and stats["replies"] == 0:
            y_positions = []
            for span, value in number_spans:
                rect = span.rect
                y_positions.append((span, value, rect['y']))

            y_positions.sort(key=lambda x: x[2])

            if stats["replies"] == 0:
                stats["replies"] = y_positions[0][1]
                debug_print(f"МЕТОД 4: Извлечено replies по Y-позиции: {stats['replies']}") # Используем debug_print

            if stats["retweets"] == 0 and len(y_positions) > 1:
                stats["retweets"] = y_positions[1][1]
                debug_print(f"МЕТОД 4: Извлечено retweets по Y-позиции: {stats['retweets']}") # Используем debug_print

            if stats["likes"] == 0 and len(y_positions) > 2:
                stats["likes"] = y_positions[2][1]
                debug_print(f"МЕТОД 4: Извлечено likes по Y-позиции: {stats['likes']}") # Используем debug_print
    except Exception as e:
        debug_print(f"Ошибка в методе 4: {e}") # Используем debug_print

    debug_print(f"Итоговая статистика твита: {stats}") # Используем debug_print
    return stats
