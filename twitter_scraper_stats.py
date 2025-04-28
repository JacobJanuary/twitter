#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для статистики и отображения результатов Twitter скрапера
Содержит функции для генерации статистики и отображения результатов
(Функционал обработки статей удален)
"""

import os
import logging
from mysql.connector import Error

# Настройка логирования
logger = logging.getLogger('twitter_scraper.stats')


def generate_tweet_statistics(results):
    """
    Генерирует статистику по собранным твитам

    Args:
        results: Список с результатами сбора твитов

    Returns:
        dict: Словарь с различными статистическими показателями
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

        # Считаем количество статей - Удалено
        # total_articles = sum(
        #     sum(1 for tweet in user.get('tweets', []) if tweet.get('article'))
        #     for user in results
        # )
        # stats['total_articles'] = total_articles

        # Считаем количество обработанных длинных твитов
        total_full_tweets = sum(
            sum(1 for tweet in user.get('tweets', []) if tweet.get('is_truncated'))
            for user in results
        )
        stats['total_full_tweets'] = total_full_tweets

        # Считаем количество внешних ссылок
        total_links = sum(
            sum(len(tweet.get("links", {}).get("external_urls", [])) for tweet in user.get('tweets', []))
            for user in results
        )
        stats['total_external_links'] = total_links

        # Считаем количество упоминаний
        total_mentions = sum(
            sum(len(tweet.get("links", {}).get("mentions", [])) for tweet in user.get('tweets', []))
            for user in results
        )
        stats['total_mentions'] = total_mentions

        # Считаем количество хэштегов
        total_hashtags = sum(
            sum(len(tweet.get("links", {}).get("hashtags", [])) for tweet in user.get('tweets', []))
            for user in results
        )
        stats['total_hashtags'] = total_hashtags

        # Считаем общее количество аккаунтов
        stats['total_accounts'] = len(results)

        # logger.info(f"Статистика сгенерирована: {total_tweets} твитов, {total_retweets} ретвитов, " +
        #             f"{total_articles} статей, {total_full_tweets} длинных твитов") # Обновлено
        logger.info(f"Статистика сгенерирована: {total_tweets} твитов, {total_retweets} ретвитов, " +
                    f"{total_full_tweets} длинных твитов")

        return stats

    except Exception as e:
        logger.error(f"Ошибка при генерации статистики: {e}")
        return {}


