#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os
import datetime
import re
import mysql.connector
from mysql.connector import Error, errorcode
import html
import logging

# Настройка логирования
logger = logging.getLogger('twitter_scraper.utils')
if not logger.handlers:
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Глобальная настройка отладки
DEBUG = True

# Директории для хранения данных
CACHE_DIR = "twitter_cache"
os.makedirs(CACHE_DIR, exist_ok=True)


def debug_print(*args, **kwargs):
    """Функция для вывода отладочной информации, если DEBUG=True."""
    if DEBUG:
        safe_args = [repr(a) if isinstance(a, str) else str(a) for a in args]
        safe_kwargs = {k: repr(v) if isinstance(v, str) else str(v) for k, v in kwargs.items()}
        try:
            print("[ОТЛАДКА]", *safe_args, **safe_kwargs)
        except Exception as e:
            print(f"[ОТЛАДКА ОШИБКА ВЫВОДА]: {e}")
            try: print("[ОТЛАДКА RAW]", args, kwargs)
            except Exception: print("[ОТЛАДКА RAW] Не удалось вывести необработанные данные.")


def initialize_mysql(config):
    """Инициализирует подключение к MySQL и создает/обновляет таблицы."""
    # (Код без изменений)
    try:
        connection = mysql.connector.connect(**config)
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            logger.info("Проверка/создание таблицы 'users'...")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                name VARCHAR(255),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)
            logger.info("Таблица 'users' проверена/создана.")
            logger.info("Проверка/обновление/создание таблицы 'tweets'...")
            try:
                cursor.execute("DESCRIBE tweets")
                existing_columns_info = cursor.fetchall(); existing_columns = {col['Field'] for col in existing_columns_info}; schema_changed = False
                columns_to_add = {
                    'original_tweet_text': "TEXT COLLATE utf8mb4_unicode_ci AFTER inserted_at",
                    'good': "TINYINT(1) DEFAULT NULL AFTER original_tweet_text",
                    'bad': "TINYINT(1) DEFAULT NULL AFTER good",
                    'isChecked': "TINYINT(1) DEFAULT NULL AFTER bad"
                }
                for col_name, col_def in columns_to_add.items():
                    if col_name not in existing_columns:
                        try: cursor.execute(f"ALTER TABLE tweets ADD COLUMN {col_name} {col_def}"); logger.info(f"Добавлена колонка '{col_name}'."); schema_changed = True
                        except Error as alter_err: logger.error(f"Ошибка добавления колонки {col_name}: {alter_err}")
                cursor.execute("SHOW INDEX FROM tweets WHERE Key_name = 'idx_original_author'")
                if not cursor.fetchone():
                     try: cursor.execute("ALTER TABLE tweets ADD INDEX idx_original_author (original_author)"); logger.info("Добавлен индекс 'idx_original_author'."); schema_changed = True
                     except Error as index_err: logger.error(f"Ошибка добавления индекса idx_original_author: {index_err}")
                if schema_changed: connection.commit(); logger.info("Схема таблицы 'tweets' обновлена.")
            except mysql.connector.Error as e:
                if e.errno == errorcode.ER_NO_SUCH_TABLE:
                    logger.info("Таблица 'tweets' не найдена, создаем новую.")
                    cursor.execute("""
                    CREATE TABLE tweets (
                        id INT AUTO_INCREMENT PRIMARY KEY, tweet_id VARCHAR(255) UNIQUE, user_id INT,
                        tweet_text TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci, created_at DATETIME, url VARCHAR(255),
                        likes INT DEFAULT 0, retweets INT DEFAULT 0, replies INT DEFAULT 0, is_retweet BOOLEAN DEFAULT FALSE,
                        original_author VARCHAR(255), inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        original_tweet_text TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
                        good TINYINT(1) DEFAULT NULL, bad TINYINT(1) DEFAULT NULL, isChecked TINYINT(1) DEFAULT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, INDEX idx_created_at (created_at),
                        INDEX idx_user_id (user_id), INDEX idx_original_author (original_author)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;""")
                    logger.info("Таблица 'tweets' создана."); connection.commit()
                else: logger.error(f"Ошибка проверки/создания таблицы tweets: {e}"); raise e
            finally:
                 if cursor: cursor.close()
            logger.info("База данных успешно инициализирована.")
            return connection
    except Error as e: logger.error(f"Ошибка подключения/инициализации MySQL: {e}"); return None


