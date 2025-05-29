#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Основной модуль скрапера Twitter, содержащий функции для инициализации и запуска скрапера
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
CHROME_PROFILE_PATH = "/Users/evgeniyyanvarskiy/Library/Application Support/Google/Chrome/Profile 1/"
CACHE_DIR = "twitter_cache"
IMAGES_DIR = "twitter_images"
ARTICLE_CACHE_DIR = "twitter_article_cache"
LINKS_CACHE_DIR = "twitter_links_cache"
HTML_CACHE_DIR = "twitter_html_cache"  # Директория для временных HTML

# Создаем директории
for directory in [CACHE_DIR, IMAGES_DIR, ARTICLE_CACHE_DIR, LINKS_CACHE_DIR, HTML_CACHE_DIR]:
    os.makedirs(directory, exist_ok=True)
    logger.info(f"Создана директория: {directory}")

# Настройки подключения к MySQL
MYSQL_CONFIG = {
    'host': '217.154.19.224',
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

    try:
        # Импортируем базовые утилиты
        from twitter_scraper_utils import (
            debug_print, initialize_mysql, save_user_to_db, save_tweet_to_db,
            parse_twitter_date, filter_recent_tweets, format_time_ago,
            initialize_browser, manual_auth_with_prompt, download_image,
            extract_tweet_stats, extract_images_from_tweet, extract_retweet_info
        )

        # Добавляем в словарь
        for func_name, func in locals().items():
            if callable(func) and not func_name.startswith('_'):
                dependencies[func_name] = func

        # Импортируем расширенные утилиты
        from twitter_scraper_enhanced_utils import (
            process_article_from_tweet, is_tweet_truncated, get_full_tweet_text,
            extract_all_links_from_tweet, save_links_to_db, extract_retweet_info_enhanced
        )

        # Добавляем в словарь
        for func_name, func in locals().items():
            if callable(func) and not func_name.startswith('_'):
                dependencies[func_name] = func

        # Импортируем утилиты для твитов
        from twitter_scraper_tweets import get_tweets_with_selenium
        dependencies['get_tweets_with_selenium'] = get_tweets_with_selenium

        # Импортируем утилиты для статистики
        from twitter_scraper_stats import (
            generate_tweet_statistics, generate_database_statistics,
            display_results_summary
        )
        dependencies['generate_tweet_statistics'] = generate_tweet_statistics
        dependencies['generate_database_statistics'] = generate_database_statistics
        dependencies['display_results_summary'] = display_results_summary

        logger.info("Импорт всех зависимостей завершен успешно")
        return dependencies

    except ImportError as e:
        logger.error(f"ОШИБКА: Не удалось импортировать функции: {e}")
        logger.error("Убедитесь, что все необходимые файлы находятся в той же директории")
        sys.exit(1)


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
    if not CHROME_PROFILE_PATH:
        print("ПРИМЕЧАНИЕ: Вы не указали путь к профилю Chrome. Будет использован временный профиль.")
        logger.warning("Путь к профилю Chrome не указан, используется временный профиль")
    else:
        print(f"Используется профиль Chrome: {CHROME_PROFILE_PATH}")
        logger.info(f"Используется профиль Chrome: {CHROME_PROFILE_PATH}")

    # Параметры для настройки
    HOURS_FILTER = 24  # Фильтр по времени публикации (в часах)
    CACHE_DURATION = 1  # Срок действия кэша (в часах)
    MAX_TWEETS = 10  # Увеличенное максимальное количество твитов для каждого аккаунта
    FORCE_REFRESH = True  # Принудительное обновление данных
    EXTRACT_ARTICLES = True  # Извлекать полные статьи из твитов
    EXTRACT_FULL_TWEETS = True  # Извлекать полный текст длинных твитов
    EXTRACT_LINKS = True  # Извлекать все ссылки из твитов

    # Инициализируем браузер
    print(f"\n--- Инициализация браузера Chrome ---")
    driver = deps['initialize_browser'](CHROME_PROFILE_PATH)
    if not driver:
        print("Не удалось инициализировать браузер. Завершение работы.")
        logger.error("Не удалось инициализировать браузер. Завершение работы.")
        return
    else:
        print("Браузер Chrome успешно инициализирован")
        logger.info("Браузер Chrome успешно инициализирован")

    try:
        # Сначала выполняем ручную авторизацию с ожиданием нажатия Enter
        print("\n--- Авторизация в Twitter ---")
        auth_result = deps['manual_auth_with_prompt'](driver)
        print(f"Результат авторизации: {'УСПЕШНО' if auth_result else 'НЕ УДАЛОСЬ ПОДТВЕРДИТЬ'}")
        logger.info(f"Результат авторизации: {'успешно' if auth_result else 'не подтверждено'}")

        # Начинаем бесконечный цикл
        while True:
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
                    break
            else:
                print("Успешное подключение к MySQL")
                logger.info("Успешное подключение к MySQL")

            # Загружаем список аккаунтов из файла
            accounts_to_track = load_accounts_from_file("influencer_twitter.txt")

            # Если файл не найден или пуст, используем дефолтный список
            if not accounts_to_track:
                print("Используем список аккаунтов по умолчанию")
                logger.info("Используем список аккаунтов по умолчанию")
                accounts_to_track = [
                    "Defi0xJeff",
                    "elonmusk",
                    "OpenAI"
                ]

            print(f"\n--- Основные параметры ---")
            print(f"Период твитов: последние {HOURS_FILTER} часа")
            print(f"Срок действия кэша: {CACHE_DURATION} час")
            print(f"Максимальное количество твитов: {MAX_TWEETS}")
            print(f"Принудительное обновление: {'ДА' if FORCE_REFRESH else 'НЕТ'}")
            print(f"Извлечение полных статей: {'ДА' if EXTRACT_ARTICLES else 'НЕТ'}")
            print(f"Извлечение полных твитов: {'ДА' if EXTRACT_FULL_TWEETS else 'НЕТ'}")
            print(f"Извлечение всех ссылок: {'ДА' if EXTRACT_LINKS else 'НЕТ'}")
            print(f"Аккаунты для отслеживания: {', '.join('@' + account for account in accounts_to_track)}")

            logger.info(f"Параметры: период={HOURS_FILTER}ч, кэш={CACHE_DURATION}ч, макс.твитов={MAX_TWEETS}, " +
                        f"обновление={FORCE_REFRESH}, статьи={EXTRACT_ARTICLES}, полные твиты={EXTRACT_FULL_TWEETS}, " +
                        f"ссылки={EXTRACT_LINKS}, аккаунтов={len(accounts_to_track)}")

            all_results = []

            # Обрабатываем каждый аккаунт
            for username in accounts_to_track:
                print(f"\n=== Обработка аккаунта @{username} ===")
                logger.info(f"Начало обработки аккаунта @{username}")

                # Получаем твиты пользователя
                user_data = deps['get_tweets_with_selenium'](
                    username,
                    driver,
                    db_connection,
                    max_tweets=MAX_TWEETS,
                    use_cache=True,
                    cache_duration_hours=CACHE_DURATION,
                    time_filter_hours=HOURS_FILTER,
                    force_refresh=FORCE_REFRESH,
                    extract_articles=EXTRACT_ARTICLES,
                    extract_full_tweets=EXTRACT_FULL_TWEETS,
                    extract_links=EXTRACT_LINKS,
                    dependencies=deps,  # Передаем словарь с функциями
                    html_cache_dir=HTML_CACHE_DIR  # Добавляем этот параметр
                )

                # Проверяем, что результат содержит твиты
                has_content = (user_data.get("tweets", []))
                if has_content:
                    all_results.append(user_data)
                    print(f"Найдено {len(user_data['tweets'])} твитов от @{username}")
                    logger.info(f"Найдено {len(user_data['tweets'])} твитов от @{username}")
                else:
                    print(f"Нет твитов от @{username} за последние {HOURS_FILTER} часа")
                    logger.info(f"Нет твитов от @{username} за последние {HOURS_FILTER} часа")

                print(f"=== Завершена обработка @{username} ===\n")
                logger.info(f"Завершена обработка @{username}")

            # Вывод результатов
            print("\n===== РЕЗУЛЬТАТЫ =====\n")
            logger.info("Формирование результатов")

            if not all_results:
                print(f"Не найдено твитов за последние {HOURS_FILTER} часа от отслеживаемых аккаунтов.")
                logger.warning(f"Не найдено твитов за последние {HOURS_FILTER} часа от отслеживаемых аккаунтов.")
            else:
                # Отображаем результаты
                deps['display_results_summary'](all_results, HOURS_FILTER, IMAGES_DIR)

                # Генерируем статистику
                stats = deps['generate_tweet_statistics'](all_results)

                # Если есть подключение к БД, получаем статистику базы данных
                if db_connection:
                    db_stats = deps['generate_database_statistics'](db_connection)

                    # Выводим статистику базы данных
                    print("\n--- Информация о базе данных ---")
                    for category, count in db_stats.items():
                        print(f"- {category}: {count}")

            # Закрываем соединение с базой данных после каждого цикла
            if db_connection and hasattr(db_connection, 'is_connected') and db_connection.is_connected():
                db_connection.close()
                print("Соединение с базой данных закрыто")
                logger.info("Соединение с базой данных закрыто")

            print("\n=== ИТЕРАЦИЯ ЗАВЕРШЕНА, НАЧИНАЮ СЛЕДУЮЩУЮ ===")
            logger.info("Итерация завершена, начинаю следующую")
            
            # Небольшая пауза между итерациями
            time.sleep(5)

    finally:
        # Закрываем браузер при выходе из программы
        print("\n--- Завершение работы ---")
        logger.info("Завершение работы скрапера")

        if driver:
            driver.quit()
            print("Браузер закрыт")
            logger.info("Браузер закрыт")

        if db_connection and hasattr(db_connection, 'is_connected') and db_connection.is_connected():
            db_connection.close()
            print("Соединение с базой данных закрыто")
            logger.info("Соединение с базой данных закрыто")

        print("\n=== СКРИПТ ЗАВЕРШИЛ РАБОТУ ===")
        logger.info("СКРИПТ ЗАВЕРШИЛ РАБОТУ")


if __name__ == "__main__":
    main()