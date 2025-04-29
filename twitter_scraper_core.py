#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Основной модуль скрапера Twitter.
API вызовы отключены. Обработка ретвитов изменена.
Оптимизирована работа с БД (пакетная вставка/обновление).
"""

import os
import sys
import json
import time
import logging
import re
from selenium import webdriver

# Настройка логирования
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler = logging.FileHandler('twitter_scraper.log', mode='a', encoding='utf-8')
log_handler.setFormatter(log_formatter)
logger = logging.getLogger('twitter_scraper')
logger.setLevel(logging.INFO)
if logger.hasHandlers(): logger.handlers.clear()
logger.addHandler(log_handler)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

# Настройки
CHROME_PROFILE_PATH = "/Users/evgeniyyanvarskiy/Library/Application Support/Google/Chrome/Profile 1/" # Пример для macOS
CACHE_DIR = "twitter_cache"
HTML_CACHE_DIR = "twitter_html_cache"

# Создаем директории
for directory in [CACHE_DIR, HTML_CACHE_DIR]:
    os.makedirs(directory, exist_ok=True)

# Настройки MySQL
MYSQL_CONFIG = {
    'host': '217.154.19.224',
    'database': 'twitter_data',
    'user': 'elcrypto',
    'password': 'LohNeMamont@!21',
    'port': 3306
}


def initialize_dependencies():
    """Импортирует и возвращает зависимости."""
    dependencies = {}
    logger.info("Инициализация зависимостей...")
    try:
        # Базовые утилиты (включая НОВУЮ функцию пакетной вставки)
        from twitter_scraper_utils import (
            debug_print, initialize_mysql, save_user_to_db, save_tweets_batch_to_db, # <-- ИЗМЕНЕНО
            parse_twitter_date, filter_recent_tweets, format_time_ago,
            initialize_browser, manual_auth_with_prompt,
            extract_tweet_stats
        )
        utils_funcs = {
            'debug_print': debug_print, 'initialize_mysql': initialize_mysql,
            'save_user_to_db': save_user_to_db, 'save_tweets_batch_to_db': save_tweets_batch_to_db, # <-- ИЗМЕНЕНО
            'parse_twitter_date': parse_twitter_date, 'filter_recent_tweets': filter_recent_tweets,
            'format_time_ago': format_time_ago, 'initialize_browser': initialize_browser,
            'manual_auth_with_prompt': manual_auth_with_prompt, 'extract_tweet_stats': extract_tweet_stats
        }
        dependencies.update(utils_funcs)
        logger.debug("Базовые утилиты импортированы.")

        # Утилиты для текста твитов
        from twitter_scraper_links_utils import is_tweet_truncated, get_full_tweet_text
        dependencies['is_tweet_truncated'] = is_tweet_truncated
        dependencies['get_full_tweet_text'] = get_full_tweet_text
        logger.debug("Утилиты для текста твитов импортированы.")

        # Утилиты для ретвитов
        from twitter_scraper_retweet_utils import extract_retweet_info_enhanced, get_author_info
        dependencies['extract_retweet_info_enhanced'] = extract_retweet_info_enhanced
        dependencies['get_author_info'] = get_author_info
        logger.debug("Утилиты для ретвитов (enhanced) импортированы.")

        # Утилиты для сбора твитов (возвращает все собранные)
        from twitter_scraper_tweets import get_tweets_with_selenium
        dependencies['get_tweets_with_selenium'] = get_tweets_with_selenium
        logger.debug("Утилиты для сбора твитов импортированы.")

        # Утилиты для статистики
        from twitter_scraper_stats import generate_tweet_statistics, generate_database_statistics, display_results_summary
        dependencies['generate_tweet_statistics'] = generate_tweet_statistics
        dependencies['generate_database_statistics'] = generate_database_statistics
        dependencies['display_results_summary'] = display_results_summary
        logger.debug("Утилиты для статистики импортированы.")

        # API клиент (заглушки)
        from twitter_api_client import get_tweet_by_id, process_api_tweet_data
        dependencies['get_tweet_by_id'] = get_tweet_by_id
        dependencies['process_api_tweet_data'] = process_api_tweet_data
        logger.debug("API клиент (заглушки) импортирован.")

        logger.info("Импорт всех зависимостей завершен успешно")
        return dependencies

    except ImportError as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать: {e}")
        logger.critical("Убедитесь, что все файлы .py находятся в той же директории.")
        import traceback; logger.error(traceback.format_exc())
        sys.exit(1)


def load_accounts_from_file(filename="influencer_twitter.txt"):
    """Загружает аккаунты Twitter из файла"""
    # (Код без изменений)
    accounts = []
    logger.info(f"Загрузка аккаунтов из файла: {filename}")
    try:
        with open(filename, 'r', encoding='utf-8') as f: lines = f.readlines()
        processed_usernames = set()
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'): continue
            username = None
            if line.startswith('http://') or line.startswith('https://'):
                try:
                    clean_url = line.split('?')[0].split('#')[0].rstrip('/')
                    parts = clean_url.split('/')
                    if len(parts) > 0:
                         potential_username = parts[-1]
                         if potential_username and re.match(r'^[A-Za-z0-9_]{1,15}$', potential_username): username = potential_username
                         else: logger.warning(f"Не валидный username из URL '{line}' в строке {line_num}")
                    else: logger.warning(f"Некорректный URL '{line}' в строке {line_num}")
                except Exception as e: logger.warning(f"Ошибка извлечения username из URL '{line}' ({line_num}): {e}")
            else:
                potential_username = line.lstrip('@')
                if potential_username and re.match(r'^[A-Za-z0-9_]{1,15}$', potential_username): username = potential_username
                else: logger.warning(f"Некорректный формат username '{line}' в строке {line_num}")
            if username and username.lower() not in processed_usernames:
                 accounts.append(username); processed_usernames.add(username.lower())
            elif not username and line: logger.warning(f"Пропущена строка {line_num}: '{line}'")
        logger.info(f"Загружено {len(accounts)} уникальных аккаунтов из {filename}")
        return accounts
    except FileNotFoundError: logger.error(f"Файл {filename} не найден!"); return []
    except Exception as e: logger.error(f"Ошибка чтения файла {filename}: {e}"); return []


def main():
    """Основная функция скрапера"""
    logger.info("="*30 + " ЗАПУСК СКРАПЕРА TWITTER (BATCH DB MODE) " + "="*30)

    deps = initialize_dependencies()

    # Проверка профиля Chrome
    effective_chrome_path = None
    if CHROME_PROFILE_PATH:
         abs_profile_path = os.path.abspath(CHROME_PROFILE_PATH)
         if os.path.exists(abs_profile_path) and os.path.isdir(abs_profile_path):
              logger.info(f"Найден профиль Chrome: {abs_profile_path}"); effective_chrome_path = abs_profile_path
         else: logger.warning(f"Профиль Chrome НЕ НАЙДЕН: {abs_profile_path}. Используется временный.")
    else: logger.info("Профиль Chrome не указан. Используется временный.")

    # Подключение к MySQL
    logger.info("--- Подключение к MySQL ---")
    db_connection = None
    try:
        db_connection = deps['initialize_mysql'](MYSQL_CONFIG)
        if db_connection and db_connection.is_connected():
            logger.info("Успешное подключение к MySQL")
            db_connection.autocommit = False # Управляем транзакциями вручную
            logger.info("Autocommit отключен для MySQL соединения.")
        else:
            if not (db_connection and db_connection.is_connected()):
                 logger.warning("Не удалось подключиться к MySQL.")
                 answer = input("Продолжить без сохранения в БД? (да/нет): ")
                 if answer.lower() not in ['да', 'yes', 'y', 'д']: logger.info("Отмена запуска без MySQL."); return
                 db_connection = None
            else: logger.error("initialize_mysql вернула некорректный результат."); db_connection = None
    except Exception as e: logger.error(f"Критическая ошибка инициализации MySQL: {e}"); db_connection = None

    # Параметры скрапинга
    HOURS_FILTER = 24
    CACHE_DURATION = 1
    MAX_TWEETS_DISPLAY = 15 # Лимит для отображения
    FORCE_REFRESH = True
    EXTRACT_FULL_TWEETS = True

    accounts_to_track = load_accounts_from_file("influencer_twitter.txt")
    if not accounts_to_track:
        logger.critical("Список аккаунтов пуст. Завершение.");
        if db_connection and db_connection.is_connected(): db_connection.close()
        return

    logger.info("--- Основные параметры скрапинга ---")
    logger.info(f"Период для фильтрации твитов (отображение): последние {HOURS_FILTER} часа")
    logger.info(f"Срок действия кэша: {CACHE_DURATION} час")
    logger.info(f"Макс. твитов на аккаунт (для отображения): {MAX_TWEETS_DISPLAY}")
    logger.info(f"Принудительное обновление (игнорировать кэш): {'ДА' if FORCE_REFRESH else 'НЕТ'}")
    logger.info(f"Извлечение полных текстов: {'ДА' if EXTRACT_FULL_TWEETS else 'НЕТ'}")
    logger.info(f"Аккаунты ({len(accounts_to_track)}): {', '.join('@' + a for a in accounts_to_track)}")

    driver = None
    try:
        logger.info("--- Инициализация браузера Chrome ---")
        driver = deps['initialize_browser'](effective_chrome_path)
        if not driver:
            logger.critical("Не удалось инициализировать браузер.")
            if db_connection and db_connection.is_connected(): db_connection.close()
            return
        logger.info("Браузер Chrome инициализирован")

        logger.info("--- Авторизация в Twitter ---")
        auth_result = deps['manual_auth_with_prompt'](driver)
        if not auth_result: logger.warning("Авторизация не подтверждена.")
        else: logger.info(f"Авторизация подтверждена.")

        all_results_for_display = [] # Список для хранения данных для итоговой сводки
        start_time_total = time.time()

        # --- Основной цикл обработки аккаунтов ---
        for i, username in enumerate(accounts_to_track, 1):
            logger.info(f"\n=== Обработка аккаунта {i}/{len(accounts_to_track)}: @{username} ===")
            start_time_user = time.time()
            collected_data = None # Результат от get_tweets_with_selenium

            try:
                # --- Шаг 1: Сбор всех твитов для пользователя ---
                collected_data = deps['get_tweets_with_selenium'](
                    username=username,
                    driver=driver,
                    db_connection=db_connection, # Нужно для save_user_to_db
                    max_tweets=MAX_TWEETS_DISPLAY, # Этот параметр теперь меньше влияет на сбор
                    use_cache=not FORCE_REFRESH,
                    cache_duration_hours=CACHE_DURATION,
                    time_filter_hours=HOURS_FILTER, # Фильтр кэша все еще нужен
                    force_refresh=FORCE_REFRESH,
                    extract_full_tweets=EXTRACT_FULL_TWEETS,
                    dependencies=deps,
                    html_cache_dir=HTML_CACHE_DIR
                )

                # Проверяем, что данные получены корректно
                if not collected_data or not isinstance(collected_data, dict) or "tweets" not in collected_data:
                     logger.error(f"Не удалось получить корректные данные для @{username}. Пропускаем.")
                     continue # Переходим к следующему пользователю

                all_user_tweets = collected_data.get("tweets", [])
                user_info = collected_data.get("user_info", {"username": username, "name": username})
                # user_id получаем из collected_data, если пользователь был сохранен
                user_id_for_db = collected_data.get("user_id")

                if not all_user_tweets:
                    logger.info(f"Не найдено твитов для @{username} в результате сбора (возможно, из кэша).")
                else:
                    logger.info(f"Собрано {len(all_user_tweets)} твитов/ретвитов для @{username}.")

                    # --- Шаг 2: Пакетное сохранение в БД ---
                    if db_connection and db_connection.is_connected() and user_id_for_db:
                        logger.info(f"Запуск пакетного сохранения {len(all_user_tweets)} твитов для @{username} (user_id: {user_id_for_db})...")
                        save_result = deps['save_tweets_batch_to_db'](db_connection, all_user_tweets)

                        if save_result is not None:
                            logger.info(f"Пакетное сохранение для @{username} завершено. Затронуто строк: {save_result}.")
                            # Коммит транзакции ПОСЛЕ успешной пакетной вставки
                            try:
                                db_connection.commit()
                                logger.info(f"Данные для @{username} сохранены в БД (COMMIT выполнен).")
                            except Exception as commit_err:
                                logger.error(f"Ошибка при COMMIT данных для @{username}: {commit_err}")
                                try:
                                     logger.warning(f"Попытка ROLLBACK из-за ошибки COMMIT для @{username}")
                                     db_connection.rollback()
                                except Exception as rb_err: logger.error(f"Ошибка ROLLBACK: {rb_err}")
                        else:
                            logger.error(f"Ошибка при пакетном сохранении данных для @{username}. Попытка ROLLBACK...")
                            try: db_connection.rollback()
                            except Exception as rb_err: logger.error(f"Ошибка ROLLBACK: {rb_err}")
                    elif not db_connection:
                         logger.info("Работа без БД, сохранение пакета пропущено.")
                    elif not user_id_for_db:
                         logger.error(f"Не удалось получить user_id для @{username}, пакетное сохранение невозможно.")


                # --- Шаг 3: Подготовка данных для отображения ---
                # Фильтруем собранные (или из кэша) твиты по времени для сводки
                recent_tweets_for_display = deps['filter_recent_tweets'](all_user_tweets, HOURS_FILTER)
                logger.info(f"Отфильтровано {len(recent_tweets_for_display)} свежих твитов для отображения.")

                # Сохраняем результат для финальной сводки
                display_data = {
                    "username": user_info.get("username"),
                    "name": user_info.get("name"),
                    # Ограничиваем количество для отображения
                    "tweets": recent_tweets_for_display[:MAX_TWEETS_DISPLAY]
                }
                all_results_for_display.append(display_data)

                end_time_user = time.time()
                logger.info(f"Завершена обработка @{username} за {end_time_user - start_time_user:.2f} сек.")


            except Exception as user_proc_err:
                 logger.error(f"Ошибка при обработке пользователя @{username}: {user_proc_err}")
                 import traceback; logger.error(traceback.format_exc())
                 if db_connection and db_connection.is_connected():
                      try: logger.warning(f"Попытка ROLLBACK из-за ошибки @{username}"); db_connection.rollback()
                      except Exception as rb_err: logger.error(f"Ошибка ROLLBACK: {rb_err}")
                 logger.info(f"Продолжаем со следующим пользователем после ошибки с @{username}")
                 continue

            # Пауза
            pause_duration = 2
            logger.debug(f"Пауза {pause_duration} сек...")
            time.sleep(pause_duration)

        # --- Конец цикла обработки аккаунтов ---

        end_time_total = time.time()
        logger.info(f"\nЗавершена обработка всех {len(accounts_to_track)} аккаунтов за {end_time_total - start_time_total:.2f} сек.")

        # --- Отображение результатов и статистики ---
        logger.info("\n" + "="*20 + " РЕЗУЛЬТАТЫ СБОРА " + "="*20)
        if not all_results_for_display:
            logger.warning(f"Не найдено свежих твитов для отображения ({HOURS_FILTER} ч).")
            print(f"\nНе найдено твитов для отображения за последние {HOURS_FILTER} часа.")
        else:
            # Отображаем сводку по отфильтрованным данным
            deps['display_results_summary'](all_results_for_display, HOURS_FILTER)

            # Статистика сбора (по данным для отображения)
            stats = deps['generate_tweet_statistics'](all_results_for_display)
            logger.info(f"Общая статистика (отображено): {stats}")

            # Статистика БД
            if db_connection and db_connection.is_connected():
                db_stats = deps['generate_database_statistics'](db_connection)
                logger.info(f"Статистика БД после завершения: {db_stats}")
                print("\n--- Информация о базе данных ---")
                if isinstance(db_stats, dict):
                     for category, count in db_stats.items(): print(f"- {category}: {count}")
                else: print("Не удалось получить статистику БД.")
            elif not db_connection: print("\nСтатистика БД недоступна (работа без БД).")


    except KeyboardInterrupt:
        logger.warning("Выполнение прервано пользователем (Ctrl+C)")
        print("\nПрервано пользователем.")
        if db_connection and db_connection.is_connected():
             try: logger.warning("Попытка COMMIT перед выходом (Ctrl+C)..."); db_connection.commit(); logger.info("COMMIT выполнен.")
             except Exception as final_commit_err: logger.error(f"Ошибка финального COMMIT: {final_commit_err}"); db_connection.rollback()

    except Exception as e:
         logger.critical(f"Критическая ошибка в главном цикле: {e}")
         import traceback; logger.error(traceback.format_exc())
         print(f"\nПроизошла критическая ошибка: {e}")
         if db_connection and db_connection.is_connected():
              try: logger.warning("Попытка ROLLBACK из-за крит. ошибки..."); db_connection.rollback()
              except Exception as critical_rb_err: logger.error(f"Ошибка ROLLBACK: {critical_rb_err}")

    finally:
        # --- Завершение работы ---
        logger.info("--- Завершение работы скрапера ---")
        if driver:
            try: driver.quit(); logger.info("Браузер Chrome закрыт")
            except Exception as e: logger.error(f"Ошибка закрытия браузера: {e}")
        if db_connection and hasattr(db_connection, 'is_connected') and db_connection.is_connected():
            try: db_connection.close(); logger.info("Соединение с MySQL закрыто")
            except Exception as e: logger.error(f"Ошибка закрытия соединения с БД: {e}")

        logger.info("="*30 + " ЗАВЕРШЕНО " + "="*30)
        print("\n=== СКРИПТ ЗАВЕРШИЛ РАБОТУ ===")

if __name__ == "__main__":
    main()
