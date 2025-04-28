#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для доступа к твитам через неофициальный API Twitter
"""

import json
import time
import logging
import requests
import re

logger = logging.getLogger('twitter_scraper.api')

def get_tweet_by_id(tweet_id):
    """
    Получает полные данные твита по его ID через API

    Args:
        tweet_id: ID твита

    Returns:
        dict: Полные данные твита или None в случае ошибки
    """
    try:
        # Формируем URL для API запроса
        api_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}"

        # Делаем запрос с заголовками для имитации браузера
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json'
        }

        response = requests.get(api_url, headers=headers, timeout=10)

        # Проверяем успешность запроса
        if response.status_code == 200:
            tweet_data = response.json()
            logger.info(f"Успешно получены данные твита {tweet_id} через API")
            return tweet_data
        else:
            logger.warning(f"Ошибка API: {response.status_code} при запросе твита {tweet_id}")
            return None

    except Exception as e:
        logger.error(f"Ошибка при запросе твита {tweet_id} через API: {e}")
        return None


def process_api_tweet_data(api_data, tweet_url):
    """
    Преобразует данные API в формат, используемый в скрипте

    Args:
        api_data: Данные твита из API
        tweet_url: Исходный URL твита

    Returns:
        dict: Данные твита в формате скрипта
    """
    if not api_data:
        return None

    try:
        tweet_data = {
            "text": api_data.get("text", ""),
            "created_at": api_data.get("created_at", ""),
            "url": tweet_url,
            "stats": {
                "likes": api_data.get("favorite_count", 0),
                "retweets": api_data.get("retweet_count", 0),
                "replies": api_data.get("reply_count", 0)
            },
            # "images": [], # Удалено
            "is_retweet": False,
            "original_author": None,
            "is_truncated": False
        }

        # Обработка полного текста
        if "text" in api_data:
            # Получаем текст без HTML тегов
            text = api_data["text"]
            # Удаляем HTML теги если они есть
            text = re.sub(r'<[^>]+>', '', text)
            tweet_data["text"] = text

        # Проверка на ретвит
        if "retweeted_status" in api_data:
            tweet_data["is_retweet"] = True
            if "user" in api_data.get("retweeted_status", {}):
                tweet_data["original_author"] = api_data["retweeted_status"]["user"].get("screen_name")

        # Добавление медиа - Удалено
        # if "photos" in api_data:
        #     for photo in api_data["photos"]:
        #         if "url" in photo:
        #             tweet_data["images"].append(photo["url"])

        # Добавление видео превью - Удалено
        # if "video" in api_data and api_data["video"].get("poster"):
        #     tweet_data["images"].append(api_data["video"]["poster"])

        return tweet_data
    except Exception as e:
        logger.error(f"Ошибка при обработке данных API: {e}")
        return None

