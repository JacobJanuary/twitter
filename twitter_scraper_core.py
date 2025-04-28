#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Основной модуль скрапера Twitter, содержащий функции для инициализации и запуска скрапера
(Функционал обработки статей удален, структура импортов упрощена)
"""

import os
import sys
import json
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='twitter_scraper.log',
    filemode='a'
)
logger = logging.getLogger('twitter_scraper')

# Настройки
CHROME_PROFILE_PATH = "/Users/evgeniyyanvarskiy/Library/Application Support/Google/Chrome/Profile 1/" # Пример пути, измените на свой
CACHE_DIR = "twitter_cache"
LINKS_CACHE_DIR = "twitter_links_cache"
HTML_CACHE_DIR = "twitter_html_cache"  # Директория для временных HTML

# Создаем директории
for directory in [CACHE_DIR, LINKS_CACHE_DIR, HTML_CACHE_DIR]:
    os.makedirs(directory, exist_ok=True)
    logger.info(f"Создана директория: {directory}")

# Настройки подключения к MySQL
MYSQL_CONFIG = {
    'host': '217.154.19.224', # Пример, измените на свой
    'database': 'twitter_data',
    'user': 'elcrypto', # Пример, измените на свой
    'password': 'LohNeMamont@!21', # Пример, измените на свой
    'port': 3306
}


def initialize_dependencies():
    """
    Импортирует необходимые модули и проверяет их наличие.
    Возвращает словарь с импортированными функциями.
    """
    dependencies = {}
    missing_modules = []

    try:
        # Импортируем базовые утилиты
        from twitter_scraper_utils import (
            debug_print, initialize_mysql, save_user_to_db, save_tweet_to_db,
            parse_twitter_date, filter_recent_tweets, format_time_ago,
            initialize_browser, manual_auth_with_prompt,
            extract_tweet_stats, extract_retweet_info # Базовая функция ретвитов
        )
        # Добавляем базовые утилиты в словарь
        base_utils = [
            debug_print, initialize_mysql, save_user_to_db, save_tweet_to_db,
            parse_twitter_date, filter_recent_tweets, format_time_ago,
            initialize_browser, manual_auth_with_prompt,
            extract_tweet_stats, extract_retweet_info
        ]
        for func in base_utils:
            dependencies[func.__name__] = func
        logger.info("Базовые утилиты (twitter_scraper_utils) импортированы.")
    except ImportError as e:
        logger.error(f"Ошибка импорта базовых утилит: {e}")
        missing_modules.append("twitter_scraper_utils")

    try:
        # Импортируем утилиты для ссылок и длинных твитов
        from twitter_scraper_links_utils import (
            extract_all_links_from_tweet, save_links_to_db,
            is_tweet_truncated, get_full_tweet_text,
            extract_full_tweet_text_from_html
        )
        link_utils = [
             extract_all_links_from_tweet, save_links_to_db,
            is_tweet_truncated, get_full_tweet_text,
            extract_full_tweet_text_from_html
        ]
        for func in link_utils:
             dependencies[func.__name__] = func
        logger.info("Утилиты для ссылок (twitter_scraper_links_utils) импортированы.")
    except ImportError as e:
        logger.error(f"Ошибка импорта утилит для ссылок: {e}")
        missing_modules.append("twitter_scraper_links_utils")

    try:
        # Импортируем утилиты для ретвитов (расширенная версия)
        from twitter_scraper_retweet_utils import (
            extract_retweet_info_enhanced, # Расширенная функция
            get_author_info
        )
        # Добавляем или перезаписываем функцию извлечения информации о ретвите
        dependencies['extract_retweet_info_enhanced'] = extract_retweet_info_enhanced
        # Добавляем функцию получения информации об авторе
        dependencies['get_author_info'] = get_author_info
        logger.info("Утилиты для ретвитов (twitter_scraper_retweet_utils) импортированы.")
    except ImportError as e:
        logger.error(f"Ошибка импорта утилит для ретвитов: {e}")
        missing_modules.append("twitter_scraper_retweet_utils")

    try:
        # Импортируем утилиты для твитов
        from twitter_scraper_tweets import get_tweets_with_selenium
        dependencies['get_tweets_with_selenium'] = get_tweets_with_selenium
        logger.info("Утилиты для твитов (twitter_scraper_tweets) импортированы.")
    except ImportError as e:
        logger.error(f"Ошибка импорта утилит для твитов: {e}")
        missing_modules.append("twitter_scraper_tweets")

    try:
        # Импортируем утилиты для статистики
        from twitter_scraper_stats import (
            generate_tweet_statistics, generate_database_statistics,
            display_results_summary
        )
        stat_utils = [
            generate_tweet_statistics, generate_database_statistics,
            display_results_summary
        ]
        for func in stat_utils:
             dependencies[func.__name__] = func
        logger.info("Утилиты для статистики (twitter_scraper_stats) импортированы.")
    except ImportError as e:
        logger.error(f"Ошибка импорта утилит для статистики: {e}")
        missing_modules.append("twitter_scraper_stats")

    # Проверяем, все ли модули загружены
    if missing_modules:
        logger.critical(f"ОШИБКА: Не удалось импортировать модули: {', '.join(missing_modules)}")
        logger.critical("Убедитесь, что все необходимые файлы (.py) находятся в той же директории, что и twitter_scraper_core.py")
        sys.exit(1)

    logger.info("Импорт всех зависимостей завершен успешно.")
    return dependencies


def load_accounts_from_file(filename="influencer_twitter.txt"):
    """Загружает аккаунты Twitter из файла"""
    accounts = []

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):  # Пропускаем пустые строки и комментарии
                continue

            # Если строка содержит URL, извлекаем username
            if line.startswith('http'):
                parts = line.rstrip('/').split('/')
                username = parts[-1]  # Берем последнюю часть URL как username
                accounts.append(username)
            else:
                # Если просто имя пользователя, добавляем как есть
                username = line.lstrip('@')  # Удаляем @ если есть
                if username:
                    accounts.append(username)

        logger.info(f"Загружено {len(accounts)} аккаунтов из файла {filename}")
        return accounts

    except FileNotFoundError:
        logger.warning(f"Файл {filename} не найден. Создайте файл и добавьте в него Twitter-аккаунты.")
        return []
    except Exception as e:
        logger.error(f"Ошибка при чтении файла {filename}: {e}")
        return []


def main():
    """
    Основная функция скрапера
    """
    print("\n=== ЗАПУСК СКРИПТА ПО СБОРУ ТВИТОВ ===\n")
    logger.info("Запуск скрипта по сбору твитов")

    # Импортируем зависимости
    deps = initialize_dependencies()

    # Напоминание о необходимости заполнить путь к профилю Chrome
    if not CHROME_PROFILE_PATH or not os.path.exists(CHROME_PROFILE_PATH):
        print(f"ПРЕДУПРЕЖДЕНИЕ: Путь к профилю Chrome не указан или неверен: {CHROME_PROFILE_PATH}")
        print("Будет использован временный профиль Selenium.")
        logger.warning(f"Путь к профилю Chrome не указан или неверен ({CHROME_PROFILE_PATH}), используется временный профиль")
        actual_profile_path = None # Используем временный профиль
    else:
        print(f"Используется профиль Chrome: {CHROME_PROFILE_PATH}")
        logger.info(f"Используется профиль Chrome: {CHROME_PROFILE_PATH}")
        actual_profile_path = CHROME_PROFILE_PATH

    # Подключаемся к базе данных
    print("\n--- Подключение к MySQL ---")
    db_connection = deps['initialize_mysql'](MYSQL_CONFIG)
    if not db_connection:
        print("ВНИМАНИЕ: Не удалось подключиться к MySQL. Данные не будут сохранены в базу.")
        logger.warning("Не удалось подключиться к MySQL. Данные не будут сохранены в базу.")
        answer = input("Хотите продолжить без сохранения в MySQL? (да/нет): ")
        if answer.lower() not in ['да', 'yes', 'y', 'д']:
            print("Выход из программы...")
            logger.info("Пользователь отменил запуск без MySQL. Выход из программы.")
            return
    else:
        print("Успешное подключение к MySQL")
        logger.info("Успешное подключение к MySQL")

    # Параметры для настройки
    HOURS_FILTER = 24  # Фильтр по времени публикации (в часах)
    CACHE_DURATION = 1  # Срок действия кэша (в часах)
    MAX_TWEETS = 10  # Максимальное количество твитов для каждого аккаунта
    FORCE_REFRESH = False  # Принудительное обновление данных (True для игнорирования кэша)
    EXTRACT_FULL_TWEETS = True  # Извлекать полный текст длинных твитов
    EXTRACT_LINKS = True  # Извлекать все ссылки из твитов

    # Загружаем список аккаунтов из файла
    accounts_to_track = load_accounts_from_file("influencer_twitter.txt")

    # Если файл не найден или пуст, используем дефолтный список
    if not accounts_to_track:
        print("Файл influencer_twitter.txt не найден или пуст. Используем список аккаунтов по умолчанию.")
        logger.warning("Файл influencer_twitter.txt не найден или пуст. Используем список аккаунтов по умолчанию.")
        accounts_to_track = [
            "Defi0xJeff", # Пример
            "elonmusk",   # Пример
            "OpenAI"      # Пример
        ]

    print(f"\n--- Основные параметры ---")
    print(f"Период твитов: последние {HOURS_FILTER} часа")
    print(f"Срок действия кэша: {CACHE_DURATION} час")
    print(f"Максимальное количество твитов на аккаунт: {MAX_TWEETS}")
    print(f"Принудительное обновление (игнор. кэш): {'ДА' if FORCE_REFRESH else 'НЕТ'}")
    print(f"Извлечение полных твитов: {'ДА' if EXTRACT_FULL_TWEETS else 'НЕТ'}")
    print(f"Извлечение всех ссылок: {'ДА' if EXTRACT_LINKS else 'НЕТ'}")
    print(f"Аккаунты для отслеживания ({len(accounts_to_track)}): {', '.join('@' + account for account in accounts_to_track)}")

    logger.info(f"Параметры: период={HOURS_FILTER}ч, кэш={CACHE_DURATION}ч, макс.твитов={MAX_TWEETS}, " +
                f"обновление={FORCE_REFRESH}, полные твиты={EXTRACT_FULL_TWEETS}, " +
                f"ссылки={EXTRACT_LINKS}, аккаунтов={len(accounts_to_track)}")

    # Инициализируем браузер
    print(f"\n--- Инициализация браузера Chrome ---")
    # Передаем actual_profile_path, который может быть None
    driver = deps['initialize_browser'](actual_profile_path)
    if not driver:
        print("Не удалось инициализировать браузер. Завершение работы.")
        logger.error("Не удалось инициализировать браузер. Завершение работы.")
        # Закрываем соединение с БД, если оно было открыто
        if db_connection and hasattr(db_connection, 'is_connected') and db_connection.is_connected():
            db_connection.close()
            logger.info("Соединение с базой данных закрыто при ошибке инициализации браузера.")
        return
    else:
        print("Браузер Chrome успешно инициализирован")
        logger.info("Браузер Chrome успешно инициализирован")

    try:
        # Сначала выполняем ручную авторизацию с ожиданием нажатия Enter
        print("\n--- Авторизация в Twitter ---")
        # Проверяем, нужна ли авторизация (например, если используется временный профиль)
        # В реальном сценарии здесь может быть более сложная логика проверки сессии
        auth_needed = not actual_profile_path # Пример: считаем, что авторизация нужна, если нет профиля
        auth_result = True # По умолчанию считаем успешной, если не требуется
        if auth_needed:
             auth_result = deps['manual_auth_with_prompt'](driver)
             print(f"Результат ручной авторизации: {'УСПЕШНО' if auth_result else 'НЕ УДАЛОСЬ ПОДТВЕРДИТЬ'}")
             logger.info(f"Результат ручной авторизации: {'успешно' if auth_result else 'не подтверждено'}")
        else:
            print("Используется профиль Chrome, предполагается наличие активной сессии.")
            logger.info("Используется профиль Chrome, ручная авторизация пропущена.")


        all_results = []
        processed_accounts = 0

        # Обрабатываем каждый аккаунт
        for username in accounts_to_track:
            processed_accounts += 1
            print(f"\n=== Обработка аккаунта @{username} ({processed_accounts}/{len(accounts_to_track)}) ===")
            logger.info(f"Начало обработки аккаунта @{username}")

            # Получаем твиты пользователя
            user_data = deps['get_tweets_with_selenium'](
                username=username,
                driver=driver,
                db_connection=db_connection,
                max_tweets=MAX_TWEETS,
                use_cache=(not FORCE_REFRESH), # Используем кэш, если не включено принуд. обновление
                cache_duration_hours=CACHE_DURATION,
                time_filter_hours=HOURS_FILTER,
                force_refresh=FORCE_REFRESH, # Передаем флаг дальше
                extract_full_tweets=EXTRACT_FULL_TWEETS,
                extract_links=EXTRACT_LINKS,
                dependencies=deps,  # Передаем словарь с функциями
                html_cache_dir=HTML_CACHE_DIR
            )

            # Проверяем, что результат содержит твиты
            if user_data and user_data.get("tweets"): # Добавлена проверка user_data
                all_results.append(user_data)
                print(f"Найдено {len(user_data['tweets'])} свежих твитов от @{username}")
                logger.info(f"Найдено {len(user_data['tweets'])} свежих твитов от @{username}")
            elif user_data: # Если user_data есть, но нет свежих твитов
                print(f"Нет свежих твитов от @{username} за последние {HOURS_FILTER} часа (или достигнут лимит).")
                logger.info(f"Нет свежих твитов от @{username} за последние {HOURS_FILTER} часа (или достигнут лимит).")
            else: # Если user_data == None (ошибка при обработке)
                 print(f"Не удалось получить данные для @{username}.")
                 logger.error(f"Не удалось получить данные для @{username}.")


            print(f"=== Завершена обработка @{username} ===\n")
            logger.info(f"Завершена обработка @{username}")
            # Небольшая пауза между обработкой аккаунтов
            time.sleep(2)

        # Вывод результатов
        print("\n===== ИТОГОВЫЕ РЕЗУЛЬТАТЫ =====\n")
        logger.info("Формирование итоговых результатов")

        if not all_results:
            print(f"Не найдено свежих твитов за последние {HOURS_FILTER} часа ни у одного из отслеживаемых аккаунтов.")
            logger.warning(f"Не найдено свежих твитов за последние {HOURS_FILTER} часа ни у одного из отслеживаемых аккаунтов.")
        else:
            # Отображаем результаты
            deps['display_results_summary'](all_results, HOURS_FILTER)

            # Генерируем общую статистику
            total_stats = deps['generate_tweet_statistics'](all_results)
            print("\n--- Общая статистика по собранным твитам ---")
            for key, value in total_stats.items():
                 # Простое форматирование ключей для вывода
                 label = key.replace('_', ' ').capitalize()
                 print(f"- {label}: {value}")
            logger.info(f"Общая статистика: {total_stats}")

        # Если есть подключение к БД, получаем статистику базы данных
        if db_connection:
            db_stats = deps['generate_database_statistics'](db_connection)
            if db_stats: # Проверяем, что статистика получена
                print("\n--- Информация о базе данных ---")
                for category, count in db_stats.items():
                    print(f"- {category}: {count}")
                logger.info(f"Статистика БД: {db_stats}")
            else:
                logger.warning("Не удалось получить статистику базы данных.")

    except Exception as e:
        # Логируем критическую ошибку в основном цикле
        logger.critical(f"Критическая ошибка в основном цикле: {e}", exc_info=True)
        print(f"Произошла критическая ошибка: {e}")
    finally:
        # Закрываем браузер и соединение с базой данных
        print("\n--- Завершение работы ---")
        logger.info("Завершение работы скрапера")

        if 'driver' in locals() and driver:
            try:
                driver.quit()
                print("Браузер закрыт")
                logger.info("Браузер закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии браузера: {e}")

        if db_connection and hasattr(db_connection, 'is_connected') and db_connection.is_connected():
            try:
                db_connection.close()
                print("Соединение с базой данных закрыто")
                logger.info("Соединение с базой данных закрыто")
            except Exception as e:
                logger.error(f"Ошибка при закрытии соединения с БД: {e}")

        print("\n=== СКРИПТ ЗАВЕРШИЛ РАБОТУ ===")
        logger.info("СКРИПТ ЗАВЕРШИЛ РАБОТУ")


if __name__ == "__main__":
    main()
