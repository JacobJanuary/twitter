#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
# Добавляем импорты для WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os
import datetime
import re
import mysql.connector
from mysql.connector import Error, errorcode # Импортируем errorcode для обработки ошибок MySQL
import html # Для декодирования HTML сущностей в API

# Глобальная настройка отладки
DEBUG = True

# Директории для хранения данных
CACHE_DIR = "twitter_cache"
os.makedirs(CACHE_DIR, exist_ok=True)


def debug_print(*args, **kwargs):
    """Функция для вывода отладочной информации"""
    if DEBUG:
        safe_args = [repr(a) if isinstance(a, str) else a for a in args]
        print("[ОТЛАДКА]", *safe_args, **kwargs)


def initialize_mysql(config):
    """Инициализирует подключение к MySQL и создает таблицы users и tweets"""
    # (Без изменений по сравнению с v5)
    try:
        connection = mysql.connector.connect(**config)
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                name VARCHAR(255),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tweets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tweet_id VARCHAR(255) UNIQUE,          -- ID оригинального твита (если ретвит) или твита
                user_id INT,                           -- ID пользователя, который сделал ретвит (или автора твита)
                tweet_text TEXT,                       -- Текст оригинального твита (если ретвит) или твита
                created_at DATETIME,                   -- Дата создания оригинального твита (если ретвит) или твита
                url VARCHAR(255),                      -- URL оригинального твита (если ретвит) или твита
                likes INT DEFAULT 0,                   -- Статистика оригинального твита (если ретвит) или твита
                retweets INT DEFAULT 0,                -- Статистика оригинального твита (если ретвит) или твита
                replies INT DEFAULT 0,                 -- Статистика оригинального твита (если ретвит) или твита
                is_retweet BOOLEAN DEFAULT FALSE,      -- Флаг, указывающий, что это ретвит
                original_author VARCHAR(255),          -- Имя пользователя автора оригинального твита (если ретвит)
                inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_created_at (created_at),
                INDEX idx_user_id (user_id),
                INDEX idx_original_author (original_author)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)
            connection.commit()
            debug_print("База данных успешно инициализирована (таблицы users, tweets)")
            return connection
    except Error as e:
        print(f"Ошибка при подключении к MySQL: {e}")
        return None


def save_user_to_db(connection, username, name):
    """Сохраняет или обновляет пользователя в базе данных"""
    # (Без изменений)
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        result = cursor.fetchone()
        user_id = None
        if result:
            user_id = result[0]
            cursor.execute("UPDATE users SET name = COALESCE(%s, name) WHERE id = %s", (name, user_id))
        else:
            cursor.execute("INSERT INTO users (username, name) VALUES (%s, %s)", (username, name))
            user_id = cursor.lastrowid
        connection.commit()
        return user_id
    except Error as e:
        print(f"Ошибка при сохранении пользователя {username}: {e}")
        return None


