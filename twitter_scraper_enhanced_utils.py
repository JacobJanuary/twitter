#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Основной модуль с улучшенными утилитами для парсера Twitter.
Импортирует функции из специализированных модулей и предоставляет единый интерфейс.
(Функционал ссылок и статей удален)
"""

import os
import logging

# Настройка логирования
# Убедимся, что логирование настроено один раз в core
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     filename='twitter_scraper.log'
# )
logger = logging.getLogger('twitter_scraper.enhanced_utils') # Используем имя модуля

# Проверяем наличие необходимых директорий (только базовые)
required_dirs = [
    "twitter_cache",
    # "twitter_images", # Удалено
    # "twitter_article_cache", # Удалено
    # "twitter_links_cache", # Удалено
    "twitter_html_cache" # Оставляем для отладки
]

for directory in required_dirs:
    # Проверяем существование перед созданием
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            logger.debug(f"Создана директория: {directory}")
        except OSError as e:
             logger.error(f"Не удалось создать директорию {directory}: {e}")
    else:
         logger.debug(f"Директория существует: {directory}")


# --- Импорт функций для работы с ссылками удален ---
# try:
#     from twitter_scraper_links_utils import (
#         extract_all_links_from_tweet,
#         save_links_to_db,
#         is_tweet_truncated, # Перенесено в tweets или utils, если еще нужно
#         get_full_tweet_text # Перенесено в tweets или utils, если еще нужно
#     )
#     logger.info("Импортированы функции для работы с ссылками")
# except ImportError as e:
#     logger.error(f"Ошибка при импорте функций для работы с ссылками: {e}")
#     # Заглушки больше не нужны, так как функционал удален

# --- Импорт функций для работы со статьями удален ---
# try:
#     from twitter_scraper_article_utils import (
#         process_article_from_tweet,
#         extract_article_urls_from_tweet,
#         parse_full_article,
#         save_article_to_db,
#         is_article_url
#     )
#     logger.info("Импортированы функции для работы со статьями")
# except ImportError as e:
#     logger.error(f"Ошибка при импорте функций для работы со статьями: {e}")
#     # Заглушки больше не нужны

# Импорт функций для работы с ретвитами (остается)
try:
    from twitter_scraper_retweet_utils import (
        extract_retweet_info_enhanced,
        extract_retweet_info_basic,
        get_author_info
    )
    logger.info("Импортированы функции для работы с ретвитами")
except ImportError as e:
    logger.error(f"Ошибка при импорте функций для работы с ретвитами: {e}")
    # Добавляем заглушки, если импорт не удался, чтобы основной скрипт не падал
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
logger.info("Модуль twitter_scraper_enhanced_utils инициализирован (без ссылок и статей)")
