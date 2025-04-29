#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Основной модуль скрапера Twitter, содержащий функции для инициализации и запуска скрапера
(Функционал изображений, ссылок и статей удален)
"""

import os
import sys
import json
import time
import logging
from selenium import webdriver
# Доп. импорты Selenium убраны, так как они используются в utils/tweets
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.common.exceptions import TimeoutException

# Настройка логирования (один раз здесь)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler = logging.FileHandler('twitter_scraper.log', mode='a', encoding='utf-8')
log_handler.setFormatter(log_formatter)

# Логгер для всего проекта
logger = logging.getLogger('twitter_scraper')
logger.setLevel(logging.INFO) # Устанавливаем уровень логирования
logger.addHandler(log_handler)

# Добавляем вывод в консоль для INFO и выше
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)


# Настройки
# Убедитесь, что путь к профилю Chrome правильный для вашей системы
CHROME_PROFILE_PATH = "/Users/evgeniyyanvarskiy/Library/Application Support/Google/Chrome/Profile 1/" # Пример для macOS
# CHROME_PROFILE_PATH = "C:\\Users\\YourUser\\AppData\\Local\\Google\\Chrome\\User Data\\Profile 1" # Пример для Windows
# CHROME_PROFILE_PATH = "~/.config/google-chrome/Profile 1" # Пример для Linux

CACHE_DIR = "twitter_cache"
# IMAGES_DIR удален
# ARTICLE_CACHE_DIR удален
# LINKS_CACHE_DIR удален
HTML_CACHE_DIR = "twitter_html_cache"  # Директория для временных HTML (для отладки)

# Создаем необходимые директории
# Убраны IMAGES_DIR, ARTICLE_CACHE_DIR, LINKS_CACHE_DIR
for directory in [CACHE_DIR, HTML_CACHE_DIR]:
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Создана директория: {directory}")
        except OSError as e:
             logger.error(f"Не удалось создать директорию {directory}: {e}")
    else:
         logger.debug(f"Директория существует: {directory}")


# Настройки подключения к MySQL
MYSQL_CONFIG = {
    'host': '217.154.19.224', # Используйте localhost, если БД на той же машине
    'database': 'twitter_data',
    'user': 'elcrypto',
    'password': 'LohNeMamont@!21',
    'port': 3306
}


def initialize_dependencies():
    """
    Импортирует необходимые модули и проверяет их наличие
    Возвращает словарь с импортированными модулями
    """
    dependencies = {}
    logger.info("Инициализация зависимостей...")

    try:
        # Импортируем базовые утилиты
        from twitter_scraper_utils import (
            debug_print, initialize_mysql, save_user_to_db, save_tweet_to_db,
            parse_twitter_date, filter_recent_tweets, format_time_ago,
            initialize_browser, manual_auth_with_prompt,
            # download_image, extract_images_from_tweet, save_image_to_db удалены
            extract_tweet_stats, extract_retweet_info # Базовый extract_retweet_info тоже импортируем на всякий случай
        )
        # Добавляем в словарь
        utils_funcs = {k: v for k, v in locals().items() if callable(v) and not k.startswith('_')}
        dependencies.update(utils_funcs)
        logger.debug("Базовые утилиты импортированы.")

        # Импортируем утилиты для ссылок (только нужные)
        from twitter_scraper_links_utils import (
            # extract_all_links_from_tweet, save_links_to_db удалены
            is_tweet_truncated,
            get_full_tweet_text,
            extract_full_tweet_text_from_html
        )
        links_funcs = {k: v for k, v in locals().items() if callable(v) and k in [
            'is_tweet_truncated', 'get_full_tweet_text', 'extract_full_tweet_text_from_html']}
        dependencies.update(links_funcs)
        logger.debug("Утилиты для текста твитов импортированы.")

        # --- Импорт утилит для статей удален ---
        # from twitter_scraper_article_utils import ...

        # Импортируем утилиты для ретвитов (из enhanced_utils, который сам импортирует retweet_utils)
        from twitter_scraper_enhanced_utils import (
            extract_retweet_info_enhanced,
            # extract_retweet_info_basic, get_author_info # Они тоже импортируются, но основной - enhanced
        )
        retweet_funcs = {k: v for k, v in locals().items() if callable(v) and k in ['extract_retweet_info_enhanced']}
        dependencies.update(retweet_funcs)
        # Добавим базовую функцию ретвитов, если enhanced не импортировалась
        if 'extract_retweet_info_enhanced' not in dependencies and 'extract_retweet_info' in dependencies:
             dependencies['extract_retweet_info_enhanced'] = dependencies['extract_retweet_info']
             logger.warning("Используется базовая функция extract_retweet_info вместо enhanced.")
        logger.debug("Утилиты для ретвитов импортированы.")


        # Импортируем утилиты для твитов
        from twitter_scraper_tweets import get_tweets_with_selenium
        dependencies['get_tweets_with_selenium'] = get_tweets_with_selenium
        logger.debug("Утилиты для сбора твитов импортированы.")

        # Импортируем утилиты для статистики
        from twitter_scraper_stats import (
            generate_tweet_statistics, generate_database_statistics,
            display_results_summary
        )
        stats_funcs = {k: v for k, v in locals().items() if callable(v) and k in [
            'generate_tweet_statistics', 'generate_database_statistics', 'display_results_summary']}
        dependencies.update(stats_funcs)
        logger.debug("Утилиты для статистики импортированы.")

        # Импортируем API клиент
        try:
            from twitter_api_client import get_tweet_by_id, process_api_tweet_data
            dependencies['get_tweet_by_id'] = get_tweet_by_id
            dependencies['process_api_tweet_data'] = process_api_tweet_data
            logger.debug("API клиент импортирован.")
        except ImportError:
             logger.warning("Не удалось импортировать API клиент. Сбор через API будет недоступен.")
             dependencies['get_tweet_by_id'] = lambda tweet_id: None
             dependencies['process_api_tweet_data'] = lambda api_data, tweet_url: None


        logger.info("Импорт всех зависимостей завершен успешно")
        return dependencies

    except ImportError as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать необходимые функции: {e}")
        logger.critical("Убедитесь, что все файлы (_utils.py, _tweets.py, _stats.py, _links_utils.py, _retweet_utils.py, _enhanced_utils.py, _api_client.py) находятся в той же директории.")
        sys.exit(1)


def load_accounts_from_file(filename="influencer_twitter.txt"):
    """Загружает аккаунты Twitter из файла"""
    accounts = []
    logger.info(f"Загрузка аккаунтов из файла: {filename}")
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Извлекаем username из URL или просто берем строку
            username = None
            if line.startswith('http'):
                try:
                    # Удаляем возможные параметры и последний слэш
                    clean_url = line.split('?')[0].split('#')[0].rstrip('/')
                    parts = clean_url.split('/')
                    if len(parts) > 0:
                         potential_username = parts[-1]
                         # Простая проверка на валидность username
                         if potential_username and potential_username.isalnum() or '_' in potential_username:
                              username = potential_username
                         else:
                              logger.warning(f"Не удалось извлечь username из URL '{line}' в строке {line_num}")
                except Exception as e:
                     logger.warning(f"Ошибка извлечения username из URL '{line}' в строке {line_num}: {e}")
            else:
                username = line.lstrip('@')
                if not (username and (username.isalnum() or '_' in username)):
                     logger.warning(f"Некорректный формат username '{line}' в строке {line_num}")
                     username = None # Сбрасываем, если формат неверный

            if username and username not in accounts: # Добавляем только уникальные
                accounts.append(username)
            elif not username:
                 logger.warning(f"Пропущена строка {line_num} в файле {filename}: '{line}'")


        logger.info(f"Загружено {len(accounts)} уникальных аккаунтов из файла {filename}")
        return accounts

    except FileNotFoundError:
        logger.error(f"Файл {filename} не найден! Пожалуйста, создайте файл и добавьте в него Twitter-аккаунты (по одному на строку, можно URL или @username).")
        return []
    except Exception as e:
        logger.error(f"Ошибка при чтении файла {filename}: {e}")
        return []


def main():
    """
    Основная функция скрапера
    """
    logger.info("="*30)
    logger.info("=== ЗАПУСК СКРИПТА ПО СБОРУ ТВИТОВ ===")
    logger.info("="*30)

    deps = initialize_dependencies()

    if not os.path.exists(CHROME_PROFILE_PATH):
         logger.warning(f"Указанный профиль Chrome НЕ НАЙДЕН: {CHROME_PROFILE_PATH}")
         logger.warning("Будет использован временный профиль Chrome.")
         effective_chrome_path = None
    else:
         logger.info(f"Используется профиль Chrome: {CHROME_PROFILE_PATH}")
         effective_chrome_path = CHROME_PROFILE_PATH


    logger.info("--- Подключение к MySQL ---")
    db_connection = None
    try:
        db_connection = deps['initialize_mysql'](MYSQL_CONFIG)
        if db_connection and db_connection.is_connected():
            logger.info("Успешное подключение к MySQL")
        else:
            logger.warning("Не удалось подключиться к MySQL. Данные не будут сохранены в базу.")
            # Спрашиваем пользователя, продолжать ли
            answer = input("Не удалось подключиться к MySQL. Продолжить без сохранения в БД? (да/нет): ")
            if answer.lower() not in ['да', 'yes', 'y', 'д']:
                logger.info("Пользователь отменил запуск без MySQL. Выход из программы.")
                print("Выход из программы...")
                return
            db_connection = None # Устанавливаем в None, если пользователь согласился продолжить
    except Exception as e:
         logger.error(f"Ошибка при инициализации MySQL: {e}")
         db_connection = None # Считаем, что подключения нет


    # Параметры для настройки
    HOURS_FILTER = 24
    CACHE_DURATION = 1
    MAX_TWEETS = 15 # Немного увеличим
    FORCE_REFRESH = True # По умолчанию обновляем принудительно
    # EXTRACT_ARTICLES удален
    EXTRACT_FULL_TWEETS = True # Оставляем извлечение полных твитов
    # EXTRACT_LINKS удален

    accounts_to_track = load_accounts_from_file("influencer_twitter.txt")

    if not accounts_to_track:
        logger.warning("Список аккаунтов пуст или файл не найден. Завершение работы.")
        print("Ошибка: Файл 'influencer_twitter.txt' не найден или пуст. Нечего отслеживать.")
        return

    logger.info("--- Основные параметры ---")
    logger.info(f"Период твитов: последние {HOURS_FILTER} часа")
    logger.info(f"Срок действия кэша: {CACHE_DURATION} час")
    logger.info(f"Максимальное количество твитов на аккаунт: {MAX_TWEETS}")
    logger.info(f"Принудительное обновление кэша: {'ДА' if FORCE_REFRESH else 'НЕТ'}")
    # logger.info(f"Извлечение полных статей: {'ДА' if EXTRACT_ARTICLES else 'НЕТ'}") # Удалено
    logger.info(f"Извлечение полных твитов: {'ДА' if EXTRACT_FULL_TWEETS else 'НЕТ'}")
    # logger.info(f"Извлечение всех ссылок: {'ДА' if EXTRACT_LINKS else 'НЕТ'}") # Удалено
    logger.info(f"Аккаунты для отслеживания ({len(accounts_to_track)}): {', '.join('@' + account for account in accounts_to_track)}")

    driver = None # Инициализируем переменную драйвера
    try:
        logger.info("--- Инициализация браузера Chrome ---")
        driver = deps['initialize_browser'](effective_chrome_path)
        if not driver:
            logger.critical("Не удалось инициализировать браузер. Завершение работы.")
            print("Критическая ошибка: Не удалось запустить браузер Chrome.")
            return

        logger.info("Браузер Chrome успешно инициализирован")

        logger.info("--- Авторизация в Twitter ---")
        auth_result = deps['manual_auth_with_prompt'](driver)
        logger.info(f"Результат подтверждения авторизации: {'УСПЕШНО' if auth_result else 'НЕ ПОДТВЕРЖДЕНО'}")
        # Продолжаем в любом случае, но логируем результат

        all_results = []
        start_time_total = time.time()

        for i, username in enumerate(accounts_to_track, 1):
            logger.info(f"=== Обработка аккаунта {i}/{len(accounts_to_track)}: @{username} ===")
            start_time_user = time.time()

            user_data = deps['get_tweets_with_selenium'](
                username=username,
                driver=driver,
                db_connection=db_connection,
                max_tweets=MAX_TWEETS,
                use_cache=not FORCE_REFRESH, # Используем кэш, если не форсируем обновление
                cache_duration_hours=CACHE_DURATION,
                time_filter_hours=HOURS_FILTER,
                force_refresh=FORCE_REFRESH,
                # extract_articles=EXTRACT_ARTICLES, # Удалено
                extract_full_tweets=EXTRACT_FULL_TWEETS,
                # extract_links=EXTRACT_LINKS, # Удалено
                dependencies=deps,
                html_cache_dir=HTML_CACHE_DIR
            )

            end_time_user = time.time()
            logger.info(f"Завершена обработка @{username} за {end_time_user - start_time_user:.2f} сек.")

            # Проверяем, что результат содержит твиты
            if user_data and user_data.get("tweets"):
                all_results.append(user_data)
                logger.info(f"Найдено {len(user_data['tweets'])} свежих твитов от @{username}")
            else:
                logger.info(f"Нет свежих твитов от @{username} за последние {HOURS_FILTER} часа")

            # Небольшая пауза между аккаунтами
            time.sleep(2)

        end_time_total = time.time()
        logger.info(f"Завершена обработка всех аккаунтов за {end_time_total - start_time_total:.2f} сек.")

        logger.info("===== РЕЗУЛЬТАТЫ =====")
        if not all_results:
            logger.warning(f"Не найдено свежих твитов за последние {HOURS_FILTER} часа от отслеживаемых аккаунтов.")
            print(f"\nНе найдено твитов за последние {HOURS_FILTER} часа от отслеживаемых аккаунтов.")
        else:
            # Отображаем результаты
            deps['display_results_summary'](all_results, HOURS_FILTER) # images_dir больше не нужен

            # Генерируем и выводим статистику
            stats = deps['generate_tweet_statistics'](all_results)
            logger.info(f"Общая статистика: {stats}")

            if db_connection:
                db_stats = deps['generate_database_statistics'](db_connection)
                logger.info(f"Статистика БД: {db_stats}")
                print("\n--- Информация о базе данных ---")
                if isinstance(db_stats, dict):
                     for category, count in db_stats.items():
                         print(f"- {category}: {count}")
                else:
                     print("Не удалось получить статистику БД.")

    except KeyboardInterrupt:
         logger.warning("Прервано пользователем (Ctrl+C)")
         print("\nПрервано пользователем.")
    except Exception as e:
         logger.critical(f"Произошла критическая ошибка в главном цикле: {e}")
         import traceback
         logger.error(traceback.format_exc()) # Логируем полный traceback
         print(f"Произошла критическая ошибка: {e}")
    finally:
        # Закрываем браузер и соединение с базой данных
        logger.info("--- Завершение работы ---")

        if driver:
            try:
                driver.quit()
                logger.info("Браузер закрыт")
            except Exception as e:
                 logger.error(f"Ошибка при закрытии браузера: {e}")

        if db_connection and hasattr(db_connection, 'is_connected') and db_connection.is_connected():
            try:
                db_connection.close()
                logger.info("Соединение с базой данных закрыто")
            except Exception as e:
                 logger.error(f"Ошибка при закрытии соединения с БД: {e}")

        logger.info("=== СКРИПТ ЗАВЕРШИЛ РАБОТУ ===")
        print("\n=== СКРИПТ ЗАВЕРШИЛ РАБОТУ ===")


if __name__ == "__main__":
    main()
