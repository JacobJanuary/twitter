#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для статистики и отображения результатов Twitter скрапера.
Уточнен вывод для ретвитов.
(Функционал статистики изображений, ссылок и статей удален)
"""

import os
import logging
from mysql.connector import Error

# Настройка логирования
logger = logging.getLogger('twitter_scraper.stats')
# Добавляем базовый обработчик, если он еще не настроен в core
if not logger.handlers:
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def generate_tweet_statistics(results):
    """
    Генерирует статистику по собранным твитам (только твиты и ретвиты)
    """
    # (Без изменений по сравнению с v2)
    logger.info("Генерация статистики по твитам")
    stats = {}
    try:
        total_tweets = sum(len(user.get('tweets', [])) for user in results if isinstance(user, dict))
        stats['total_tweets'] = total_tweets
        total_retweets = sum(
            sum(1 for tweet in user.get('tweets', []) if isinstance(tweet, dict) and tweet.get('is_retweet'))
            for user in results if isinstance(user, dict)
        )
        stats['total_retweets'] = total_retweets
        stats['total_accounts'] = len(results)
        logger.info(f"Статистика сгенерирована: {total_tweets} твитов/ретвитов, {total_retweets} ретвитов")
        return stats
    except Exception as e:
        logger.error(f"Ошибка при генерации статистики: {e}")
        return {}


def generate_database_statistics(db_connection):
    """
    Генерирует статистику базы данных (только таблицы users и tweets)
    """
    # (Без изменений по сравнению с v2)
    logger.info("Генерация статистики базы данных")
    db_stats = {}
    if not db_connection or not db_connection.is_connected():
        logger.warning("Нет подключения к БД для генерации статистики")
        return {"Ошибка": "Нет подключения к БД"}
    try:
        cursor = db_connection.cursor()
        tables = [{"name": "users", "label": "Пользователей"}, {"name": "tweets", "label": "Твитов/Ретвитов"}]
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table['name']}")
                count = cursor.fetchone()[0]
                db_stats[table['label']] = count
                logger.info(f"В таблице {table['name']} найдено {count} записей")
            except Error as e:
                if e.errno == 1146: logger.warning(f"Таблица {table['name']} не найдена в БД.")
                else: logger.error(f"Не удалось получить данные из таблицы {table['name']}: {e}")
                db_stats[table['label']] = "Н/Д"
        cursor.close()
        return db_stats
    except Exception as e:
        logger.error(f"Ошибка при генерации статистики базы данных: {e}")
        return {}


def display_results_summary(results, time_filter_hours):
    """
    Отображает сводку результатов работы скрапера.
    Уточняет вывод для ретвитов.
    """
    logger.info("Отображение сводки результатов")

    try:
        # Вспомогательная функция для форматирования времени (как в v2)
        def format_time_ago(iso_time_str):
            if not iso_time_str: return "неизвестно"
            try:
                from twitter_scraper_utils import format_time_ago as format_util
                return format_util(iso_time_str)
            except (ImportError, NameError, Exception):
                try:
                    from dateutil import parser
                    import datetime
                    tweet_time = parser.isoparse(iso_time_str)
                    if tweet_time.tzinfo is None: tweet_time = tweet_time.replace(tzinfo=datetime.timezone.utc)
                    now = datetime.datetime.now(datetime.timezone.utc)
                    diff = now - tweet_time
                    if diff.days > 0: return f"{diff.days} д. назад"
                    hours = diff.seconds // 3600; minutes = (diff.seconds % 3600) // 60
                    if hours > 0: return f"{hours} ч. назад"
                    if minutes > 0: return f"{minutes} мин. назад"
                    return "только что"
                except: return iso_time_str.replace('T', ' ').split('.')[0]

        # Выводим информацию о каждом пользователе и его твитах
        for user_result in results:
            if not isinstance(user_result, dict): continue
            user_name = user_result.get('name', 'Unknown')
            user_username = user_result.get('username', 'unknown')
            print(f"\n--- {user_name} (@{user_username}) ---")
            logger.info(f"Результаты для пользователя @{user_username}")

            tweets = user_result.get('tweets', [])
            if tweets:
                print("\nСвежие твиты/ретвиты:")
                for tweet in tweets:
                    if not isinstance(tweet, dict): continue
                    try:
                        # Дата создания ОРИГИНАЛА (если ретвит)
                        time_str = format_time_ago(tweet.get("created_at", ""))
                        retweet_prefix = ""
                        original_info = ""

                        if tweet.get("is_retweet"):
                            original_author = tweet.get('original_author', 'unknown')
                            retweet_prefix = f"🔄 Ретвит @{user_username} (от @{original_author}): "
                            original_url = tweet.get('original_tweet_url', '')
                            if original_url:
                                 original_info = f"\n   Оригинал: {original_url}"
                        else:
                             retweet_prefix = f"👤 Твит @{user_username}: " # Указываем автора твита

                        # Текст ОРИГИНАЛА (если ретвит)
                        print(f"[{time_str}] {retweet_prefix}{tweet.get('text', '')}")
                        # URL РЕТВИТА (или твита)
                        print(f"   URL: {tweet.get('url', '')}{original_info}")

                        # Статистика ОРИГИНАЛА (если ретвит)
                        stats = tweet.get("stats", {})
                        print(f"   Статистика (оригинала): 👍 {stats.get('likes', 0)} | 🔄 {stats.get('retweets', 0)} | 💬 {stats.get('replies', 0)}")

                        print("-" * 20) # Разделитель
                    except Exception as e:
                        logger.error(f"Ошибка при выводе информации о твите {tweet.get('url', '')}: {e}")
            else:
                 print("Нет свежих твитов/ретвитов для отображения.")

        # Вывод общей статистики (без изменений)
        stats = generate_tweet_statistics(results)
        print("\n===== ОБЩАЯ СТАТИСТИКА =====")
        print(f"\nОбработано аккаунтов: {stats.get('total_accounts', 0)}")
        print(f"Всего получено свежих твитов/ретвитов (за {time_filter_hours} ч): {stats.get('total_tweets', 0)}")
        print(f"Из них ретвитов (записей): {stats.get('total_retweets', 0)}")

        logger.info("Сводка результатов отображена успешно")

    except Exception as e:
        logger.error(f"Ошибка при отображении сводки результатов: {e}")
        print(f"Ошибка при отображении результатов: {e}")

