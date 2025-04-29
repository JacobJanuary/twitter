#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для доступа к твитам через неофициальный API Twitter.
(Функционал отключен, так как API-эндпоинт не работает)
"""

import logging
# Остальные импорты (json, time, requests, re, html) больше не нужны

logger = logging.getLogger('twitter_scraper.api')
# Добавляем базовый обработчик, если он еще не настроен в core
if not logger.handlers:
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def get_tweet_by_id(tweet_id):
    """
    Заглушка для функции получения данных твита через API.
    (API отключен)

    Args:
        tweet_id: ID твита (не используется)

    Returns:
        None: Всегда возвращает None.
    """
    logger.debug(f"API вызов для tweet_id {tweet_id} отключен.")
    return None # Всегда возвращаем None


def process_api_tweet_data(api_data, tweet_url):
    """
    Заглушка для функции обработки данных API.
    (API отключен)

    Args:
        api_data: Данные API (не используется)
        tweet_url: URL твита (не используется)

    Returns:
        None: Всегда возвращает None.
    """
    logger.debug(f"Обработка данных API для {tweet_url} отключена.")
    return None # Всегда возвращаем None

logger.info("Модуль twitter_api_client загружен (функционал отключен).")