def save_user_to_db(connection, username, name):
    """Сохраняет или обновляет пользователя в базе данных. НЕ ДЕЛАЕТ COMMIT."""
    # (Код без изменений)
    if not connection or not connection.is_connected(): logger.error("Нет подключения к БД для сохранения пользователя."); return None
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        insert_query = """
            INSERT INTO users (username, name) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE name = COALESCE(VALUES(name), name), last_updated = CURRENT_TIMESTAMP
        """
        cursor.execute(insert_query, (username, name))
        user_id = cursor.lastrowid
        if user_id == 0:
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            result = cursor.fetchone()
            if result: user_id = result['id']
            else: logger.error(f"Не удалось получить ID для {username} после ON DUPLICATE KEY UPDATE"); return None
        debug_print(f"Пользователь @{username} подготовлен (ID: {user_id}). Commit будет позже.")
        return user_id
    except Error as e: logger.error(f"Ошибка сохранения пользователя {username}: {e}"); return None
    finally:
         if cursor:
             try: cursor.close()
             except: pass


def save_tweets_batch_to_db(connection, list_of_tweets):
    """Сохраняет пакет твитов в базу данных. НЕ ДЕЛАЕТ COMMIT."""
    # (Код без изменений)
    if not connection or not connection.is_connected(): logger.error("Нет подключения к БД для пакетного сохранения."); return None
    if not list_of_tweets: logger.info("Нет твитов для пакетного сохранения."); return 0
    cursor = None; prepared_data = []; processed_count = 0
    try:
        cursor = connection.cursor()
        logger.info(f"Подготовка {len(list_of_tweets)} твитов для пакетной вставки/обновления...")
        for tweet_data in list_of_tweets:
            db_user_id = tweet_data.get('retweeting_user_id') if tweet_data.get('is_retweet') else tweet_data.get('author_user_id')
            tweet_id_val = tweet_data.get("tweet_id")
            if not tweet_id_val: logger.warning(f"Пропуск твита без tweet_id в пакете. URL: {tweet_data.get('url', 'N/A')}"); continue
            stats = tweet_data.get("stats", {}); created_at = parse_twitter_date(tweet_data.get("created_at", ""))
            created_at_str = created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else None
            tweet_text_str = tweet_data.get("text", "") or ""; original_author_str = tweet_data.get("original_author")
            is_retweet_flag = tweet_data.get("is_retweet", False); url_to_save = tweet_data.get("url")
            prepared_data.append((
                tweet_id_val, db_user_id, tweet_text_str, created_at_str, url_to_save,
                stats.get("likes", 0), stats.get("retweets", 0), stats.get("replies", 0),
                is_retweet_flag, original_author_str
            ))
        if not prepared_data: logger.warning("После подготовки не осталось данных для пакетной вставки."); return 0
        sql = """
            INSERT INTO tweets (
                tweet_id, user_id, tweet_text, created_at, url,
                likes, retweets, replies, is_retweet, original_author
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                likes = GREATEST(likes, VALUES(likes)),
                retweets = GREATEST(retweets, VALUES(retweets)),
                replies = GREATEST(replies, VALUES(replies))
        """
        logger.info(f"Выполнение executemany для {len(prepared_data)} записей...")
        start_time = time.time()
        cursor.executemany(sql, prepared_data)
        end_time = time.time()
        processed_count = cursor.rowcount
        logger.info(f"Executemany завершен за {end_time - start_time:.2f} сек. Затронуто строк: {processed_count}")
        return processed_count
    except Error as e: logger.error(f"Ошибка MySQL при пакетном сохранении: {e}"); return None
    except Exception as e: logger.error(f"Неожиданная ошибка при пакетном сохранении: {e}"); import traceback; logger.error(traceback.format_exc()); return None
    finally:
         if cursor:
              try: cursor.close()
              except Exception as cur_close_err: logger.warning(f"Не удалось закрыть курсор: {cur_close_err}")


