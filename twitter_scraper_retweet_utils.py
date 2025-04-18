#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы с ретвитами и анализа информации об авторах.
Содержит функции для определения и классификации ретвитов и их авторов.
"""

import re
import logging
from selenium.webdriver.common.by import By

# Настройка логирования
logger = logging.getLogger('twitter_scraper.retweets')


def extract_retweet_info_enhanced(tweet_element):
    """
    Улучшенная функция для извлечения информации о ретвите с более надежным определением

    Args:
        tweet_element: Элемент твита Selenium WebDriver

    Returns:
        dict: Словарь с информацией о ретвите
    """
    result = {
        "is_retweet": False,
        "original_author": None
    }

    try:
        logger.info("Начало расширенной проверки на ретвит...")

        # МЕТОД 1: Проверка атрибутов интерфейса и классов
        try:
            # Ищем элементы с указанием ретвита/репоста через различные CSS селекторы
            retweet_indicators = [
                '[data-testid="socialContext"]',  # Стандартный элемент контекста
                '[data-testid="retweet"]'  # Элемент кнопки ретвита
            ]

            # Также проверяем по XPath для текстовых индикаторов
            xpath_indicators = [
                './/span[contains(text(), "Retweeted")]',
                './/span[contains(text(), "reposted")]',
                './/span[contains(text(), "ретвитнул")]',
                './/span[contains(text(), "повторно опубликовал")]'
            ]

            # Проверяем CSS селекторы
            for indicator in retweet_indicators:
                elements = tweet_element.find_elements(By.CSS_SELECTOR, indicator)
                if elements:
                    for element in elements:
                        try:
                            element_text = element.text.lower()
                            # Проверяем, содержит ли текст индикаторы ретвита
                            if any(ind in element_text for ind in [
                                "retweeted", "reposted", "ретвитнул", "ретвитнула",
                                "повторно опубликовал", "повторно опубликовала"
                            ]):
                                logger.info(f"Обнаружен ретвит через индикатор в тексте: '{element_text}'")
                                result["is_retweet"] = True
                                break
                        except Exception as e:
                            logger.error(f"Ошибка при проверке элемента с индикатором: {e}")

                    # Если определили, что это ретвит, выходим из цикла
                    if result["is_retweet"]:
                        break

            # Проверяем XPath выражения, если еще не нашли ретвит
            if not result["is_retweet"]:
                for xpath in xpath_indicators:
                    elements = tweet_element.find_elements(By.XPATH, xpath)
                    if elements:
                        logger.info(f"Обнаружен ретвит через XPath: {xpath}")
                        result["is_retweet"] = True
                        break

        except Exception as e:
            logger.error(f"Ошибка при проверке атрибутов интерфейса: {e}")

        # МЕТОД 2: Проверка HTML атрибутов
        if not result["is_retweet"]:
            try:
                # Получаем HTML твита
                html = tweet_element.get_attribute('outerHTML')

                # Ищем индикаторы ретвита в HTML
                if any(indicator in html.lower() for indicator in
                       ["retweeted", "reposted", "ретвитнул", "socialcontext"]):
                    logger.info(f"Обнаружен ретвит через анализ HTML")
                    result["is_retweet"] = True

            except Exception as e:
                logger.error(f"Ошибка при анализе HTML: {e}")

        # МЕТОД 3: Проверка на наличие двух разных имен пользователей
        if not result["is_retweet"]:
            try:
                # Ищем все имена пользователей в твите
                usernames = set()

                # Ищем все ссылки на профили
                user_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[role="link"][href*="/"]')

                for link in user_links:
                    href = link.get_attribute('href')
                    if href and '/status/' not in href and ('twitter.com/' in href or 'x.com/' in href):
                        if 'twitter.com/' in href:
                            username = href.split('twitter.com/')[-1].split('?')[0].strip('/')
                        else:
                            username = href.split('x.com/')[-1].split('?')[0].strip('/')

                        if username and len(username) > 1:
                            usernames.add(username)

                logger.info(f"Найдено уникальных имен пользователей: {len(usernames)}")
                if len(usernames) >= 2:
                    logger.info(f"Обнаружен ретвит по наличию нескольких имен пользователей: {usernames}")
                    result["is_retweet"] = True

            except Exception as e:
                logger.error(f"Ошибка при проверке имен пользователей: {e}")

        # Если определили, что это ретвит, ищем оригинального автора
        if result["is_retweet"]:
            try:
                # МЕТОД 1: Поиск по socialContext
                try:
                    social_context = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"]')
                    if social_context:
                        # Ищем ссылки внутри socialContext
                        links = social_context[0].find_elements(By.TAG_NAME, 'a')
                        for link in links:
                            href = link.get_attribute('href')
                            if href and ('twitter.com/' in href or 'x.com/' in href) and '/status/' not in href:
                                if 'twitter.com/' in href:
                                    original_author = href.split('twitter.com/')[-1].split('?')[0].strip('/')
                                else:
                                    original_author = href.split('x.com/')[-1].split('?')[0].strip('/')
                                logger.info(f"Найден оригинальный автор через socialContext: @{original_author}")
                                result["original_author"] = original_author
                                break
                except Exception as e:
                    logger.error(f"Ошибка при поиске автора через socialContext: {e}")

                # МЕТОД 2: Поиск в тексте socialContext
                if not result["original_author"]:
                    try:
                        social_context = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"]')
                        if social_context:
                            context_text = social_context[0].text
                            # Ищем упоминания пользователей в тексте (формат @username)
                            mentions = re.findall(r'@(\w+)', context_text)
                            if mentions:
                                result["original_author"] = mentions[0]
                                logger.info(
                                    f"Найден оригинальный автор через текст socialContext: @{result['original_author']}")
                    except Exception as e:
                        logger.error(f"Ошибка при поиске автора в тексте socialContext: {e}")

                # МЕТОД 3: Анализ структуры твита
                if not result["original_author"]:
                    try:
                        # Ищем все ссылки на профили
                        user_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[role="link"][href*="/"]')
                        usernames = []

                        for link in user_links:
                            href = link.get_attribute('href')
                            if href and '/status/' not in href and ('twitter.com/' in href or 'x.com/' in href):
                                if 'twitter.com/' in href:
                                    username = href.split('twitter.com/')[-1].split('?')[0].strip('/')
                                else:
                                    username = href.split('x.com/')[-1].split('?')[0].strip('/')

                                if username and len(username) > 1 and username not in usernames:
                                    usernames.append(username)

                        # В большинстве случаев второе имя в списке - это оригинальный автор
                        if len(usernames) >= 2:
                            result["original_author"] = usernames[1]
                            logger.info(f"Найден вероятный оригинальный автор: @{result['original_author']}")
                    except Exception as e:
                        logger.error(f"Ошибка при анализе структуры твита: {e}")

            except Exception as e:
                logger.error(f"Общая ошибка при поиске оригинального автора: {e}")

        logger.info(f"Результат определения ретвита: {result}")
        return result

    except Exception as e:
        logger.error(f"Общая ошибка при определении ретвита: {e}")
        return result


def extract_retweet_info_basic(tweet_element):
    """
    Базовая функция для извлечения информации о ретвите.
    Используется как резервный вариант, если расширенная функция не работает.

    Args:
        tweet_element: Элемент твита Selenium WebDriver

    Returns:
        dict: Словарь с информацией о ретвите
    """
    result = {
        "is_retweet": False,
        "original_author": None
    }

    try:
        # Быстрая проверка через data-testid="socialContext"
        social_context = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"]')
        if social_context:
            context_text = social_context[0].text.lower()
            if any(term in context_text for term in ["retweeted", "reposted", "ретвитнул"]):
                result["is_retweet"] = True

                # Пытаемся извлечь имя оригинального автора
                mentions = re.findall(r'@(\w+)', social_context[0].text)
                if mentions:
                    result["original_author"] = mentions[0]

        # Проверка на наличие иконки ретвита
        if not result["is_retweet"]:
            retweet_icons = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="retweet"]')
            if retweet_icons and len(retweet_icons) > 0:
                result["is_retweet"] = True

    except Exception as e:
        logger.error(f"Ошибка при базовой проверке ретвита: {e}")

    return result


def get_author_info(tweet_element):
    """
    Извлекает информацию об авторе твита

    Args:
        tweet_element: Элемент твита Selenium WebDriver

    Returns:
        dict: Словарь с информацией об авторе
    """
    author_info = {
        "username": None,
        "display_name": None,
        "verified": False
    }

    try:
        # Ищем элементы с информацией об авторе
        author_elements = tweet_element.find_elements(
            By.CSS_SELECTOR,
            '[data-testid="User-Name"]'
        )

        if author_elements:
            # Имя автора обычно в первом элементе
            author_element = author_elements[0]

            # Ищем отображаемое имя
            name_elements = author_element.find_elements(By.CSS_SELECTOR, 'span')
            if name_elements:
                for elem in name_elements:
                    if elem.text and len(elem.text) > 0 and elem.text[0] != '@':
                        author_info["display_name"] = elem.text
                        break

            # Ищем имя пользователя (@username)
            username_elements = author_element.find_elements(By.CSS_SELECTOR, 'span:contains("@")')
            if username_elements:
                for elem in username_elements:
                    username_match = re.search(r'@(\w+)', elem.text)
                    if username_match:
                        author_info["username"] = username_match.group(1)
                        break

            # Если не удалось найти через span, ищем через ссылку
            if not author_info["username"]:
                links = author_element.find_elements(By.TAG_NAME, 'a')
                for link in links:
                    href = link.get_attribute('href')
                    if href and '/status/' not in href and ('twitter.com/' in href or 'x.com/' in href):
                        if 'twitter.com/' in href:
                            username = href.split('twitter.com/')[-1].split('?')[0].strip('/')
                        else:
                            username = href.split('x.com/')[-1].split('?')[0].strip('/')

                        if username and len(username) > 1:
                            author_info["username"] = username
                            break

            # Проверяем, верифицирован ли аккаунт (наличие синей галочки)
            verified_elements = author_element.find_elements(By.CSS_SELECTOR, 'svg[aria-label="Verified account"]')
            if verified_elements:
                author_info["verified"] = True

    except Exception as e:
        logger.error(f"Ошибка при извлечении информации об авторе: {e}")

    return author_info