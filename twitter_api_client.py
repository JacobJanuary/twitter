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
        # Используем альтернативный эндпоинт, который может быть стабильнее
        api_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en"
        # Или можно попробовать этот:
        # api_url = f"https://api.twitter.com/2/tweets/{tweet_id}?tweet.fields=created_at,public_metrics,entities&expansions=author_id"
        # (Но для последнего нужна авторизация)

        logger.debug(f"Запрос к API: {api_url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5' # Предпочитаем английский язык
        }

        response = requests.get(api_url, headers=headers, timeout=15) # Увеличен таймаут
        response.raise_for_status() # Проверяем на HTTP ошибки

        tweet_data = response.json()
        logger.info(f"Успешно получены данные твита {tweet_id} через API")
        return tweet_data

    except requests.exceptions.RequestException as e:
        logger.warning(f"Ошибка сети при запросе твита {tweet_id} через API: {e}")
        return None
    except json.JSONDecodeError as e:
         logger.warning(f"Ошибка декодирования JSON от API для твита {tweet_id}: {e}")
         return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при запросе твита {tweet_id} через API: {e}")
        return None


def process_api_tweet_data(api_data, tweet_url):
    """
    Преобразует данные API в формат, используемый в скрипте (без изображений)

    Args:
        api_data: Данные твита из API
        tweet_url: Исходный URL твита

    Returns:
        dict: Данные твита в формате скрипта
    """
    if not api_data:
        return None

    try:
        # Базовая структура твита
        tweet_data = {
            "text": api_data.get("text", ""),
            "created_at": api_data.get("created_at", ""),
            "url": tweet_url,
            "stats": {
                "likes": api_data.get("favorite_count", 0),
                "retweets": api_data.get("retweet_count", 0),
                "replies": api_data.get("reply_count", 0) # reply_count может отсутствовать
            },
            # "images": [], # Удалено
            "is_retweet": False,
            "original_author": None,
            "is_truncated": False # API обычно возвращает полный текст
        }

        # Обработка полного текста (удаляем HTML теги, если есть)
        if "text" in api_data:
            text = api_data["text"]
            text = re.sub(r'<[^>]+>', '', text).strip()
            # Иногда API возвращает HTML сущности, пробуем их декодировать
            try:
                import html
                text = html.unescape(text)
            except ImportError:
                pass # Модуль html может отсутствовать
            tweet_data["text"] = text

        # Проверка на ретвит (в данных этого API ретвиты могут быть вложенными)
        if "retweeted_status" in api_data:
            tweet_data["is_retweet"] = True
            original_tweet = api_data["retweeted_status"]
            if "user" in original_tweet:
                tweet_data["original_author"] = original_tweet["user"].get("screen_name")
            # Заменяем текст и дату на данные оригинального твита
            tweet_data["text"] = original_tweet.get("text", tweet_data["text"])
            tweet_data["created_at"] = original_tweet.get("created_at", tweet_data["created_at"])
            # Статистика в этом случае относится к ретвиту, а не оригиналу
            # Можно попробовать извлечь статистику оригинала, если она есть
            tweet_data["stats"]["likes"] = original_tweet.get("favorite_count", tweet_data["stats"]["likes"])
            tweet_data["stats"]["retweets"] = original_tweet.get("retweet_count", tweet_data["stats"]["retweets"])

        # Проверка на цитирование (Quote Tweet)
        elif "quoted_status" in api_data:
             # Можно добавить обработку цитируемого твита, если нужно
             pass

        # --- Удалена обработка изображений ---
        # # Добавление медиа (фото)
        # if "photos" in api_data:
        #     for photo in api_data["photos"]:
        #         if "url" in photo:
        #             tweet_data["images"].append(photo["url"])
        #
        # # Добавление видео превью
        # if "video" in api_data and api_data["video"].get("poster"):
        #     tweet_data["images"].append(api_data["video"]["poster"])

        # Если нет счетчика ответов, ставим 0
        if "reply_count" not in api_data:
             tweet_data["stats"]["replies"] = 0

        return tweet_data
    except Exception as e:
        logger.error(f"Ошибка при обработке данных API для твита {tweet_url}: {e}")
        return None