def save_tweet_to_db(connection, user_id, tweet_data):
    """
    Сохраняет твит или ретвит в базу данных.
    Использует ID твита (оригинала для ретвитов) как ключ `tweet_id`.
    Сохраняет URL твита (оригинала для ретвитов) в колонку `url`.
    Обновляет статистику, если запись с таким ID уже существует.
    """
    if not connection or not connection.is_connected():
         print("Ошибка: Нет подключения к БД для сохранения твита.")
         return None

    try:
        cursor = connection.cursor(dictionary=True)

        # ID для сохранения и проверки (ID оригинала для ретвитов, ID твита для обычных)
        id_to_check = tweet_data.get("tweet_id")
        # URL для сохранения (URL оригинала для ретвитов, URL твита для обычных)
        url_to_save = tweet_data.get("url")

        if not id_to_check or not url_to_save:
            # Используем URL ретвита для логгирования, если основной URL не найден
            log_url = tweet_data.get("retweet_url_for_log", tweet_data.get("url", "N/A"))
            print(f"Ошибка: Не удалось определить ID или URL для сохранения твита/ретвита URL: {log_url}")
            logger.error(f"Missing ID ({id_to_check}) or URL ({url_to_save}) for tweet/retweet: {log_url}")
            return None

        # Ищем существующую запись по ID
        cursor.execute("SELECT id, likes, retweets, replies FROM tweets WHERE tweet_id = %s", (id_to_check,))
        existing_tweet = cursor.fetchone()

        # Данные для вставки/обновления
        stats = tweet_data.get("stats", {})
        likes_val = stats.get("likes", 0)
        retweets_val = stats.get("retweets", 0)
        replies_val = stats.get("replies", 0)
        created_at = parse_twitter_date(tweet_data.get("created_at", ""))
        created_at_str = created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else None
        tweet_text_str = tweet_data.get("text", "") or ""
        original_author_str = tweet_data.get("original_author", "") or ""
        is_retweet_flag = tweet_data.get("is_retweet", False)
        # user_id - это ID пользователя, который сделал ретвит или автора твита

        if existing_tweet:
            # Запись существует - обновляем статистику
            tweet_db_id = existing_tweet['id']
            existing_stats = {'likes': existing_tweet['likes'], 'retweets': existing_tweet['retweets'], 'replies': existing_tweet['replies']}
            debug_print(f"Запись для tweet_id {id_to_check} уже существует (DB ID: {tweet_db_id}). Обновляем статистику.")

            update_query = "UPDATE tweets SET "
            update_params = []
            fields_to_update = []

            if likes_val > existing_stats.get('likes', 0): fields_to_update.append("likes = %s"); update_params.append(likes_val)
            if retweets_val > existing_stats.get('retweets', 0): fields_to_update.append("retweets = %s"); update_params.append(retweets_val)
            if replies_val > existing_stats.get('replies', 0): fields_to_update.append("replies = %s"); update_params.append(replies_val)

            # Можно добавить обновление user_id, если ретвит того же твита сделал другой наш пользователь
            # fields_to_update.append("user_id = %s"); update_params.append(user_id)
            # Но пока обновляем только статистику

            if fields_to_update:
                 update_query += ", ".join(fields_to_update)
                 update_query += " WHERE id = %s"
                 update_params.append(tweet_db_id)
                 cursor.execute(update_query, tuple(update_params))
                 debug_print(f"Статистика для tweet_id {id_to_check} обновлена.")
            # else: debug_print(f"Статистика для tweet_id {id_to_check} не требует обновления.")

        else:
            # Новая запись - вставляем
            debug_print(f"Создаем новую запись для tweet_id {id_to_check}")
            insert_query = """
                INSERT INTO tweets
                (tweet_id, user_id, tweet_text, created_at, url,
                 likes, retweets, replies,
                 is_retweet, original_author)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            insert_params = (
                id_to_check,            # ID оригинала (если ретвит) или твита
                user_id,                # ID пользователя, кто ретвитнул или автора
                tweet_text_str,         # Текст оригинала или твита
                created_at_str,         # Дата оригинала или твита
                url_to_save,            # URL оригинала (если ретвит) или твита
                likes_val,              # Статистика оригинала или твита
                retweets_val,
                replies_val,
                is_retweet_flag,        # Флаг ретвита
                original_author_str     # Автор оригинала (пусто, если не ретвит)
            )
            try:
                cursor.execute(insert_query, insert_params)
                tweet_db_id = cursor.lastrowid
                debug_print(f"Создана новая запись (DB ID: {tweet_db_id})")
            except mysql.connector.Error as err:
                 if err.errno == errorcode.ER_DUP_ENTRY:
                      print(f"Предупреждение: Попытка вставить дубликат tweet_id {id_to_check}. Запись уже существует (возможно, найдена другим пользователем).")
                      logger.warning(f"Duplicate entry for tweet_id {id_to_check}. Record likely exists.")
                      tweet_db_id = None # Не удалось вставить
                 else:
                      print(f"Ошибка MySQL при INSERT твита (ID: {id_to_check}): {err}")
                      logger.error(f"MySQL Error on INSERT tweet_id {id_to_check}: {err}")
                      raise err

        connection.commit()
        return tweet_db_id

    except Error as e:
        log_url = tweet_data.get("retweet_url_for_log", tweet_data.get("url", "N/A"))
        print(f"Ошибка MySQL при сохранении твита (ID для проверки: {id_to_check}, URL: {log_url}): {e}")
        logger.error(f"MySQL Error saving tweet_id {id_to_check} (URL: {log_url}): {e}")
        try:
            if connection.is_connected() and connection.in_transaction: connection.rollback()
        except Exception as rb_err: print(f"Ошибка при откате транзакции: {rb_err}")
        return None
    except Exception as e:
        log_url = tweet_data.get("retweet_url_for_log", tweet_data.get("url", "N/A"))
        print(f"Неожиданная ошибка при сохранении твита (ID для проверки: {id_to_check}, URL: {log_url}): {e}")
        logger.error(f"Unexpected error saving tweet_id {id_to_check} (URL: {log_url}): {e}")
        import traceback; logger.error(traceback.format_exc())
        return None
    finally:
         if 'cursor' in locals() and cursor:
              try: cursor.close()
              except: pass


def parse_twitter_date(date_str):
    """Парсит дату из различных форматов Twitter"""
    # (Без изменений)
    if not date_str: return None
    try:
        if "Z" in date_str: return datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if "T" in date_str and ('+' in date_str or '-' in date_str.split('T')[1]): return datetime.datetime.fromisoformat(date_str)
        formats = ["%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(date_str, fmt)
                if dt.tzinfo is None: dt = dt.replace(tzinfo=datetime.timezone.utc)
                return dt
            except ValueError: continue
    except Exception as e: debug_print(f"Ошибка парсинга даты '{date_str}': {e}")
    try:
        if "T" in date_str and "." in date_str and date_str.endswith("Z"): dt = datetime.datetime.fromisoformat(date_str.split(".")[0]); return dt.replace(tzinfo=datetime.timezone.utc)
        if date_str.isdigit(): return datetime.datetime.fromtimestamp(int(date_str), tz=datetime.timezone.utc)
    except Exception as e: debug_print(f"Доп. ошибка парсинга даты '{date_str}': {e}")
    now = datetime.datetime.now(datetime.timezone.utc); debug_print(f"Не удалось разобрать дату '{date_str}'. Используем текущее время."); return now


def filter_recent_tweets(tweets, hours=24):
    """Фильтрует твиты, оставляя только опубликованные за последние N часов"""
    # (Без изменений)
    if not tweets: return []
    current_time = datetime.datetime.now(datetime.timezone.utc); cutoff_time = current_time - datetime.timedelta(hours=hours)
    recent_tweets = []
    for tweet in tweets:
        if not tweet or not tweet.get("created_at"): continue
        try:
            tweet_time = parse_twitter_date(tweet["created_at"])
            if not tweet_time: continue
            if tweet_time.tzinfo is None: tweet_time = tweet_time.replace(tzinfo=datetime.timezone.utc)
            if tweet_time >= cutoff_time: recent_tweets.append(tweet)
        except Exception as e: debug_print(f"Ошибка обработки даты твита {tweet.get('url', '')}: {e}")
    return recent_tweets


def format_time_ago(iso_time_str):
    """Форматирует время в человеко-читаемый вид"""
    # (Без изменений)
    try:
        if not iso_time_str: return "неизвестно"
        tweet_time = parse_twitter_date(iso_time_str)
        if not tweet_time: return iso_time_str
        if tweet_time.tzinfo is None: tweet_time = tweet_time.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc); diff = now - tweet_time
        if diff.days > 0: return f"{diff.days} д. назад"
        hours = diff.seconds // 3600; minutes = (diff.seconds % 3600) // 60
        if hours > 0: return f"{hours} ч. назад"
        if minutes > 0: return f"{minutes} мин. назад"
        return "только что"
    except Exception:
        if iso_time_str and "T" in iso_time_str: return iso_time_str.split("T")[1][:8]
        return iso_time_str


def initialize_browser(chrome_profile_path=None):
    """Инициализирует и возвращает браузер Chrome"""
    # (Без изменений)
    options = Options(); options.add_argument("--window-size=1920,1080")
    if chrome_profile_path:
        if os.path.exists(chrome_profile_path): options.add_argument(f"user-data-dir={chrome_profile_path}"); print(f"Используется профиль Chrome: {chrome_profile_path}")
        else: print(f"ВНИМАНИЕ: Профиль Chrome не найден: {chrome_profile_path}. Будет использован временный."); chrome_profile_path = None
    options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage"); options.add_argument("--disable-gpu"); options.add_argument("--disable-extensions")
    options.add_argument("--disable-blink-features=AutomationControlled"); options.add_experimental_option("excludeSwitches", ["enable-automation"]); options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--log-level=3"); options.add_argument("--silent")
    try:
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.set_page_load_timeout(60)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'})
        return driver
    except Exception as e:
        print(f"Ошибка инициализации браузера: {e}\nУбедитесь, что ChromeDriver установлен и совместим с Chrome."); return None


def manual_auth_with_prompt(driver):
    """Открывает страницу авторизации Twitter и ждет подтверждения пользователя"""
    # (Без изменений)
    try:
        print("\n=== АВТОРИЗАЦИЯ В TWITTER ==="); print("Открывается страница входа..."); print("Войдите в аккаунт и нажмите Enter в консоли.")
        driver.get("https://twitter.com/login")
        input("\nПосле завершения авторизации нажмите Enter для продолжения...")
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="primaryColumn"]')))
            print("Признаки авторизации обнаружены. Продолжаем.")
            return True
        except TimeoutException:
            print("ВНИМАНИЕ: Не удалось подтвердить авторизацию (не найден контент ленты).")
            cont = input("Продолжить несмотря на возможную ошибку авторизации? (да/нет): ")
            return cont.lower() in ['да', 'yes', 'y', 'д']
    except Exception as e: print(f"Ошибка при авторизации: {e}"); return False


def extract_retweet_info(tweet_element):
    """Базовая функция для извлечения информации о ретвите (остается как резерв)"""
    # (Без изменений)
    result = {"is_retweet": False, "original_author": None, "original_tweet_url": None}
    try:
        social_context = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"]')
        if social_context:
            context_text = social_context[0].text.lower()
            if any(term in context_text for term in ["retweeted", "reposted", "ретвитнул"]):
                result["is_retweet"] = True
                mentions = re.findall(r'@(\w+)', social_context[0].text);
                if mentions: result["original_author"] = mentions[0]
                try:
                     links = social_context[0].find_elements(By.TAG_NAME, 'a')
                     for link in links:
                          href = link.get_attribute('href')
                          if href and '/status/' in href: result["original_tweet_url"] = href.split("?")[0]; break
                except: pass
        if not result["is_retweet"]:
            try:
                 if tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="retweet"] svg'): result["is_retweet"] = True
            except (NoSuchElementException, StaleElementReferenceException): pass
        if result["is_retweet"] and (not result["original_author"] or not result["original_tweet_url"]):
             result["is_retweet"] = False; result["original_author"] = None; result["original_tweet_url"] = None
    except Exception as e: debug_print(f"Ошибка при базовой проверке ретвита: {e}")
    return result


def extract_tweet_stats(tweet_element):
    """Извлекает статистику твита (лайки, ретвиты, ответы)"""
    # (Без изменений)
    stats = {"likes": 0, "retweets": 0, "replies": 0}; processed_values = set()
    def parse_stat_value(text):
        text = text.upper().replace(',', ''); value_str = re.sub(r'[^\d.]', '', text)
        if not value_str: return 0
        try:
            value = float(value_str)
            if 'K' in text: value *= 1000
            elif 'M' in text: value *= 1000000
            return int(value)
        except ValueError: return 0
    try:
        buttons = tweet_element.find_elements(By.CSS_SELECTOR, 'div[role="button"][data-testid]')
        for button in buttons:
            try:
                aria_label = button.get_attribute('aria-label'); test_id = button.get_attribute('data-testid')
                if not aria_label and not test_id: continue
                text_content = button.text; value = 0
                numbers_aria = re.findall(r'([\d.,]+)\s*(?:K|M)?', aria_label or "")
                if numbers_aria: value = parse_stat_value(numbers_aria[0] + ('K' if 'K' in (aria_label or "").upper() else '') + ('M' if 'M' in (aria_label or "").upper() else ''))
                elif text_content: value = parse_stat_value(text_content)
                if value > 0:
                     stat_key = None; label_lower = (aria_label or "").lower(); testid_lower = (test_id or "").lower()
                     if "reply" in testid_lower or "ответ" in label_lower or "comment" in label_lower: stat_key = "replies"
                     elif "retweet" in testid_lower or "ретвит" in label_lower or "repost" in label_lower: stat_key = "retweets"
                     elif "like" in testid_lower or "нрав" in label_lower or "лайк" in label_lower: stat_key = "likes"
                     if stat_key and (stat_key, value) not in processed_values: stats[stat_key] = max(stats[stat_key], value); processed_values.add((stat_key, value))
            except StaleElementReferenceException: continue
            except Exception as e: debug_print(f"Ошибка обработки кнопки статистики: {e}")
    except Exception as e: debug_print(f"Ошибка поиска кнопок статистики: {e}")
    return stats