# --- ИСПРАВЛЕННАЯ ФУНКЦИЯ ---
def parse_twitter_date(date_str):
    """Парсит дату из различных форматов Twitter"""
    if not date_str: return None
    parsed_dt = None
    try: # Внешний try для общих ошибок парсинга
        # Попытка 1: Стандартный ISO формат с Z
        if isinstance(date_str, str) and "Z" in date_str and "T" in date_str:
            try:
                parsed_dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                # --- ИСПРАВЛЕНИЕ: Отделяем проверку и return ---
                if parsed_dt.tzinfo is None or parsed_dt.tzinfo.utcoffset(parsed_dt) != datetime.timedelta(0):
                     parsed_dt = parsed_dt.replace(tzinfo=datetime.timezone.utc)
                return parsed_dt
                # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
            except ValueError: pass

        # Попытка 2: Стандартный ISO формат с T и смещением
        if isinstance(date_str, str) and "T" in date_str and ('+' in date_str.split('T')[1] or '-' in date_str.split('T')[1]):
            try:
                parsed_dt = datetime.datetime.fromisoformat(date_str)
                # --- ИСПРАВЛЕНИЕ: Отделяем проверку и return ---
                if parsed_dt.tzinfo is None:
                     parsed_dt = parsed_dt.replace(tzinfo=datetime.timezone.utc)
                elif parsed_dt.tzinfo.utcoffset(parsed_dt) != datetime.timedelta(0):
                     parsed_dt = parsed_dt.astimezone(datetime.timezone.utc)
                return parsed_dt
                # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
            except ValueError: pass

        # Попытка 3: Формат из старого API Twitter
        if isinstance(date_str, str):
             fmt_api = "%a %b %d %H:%M:%S %z %Y"
             try:
                 parsed_dt = datetime.datetime.strptime(date_str, fmt_api)
                 # --- ИСПРАВЛЕНИЕ: Отделяем проверку и return ---
                 if parsed_dt.tzinfo is None or parsed_dt.tzinfo.utcoffset(parsed_dt) != datetime.timedelta(0):
                     parsed_dt = parsed_dt.astimezone(datetime.timezone.utc)
                 return parsed_dt
                 # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
             except ValueError: pass

        # Попытка 4: Другие распространенные форматы без явной TZ
        formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]
        if isinstance(date_str, str):
            for fmt in formats:
                try:
                    parsed_dt = datetime.datetime.strptime(date_str, fmt)
                    # --- ИСПРАВЛЕНИЕ: Отделяем присваивание и return ---
                    parsed_dt = parsed_dt.replace(tzinfo=datetime.timezone.utc)
                    return parsed_dt
                    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
                except ValueError: continue

    except Exception as e:
        debug_print(f"Общая ошибка парсинга даты '{date_str}': {e}")

    # Попытка 5: Резервные варианты
    try:
        # ISO формат с миллисекундами и Z
        if isinstance(date_str, str) and "T" in date_str and "." in date_str and date_str.endswith("Z"):
            try:
                base_date_str = date_str.split(".")[0]
                parsed_dt = datetime.datetime.fromisoformat(base_date_str)
                # --- ИСПРАВЛЕНИЕ: Отделяем присваивание и return ---
                parsed_dt = parsed_dt.replace(tzinfo=datetime.timezone.utc)
                return parsed_dt
                # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
            except ValueError: pass

        # Если передали числовой timestamp
        if isinstance(date_str, (int, float)):
            try:
                # --- ИСПРАВЛЕНИЕ: Отделяем присваивание и return ---
                parsed_dt = datetime.datetime.fromtimestamp(int(date_str), tz=datetime.timezone.utc)
                return parsed_dt
                # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
            except (ValueError, OSError): pass

    except Exception as e:
        debug_print(f"Ошибка в резервных вариантах парсинга даты '{date_str}': {e}")

    # Если ни один формат не подошел
    now = datetime.datetime.now(datetime.timezone.utc)
    debug_print(f"Не удалось разобрать дату '{date_str}' ни одним из способов. Используем текущее время.")
    return now