def generate_database_statistics(db_connection):
    """
    Генерирует статистику базы данных

    Args:
        db_connection: Соединение с базой данных MySQL

    Returns:
        dict: Словарь с различными статистическими показателями из базы данных
    """
    logger.info("Генерация статистики базы данных")
    db_stats = {}

    try:
        cursor = db_connection.cursor()

        # Список таблиц для проверки
        tables = [
            {"name": "users", "label": "Пользователей"},
            {"name": "tweets", "label": "Твитов"},
            # {"name": "articles", "label": "Статей"}, # Удалено
            {"name": "tweet_links", "label": "Ссылок из твитов"},
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
                # Если таблицы нет (например, articles), это ожидаемо
                if e.errno == 1146: # Table doesn't exist
                     logger.info(f"Таблица {table['name']} не существует (ожидаемо).")
                     db_stats[table['label']] = 0
                else:
                    logger.warning(f"Не удалось получить данные из таблицы {table['name']}: {e}")
                    db_stats[table['label']] = "Н/Д"

        # Детализация по типам ссылок, если таблица существует
        try:
            cursor.execute("SELECT link_type, COUNT(*) FROM tweet_links GROUP BY link_type")
            link_stats = cursor.fetchall()

            for link_type, count in link_stats:
                db_stats[f"Ссылки типа '{link_type}'"] = count
                logger.info(f"Ссылок типа '{link_type}': {count}")
        except Error as e:
            if e.errno == 1146: # Table doesn't exist
                 logger.info("Таблица tweet_links не существует.")
            else:
                logger.warning(f"Не удалось получить данные о типах ссылок: {e}")

        # Топ доменов статей - Удалено
        # ... (блок try/except удален) ...

        return db_stats

    except Exception as e:
        logger.error(f"Ошибка при генерации статистики базы данных: {e}")
        return {}


def display_results_summary(results, time_filter_hours):
    """
    Отображает сводку результатов работы скрапера

    Args:
        results: Список с результатами сбора твитов
        time_filter_hours: Фильтр по времени публикации твитов в часах
    """
    logger.info("Отображение сводки результатов")

    try:
        # Вспомогательная функция для форматирования времени
        def format_time_ago(iso_time_str):
            if not iso_time_str:
                return "неизвестно"

            try:
                # Получаем функцию форматирования из глобального пространства имен
                import twitter_scraper_utils
                format_time_func = getattr(twitter_scraper_utils, 'format_time_ago', None)
                if format_time_func and callable(format_time_func):
                    return format_time_func(iso_time_str)
                else:
                    # Базовое форматирование, если функция недоступна
                    return iso_time_str.replace('T', ' ').split('.')[0]
            except Exception as e:
                logger.error(f"Ошибка при вызове format_time_ago: {e}")
                return iso_time_str

        # Выводим информацию о каждом пользователе и его твитах
        for user in results:
            print(f"\n--- {user['name']} (@{user['username']}) ---")
            logger.info(f"Результаты для пользователя @{user['username']}")

            # Выводим твиты
            if user.get('tweets', []):
                print("\nТвиты:")
                for tweet in user["tweets"]:
                    try:
                        # Форматируем время
                        time_str = format_time_ago(tweet.get("created_at", ""))

                        # Отмечаем, является ли твит ретвитом
                        retweet_prefix = ""
                        if tweet.get("is_retweet"):
                            retweet_prefix = f"🔄 Ретвит от @{tweet.get('original_author', 'unknown')}: "

                        # Выводим основную информацию о твите
                        print(f"[{time_str}] {retweet_prefix}{tweet.get('text', '')}")
                        print(f"Дата (ISO): {tweet.get('created_at', '')}")
                        print(f"URL: {tweet.get('url', '')}")

                        # Выводим статистику
                        stats = tweet.get("stats", {})
                        print(
                            f"Статистика: 👍 {stats.get('likes', 0)} | 🔄 {stats.get('retweets', 0)} | 💬 {stats.get('replies', 0)}")

                        # Выводим информацию о ссылках в твите
                        if tweet.get("links"):
                            links = tweet.get("links")

                            # Внешние ссылки
                            if links.get("external_urls"):
                                print(f"🔗 Внешние ссылки ({len(links['external_urls'])}):")
                                for url in links["external_urls"]:
                                    print(f"  - {url}")

                            # Упоминания
                            if links.get("mentions"):
                                print(f"👤 Упоминания ({len(links['mentions'])}):")
                                for mention in links["mentions"]:
                                    print(f"  - @{mention}")

                            # Хэштеги
                            if links.get("hashtags"):
                                print(f"# Хэштеги ({len(links['hashtags'])}):")
                                for hashtag in links["hashtags"]:
                                    print(f"  - #{hashtag}")

                        # Выводим информацию о статье, если есть - Удалено
                        # ... (блок if tweet.get("article") удален) ...

                        # Отмечаем, если твит был обрезан и получен полный текст
                        if tweet.get("is_truncated"):
                            print(f"📝 Получена полная версия длинного твита")

                        print("")
                    except Exception as e:
                        logger.error(f"Ошибка при выводе информации о твите: {e}")

        # Вывод статистики
        stats = generate_tweet_statistics(results)

        print("\n===== ОБЩАЯ СТАТИСТИКА =====")
        print(f"\nВсего получено: {stats.get('total_tweets', 0)} твитов")
        print(f"Из них ретвитов: {stats.get('total_retweets', 0)}")
        # print(f"Всего извлечено статей: {stats.get('total_articles', 0)}") # Удалено
        print(f"Всего обработано длинных твитов: {stats.get('total_full_tweets', 0)}")
        print(f"Всего извлечено внешних ссылок: {stats.get('total_external_links', 0)}")
        print(f"Всего упоминаний: {stats.get('total_mentions', 0)}")
        print(f"Всего хэштегов: {stats.get('total_hashtags', 0)}")
        print(f"Число аккаунтов с контентом: {stats.get('total_accounts', 0)} из {len(results)}")
        print(f"Период: последние {time_filter_hours} часа")

        logger.info("Сводка результатов отображена успешно")

    except Exception as e:
        logger.error(f"Ошибка при отображении сводки результатов: {e}")
        print(f"Ошибка при отображении результатов: {e}")

