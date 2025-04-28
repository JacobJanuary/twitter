#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Основной модуль с улучшенными утилитами для парсера Twitter.
Импортирует функции из специализированных модулей и предоставляет единый интерфейс.
(Функционал обработки статей полностью удален)
"""

import os
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='twitter_scraper.log'
)
logger = logging.getLogger('twitter_scraper')

# Проверяем наличие необходимых директорий
required_dirs = [
    "twitter_cache",
    # "twitter_article_cache", # Удалено
    "twitter_links_cache",
    "twitter_html_cache"
]

for directory in required_dirs:
    os.makedirs(directory, exist_ok=True)
    logger.debug(f"Проверена директория: {directory}")

# Импорт функций для работы с ссылками
try:
    from twitter_scraper_links_utils import (
        extract_all_links_from_tweet,
        save_links_to_db,
        is_tweet_truncated,
        get_full_tweet_text
    )

    logger.info("Импортированы функции для работы с ссылками")
except ImportError as e:
    logger.error(f"Ошибка при импорте функций для работы с ссылками: {e}")


    # Заглушки для функций
    def extract_all_links_from_tweet(tweet_element, username, expand_first=True):
        logger.warning("Используется заглушка extract_all_links_from_tweet")
        return {"external_urls": [], "mentions": [], "hashtags": [], "media_urls": []}


    def save_links_to_db(connection, tweet_db_id, links):
        logger.warning("Используется заглушка save_links_to_db")
        return False


    def is_tweet_truncated(tweet_element):
        logger.warning("Используется заглушка is_tweet_truncated")
        return False


    def get_full_tweet_text(driver, tweet_url, max_attempts=3):
        logger.warning("Используется заглушка get_full_tweet_text")
        return ""

# Импорт функций для работы со статьями - Полностью Удалено
# ... (весь блок try/except и заглушки удалены) ...

# Импорт функций для работы с ретвитами
try:
    from twitter_scraper_retweet_utils import (
        extract_retweet_info_enhanced,
        extract_retweet_info_basic,
        get_author_info
    )

    logger.info("Импортированы функции для работы с ретвитами")
except ImportError as e:
    logger.error(f"Ошибка при импорте функций для работы с ретвитами: {e}")


    # Заглушки для функций
    def extract_retweet_info_enhanced(tweet_element):
        logger.warning("Используется заглушка extract_retweet_info_enhanced")
        return {"is_retweet": False, "original_author": None}


    def extract_retweet_info_basic(tweet_element):
        logger.warning("Используется заглушка extract_retweet_info_basic")
        return {"is_retweet": False, "original_author": None}


    def get_author_info(tweet_element):
        logger.warning("Используется заглушка get_author_info")
        return {"username": None, "display_name": None, "verified": False}

# Логируем успешную инициализацию
logger.info("Модуль twitter_scraper_enhanced_utils инициализирован успешно (без функционала статей)")

# Заглушка для process_article_from_tweet, если она где-то еще вызывается (хотя не должна)
def process_article_from_tweet(*args, **kwargs):
    logger.debug("Вызвана заглушка process_article_from_tweet (функционал статей удален).")
    return None