def filter_recent_tweets(tweets, hours=24):
    """Фильтрует твиты, оставляя только опубликованные за последние N часов"""
    # (Код без изменений)
    if not tweets: return []
    current_time = datetime.datetime.now(datetime.timezone.utc); cutoff_time = current_time - datetime.timedelta(hours=hours)
    recent_tweets = []; processed_ids = set()
    for tweet in tweets:
        if not isinstance(tweet, dict) or not tweet.get("created_at"): logger.warning(f"Пропуск некорректного твита в фильтре: {tweet}"); continue
        tweet_id = tweet.get("tweet_id")
        if not tweet_id: logger.warning(f"Пропуск твита без ID в фильтре: {tweet.get('url')}"); continue
        if tweet_id in processed_ids: logger.debug(f"Пропуск дубликата tweet_id {tweet_id} в фильтре."); continue
        try:
            tweet_time = parse_twitter_date(tweet["created_at"])
            if not tweet_time: logger.warning(f"Не удалось распарсить дату для твита {tweet_id}, пропускаем."); continue
            if tweet_time.tzinfo is None: tweet_time = tweet_time.replace(tzinfo=datetime.timezone.utc)
            elif tweet_time.tzinfo.utcoffset(tweet_time) != datetime.timedelta(0): tweet_time = tweet_time.astimezone(datetime.timezone.utc)
            if tweet_time >= cutoff_time: recent_tweets.append(tweet); processed_ids.add(tweet_id)
        except Exception as e: logger.error(f"Ошибка обработки даты твита {tweet_id} ({tweet.get('url', '')}): {e}")
    logger.info(f"Фильтр: найдено {len(recent_tweets)} твитов за последние {hours} часов из {len(tweets)}.")
    return recent_tweets


def format_time_ago(iso_time_str):
    """Форматирует время в человеко-читаемый вид"""
    # (Код без изменений)
    try:
        if not iso_time_str: return "неизвестно"
        tweet_time = parse_twitter_date(iso_time_str);
        if not tweet_time: return iso_time_str
        if tweet_time.tzinfo is None: tweet_time = tweet_time.replace(tzinfo=datetime.timezone.utc)
        elif tweet_time.tzinfo.utcoffset(tweet_time) != datetime.timedelta(0): tweet_time = tweet_time.astimezone(datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc); diff = now - tweet_time
        if diff.days > 0: return f"{diff.days} д. назад"
        hours = diff.seconds // 3600; minutes = (diff.seconds % 3600) // 60
        if hours > 0: return f"{hours} ч. назад"
        if minutes > 0: return f"{minutes} мин. назад"
        return "только что"
    except Exception:
        if iso_time_str and isinstance(iso_time_str, str) and "T" in iso_time_str:
             try: return iso_time_str.split("T")[1][:8]
             except: pass
        return str(iso_time_str)


def initialize_browser(chrome_profile_path=None):
    """Инициализирует и возвращает браузер Chrome"""
    # (Код без изменений)
    options = Options(); options.add_argument("--window-size=1920,1080")
    if chrome_profile_path:
        abs_profile_path = os.path.abspath(chrome_profile_path)
        if os.path.exists(abs_profile_path) and os.path.isdir(abs_profile_path): options.add_argument(f"user-data-dir={abs_profile_path}"); logger.info(f"Используется профиль Chrome: {abs_profile_path}")
        else: logger.warning(f"Профиль Chrome не найден: {abs_profile_path}. Используется временный."); chrome_profile_path = None
    else: logger.info("Профиль Chrome не указан, используется временный.")
    options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage"); options.add_argument("--disable-gpu"); options.add_argument("--disable-extensions")
    options.add_argument("--disable-blink-features=AutomationControlled"); options.add_experimental_option("excludeSwitches", ["enable-automation"]); options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--log-level=3"); options.add_argument("--silent")
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
    options.add_argument(f'user-agent={user_agent}'); logger.info(f"Установлен User-Agent: {user_agent}")
    try:
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": user_agent})
        driver.set_page_load_timeout(60)
        logger.info("Браузер Chrome успешно инициализирован.")
        return driver
    except Exception as e: logger.critical(f"Ошибка инициализации браузера: {e}"); import traceback; logger.error(traceback.format_exc()); return None


