#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для статистики и отображения результатов Twitter скрапера
(Функционал статистики изображений, ссылок и статей удален)
"""

import os
import logging
from mysql.connector import Error

# Настройка логирования
logger = logging.getLogger('twitter_scraper.stats')


def generate_tweet_statistics(results):
    """
    Генерирует статистику по собранным твитам (только твиты и ретвиты)

    Args:
        results: Список с результатами сбора твитов

    Returns:
        dict: Словарь со статистическими показателями
    """
    logger.info("Генерация статистики по твитам")
    stats = {}

    try:
        # Считаем общее количество твитов
        total_tweets = sum(len(user.get('tweets', [])) for user in results)
        stats['total_tweets'] = total_tweets

        # Считаем количество ретвитов
        total_retweets = sum(
            sum(1 for tweet in user.get('tweets', []) if tweet.get('is_retweet'))
            for user in results
        )
        stats['total_retweets'] = total_retweets

        # --- Удален подсчет изображений, статей, ссылок ---
        # total_images = ...
        # stats['total_images'] = total_images
        # total_articles = ...
        # stats['total_articles'] = total_articles
        # total_full_tweets = ...
        # stats['total_full_tweets'] = total_full_tweets
        # total_links = ...
        # stats['total_external_links'] = total_links
        # total_mentions = ...
        # stats['total_mentions'] = total_mentions
        # total_hashtags = ...
        # stats['total_hashtags'] = total_hashtags

        # Считаем количество обработанных аккаунтов
        stats['total_accounts'] = len(results)

        logger.info(f"Статистика сгенерирована: {total_tweets} твитов, {total_retweets} ретвитов")

        return stats

    except Exception as e:
        logger.error(f"Ошибка при генерации статистики: {e}")
        return {}


def generate_database_statistics(db_connection):
    """
    Генерирует статистику базы данных (только таблицы users и tweets)

    Args:
        db_connection: Соединение с базой данных MySQL

    Returns:
        dict: Словарь со статистическими показателями из базы данных
    """
    logger.info("Генерация статистики базы данных")
    db_stats = {}

    if not db_connection or not db_connection.is_connected():
        logger.warning("Нет подключения к БД для генерации статистики")
        return {"Ошибка": "Нет подключения к БД"}

    try:
        cursor = db_connection.cursor()

        # Список таблиц для проверки (только users и tweets)
        tables = [
            {"name": "users", "label": "Пользователей"},
            {"name": "tweets", "label": "Твитов"},
            # {"name": "images", "label": "Изображений"}, # Удалено
            # {"name": "articles", "label": "Статей"}, # Удалено
            # {"name": "tweet_links", "label": "Ссылок из твитов"}, # Удалено
            # {"name": "article_links", "label": "Ссылок из статей"} # Удалено
        ]

        # Подсчет записей в каждой таблице
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table['name']}")
                count = cursor.fetchone()[0]
                db_stats[table['label']] = count
                logger.info(f"В таблице {table['name']} найдено {count} записей")
            except Error as e:
                # Логируем ошибку, если таблица не найдена (это нормально, если ее не создавали)
                if e.errno == 1146: # ER_NO_SUCH_TABLE
                     logger.warning(f"Таблица {table['name']} не найдена в БД.")
                else:
                     logger.error(f"Не удалось получить данные из таблицы {table['name']}: {e}")
                db_stats[table['label']] = "Н/Д"

        # --- Удалена детализация по ссылкам и статьям ---
        # try:
        #     cursor.execute("SELECT link_type, COUNT(*) FROM tweet_links GROUP BY link_type")
        #     # ...
        # except Error as e:
        #     # ...
        #
        # try:
        #     cursor.execute(""" SELECT source_domain, COUNT(*) ... FROM articles ... """)
        #     # ...
        # except Error as e:
        #     # ...

        cursor.close() # Закрываем курсор
        return db_stats

    except Exception as e:
        logger.error(f"Ошибка при генерации статистики базы данных: {e}")
        return {}


def display_results_summary(results, time_filter_hours, images_dir=None): # images_dir больше не обязателен
    """
    Отображает сводку результатов работы скрапера (без изображений, ссылок, статей)

    Args:
        results: Список с результатами сбора твитов
        time_filter_hours: Фильтр по времени публикации твитов в часах
        images_dir: Директория для сохранения изображений (больше не используется)
    """
    logger.info("Отображение сводки результатов")

    try:
        # Вспомогательная функция для форматирования времени
        def format_time_ago(iso_time_str):
            if not iso_time_str: return "неизвестно"
            try:
                # Пытаемся импортировать и использовать основную функцию форматирования
                from twitter_scraper_utils import format_time_ago as format_util
                return format_util(iso_time_str)
            except (ImportError, NameError, Exception):
                # Резервное базовое форматирование
                try:
                    from dateutil import parser
                    import datetime
                    tweet_time = parser.isoparse(iso_time_str)
                    now = datetime.datetime.now(datetime.timezone.utc)
                    diff = now - tweet_time
                    if diff.days > 0: return f"{diff.days} д. назад"
                    hours = diff.seconds // 3600
                    if hours > 0: return f"{hours} ч. назад"
                    minutes = (diff.seconds % 3600) // 60
                    if minutes > 0: return f"{minutes} мин. назад"
                    return "только что"
                except:
                     return iso_time_str.replace('T', ' ').split('.')[0] # Самый простой вариант

        # Выводим информацию о каждом пользователе и его твитах
        for user_result in results:
            if not isinstance(user_result, dict):
                 logger.warning(f"Некорректный формат результата пользователя: {user_result}")
                 continue

            print(f"\n--- {user_result.get('name', 'Unknown')} (@{user_result.get('username', 'unknown')}) ---")
            logger.info(f"Результаты для пользователя @{user_result.get('username', 'unknown')}")

            tweets = user_result.get('tweets', [])
            if tweets:
                print("\nТвиты:")
                for tweet in tweets:
                    if not isinstance(tweet, dict):
                         logger.warning(f"Некорректный формат твита: {tweet}")
                         continue
                    try:
                        time_str = format_time_ago(tweet.get("created_at", ""))
                        retweet_prefix = ""
                        if tweet.get("is_retweet"):
                            retweet_prefix = f"🔄 Ретвит от @{tweet.get('original_author', 'unknown')}: "

                        print(f"[{time_str}] {retweet_prefix}{tweet.get('text', '')}")
                        # print(f"Дата (ISO): {tweet.get('created_at', '')}") # Можно убрать для краткости
                        print(f"URL: {tweet.get('url', '')}")

                        stats = tweet.get("stats", {})
                        print(
                            f"Статистика: 👍 {stats.get('likes', 0)} | 🔄 {stats.get('retweets', 0)} | 💬 {stats.get('replies', 0)}")

                        # --- Удален вывод изображений, ссылок, статей ---
                        # images = tweet.get("images", [])
                        # if images: ...
                        # if tweet.get("links"): ...
                        # if tweet.get("article"): ...
                        # if tweet.get("is_truncated"): ...

                        print("-" * 20) # Разделитель между твитами
                    except Exception as e:
                        logger.error(f"Ошибка при выводе информации о твите {tweet.get('url', '')}: {e}")
            else:
                 print("Нет свежих твитов для отображения.")


        # Вывод общей статистики
        stats = generate_tweet_statistics(results)

        print("\n===== ОБЩАЯ СТАТИСТИКА =====")
        print(f"\nОбработано аккаунтов: {stats.get('total_accounts', 0)}")
        print(f"Всего получено свежих твитов (за {time_filter_hours} ч): {stats.get('total_tweets', 0)}")
        print(f"Из них ретвитов: {stats.get('total_retweets', 0)}")
        # --- Удален вывод статистики по изображениям, статьям, ссылкам ---
        # print(f"Всего сохранено изображений: {stats.get('total_images', 0)}")
        # print(f"Всего извлечено статей: {stats.get('total_articles', 0)}")
        # print(f"Всего обработано длинных твитов: {stats.get('total_full_tweets', 0)}")
        # print(f"Всего извлечено внешних ссылок: {stats.get('total_external_links', 0)}")
        # print(f"Всего упоминаний: {stats.get('total_mentions', 0)}")
        # print(f"Всего хэштегов: {stats.get('total_hashtags', 0)}")
        # print(f"Изображения сохранены в директории: {os.path.abspath(images_dir)}") # Удалено

        logger.info("Сводка результатов отображена успешно")

    except Exception as e:
        logger.error(f"Ошибка при отображении сводки результатов: {e}")
        print(f"Ошибка при отображении результатов: {e}")