def manual_auth_with_prompt(driver):
    """Открывает страницу авторизации Twitter и ждет подтверждения пользователя"""
    # (Код без изменений)
    if not driver: logger.error("Браузер не инициализирован, авторизация невозможна."); return False
    try:
        print("\n" + "="*20 + " АВТОРИЗАЦИЯ В TWITTER " + "="*20); print("Открывается страница входа Twitter/X..."); print("ПОЖАЛУЙСТА:\n1. Войдите в свой аккаунт.\n2. Убедитесь, что видите ленту.\n3. Вернитесь сюда и нажмите Enter."); print("="*60)
        driver.get("https://twitter.com/")
        input("\n>>> Нажмите Enter после завершения авторизации...")
        try:
            WebDriverWait(driver, 10).until(EC.any_of(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[data-testid="AppTabBar_Home_Link"]')), EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="SideNav_AccountSwitcher_Button"]'))))
            logger.info("Признаки авторизации обнаружены."); print("Авторизация подтверждена."); return True
        except TimeoutException:
            logger.warning("Не удалось автоматически подтвердить авторизацию."); print("\nВНИМАНИЕ: Не удалось автоматически подтвердить вход.")
            cont = input("Продолжить выполнение скрипта? (да/нет): ")
            return cont.lower() in ['да', 'yes', 'y', 'д']
    except WebDriverException as e: logger.error(f"Ошибка WebDriver во время авторизации: {e}"); print(f"Ошибка браузера: {e}"); return False
    except Exception as e: logger.error(f"Неожиданная ошибка при ручной авторизации: {e}"); print(f"Ошибка авторизации: {e}"); return False


def extract_tweet_stats(tweet_element):
    """Извлекает статистику твита (лайки, ретвиты, ответы)"""
    # (Код без изменений)
    stats = {"likes": 0, "retweets": 0, "replies": 0}
    def parse_stat_value(text):
        if not isinstance(text, str): return 0
        text_upper = text.upper(); text_cleaned = text_upper.replace(',', ''); value_match = re.search(r'([\d.]+)', text_cleaned)
        if not value_match: return 0; value_str = value_match.group(1)
        try:
            value = float(value_str); multiplier = 1
            if 'K' in text_cleaned: multiplier = 1000
            elif 'M' in text_cleaned: multiplier = 1000000
            return int(value * multiplier)
        except ValueError: return 0
    try:
        stat_buttons_container = tweet_element.find_element(By.CSS_SELECTOR, 'div[role="group"]')
        buttons = stat_buttons_container.find_elements(By.CSS_SELECTOR, 'button[data-testid]')
        for button in buttons:
            try:
                test_id = button.get_attribute('data-testid').lower(); aria_label = button.get_attribute('aria-label') or ""; text_content = button.text.strip()
                value = 0; aria_numbers = re.findall(r'([\d,.]+)', aria_label)
                if aria_numbers: value = parse_stat_value(aria_label)
                elif text_content: value = parse_stat_value(text_content)
                if value > 0:
                    stat_key = None
                    if "reply" in test_id or "ответ" in aria_label.lower() or "comment" in aria_label.lower(): stat_key = "replies"
                    elif "retweet" in test_id or "ретвит" in aria_label.lower() or "repost" in aria_label.lower(): stat_key = "retweets"
                    elif "like" in test_id or "нрав" in aria_label.lower() or "лайк" in aria_label.lower(): stat_key = "likes"
                    if stat_key: stats[stat_key] = max(stats.get(stat_key, 0), value)
            except StaleElementReferenceException: logger.warning("Кнопка статистики устарела."); continue
            except Exception as e:
                 if not isinstance(e, NoSuchElementException): logger.warning(f"Ошибка обработки кнопки статистики: {e}")
    except NoSuchElementException: logger.debug("Контейнер кнопок статистики не найден.")
    except Exception as e: logger.error(f"Общая ошибка при поиске/обработке статистики: {e}")
    return stats
