#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для извлечения твитов из Twitter
Содержит функции для получения твитов, их обработки и сохранения
"""

import os
import json
import time
import logging
import re
import requests
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
# Импорты для резервного метода
from twitter_scraper_utils import extract_tweet_stats, extract_images_from_tweet
from twitter_scraper_retweet_utils import extract_retweet_info_enhanced
from twitter_scraper_links_utils import (
    extract_all_links_from_tweet,
    is_tweet_truncated,
    get_full_tweet_text,
    extract_full_tweet_text_from_html  # Добавляем новую функцию
)
# Настройка логирования
logger = logging.getLogger('twitter_scraper.tweets')

# Директории для кэширования
CACHE_DIR = "twitter_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

HTML_CACHE_DIR = "twitter_html_cache"
os.makedirs(HTML_CACHE_DIR, exist_ok=True)

def expand_tweet_content(driver, tweet_element):
    """
    Расширяет содержимое твита, нажимая на кнопку "Показать ещё" или "Show more"

    Args:
        driver: Экземпляр Selenium WebDriver
        tweet_element: Элемент твита Selenium WebDriver

    Returns:
        bool: True, если твит был успешно расширен, False в противном случае
    """
    expanded = False
    try:
        # Проверяем наличие кнопок раскрытия различных типов
        show_more_selectors = [
            # XPath селекторы для кнопок раскрытия
            ".//div[@role='button' and contains(., 'Show more')]",
            ".//div[@role='button' and contains(., 'Показать ещё')]",
            ".//div[@role='button' and contains(., 'show more')]",
            ".//span[contains(., 'Show more')]",
            ".//span[contains(., 'Показать ещё')]",
            ".//div[contains(., 'Show more') and @data-testid='tweetEngagement']",
            # CSS селекторы для кнопок раскрытия
            "div[role='button']:has-text('Show more')",
            "div[role='button']:has-text('Показать ещё')"
        ]

        # Пробуем каждый селектор
        for selector in show_more_selectors:
            try:
                show_more_buttons = tweet_element.find_elements(By.XPATH, selector)
                if show_more_buttons:
                    logger.info(f"Найдены кнопки раскрытия через селектор: {selector}")
                    break
            except:
                continue
        else:
            # Если не нашли через XPath, пробуем через CSS селекторы
            try:
                show_more_buttons = tweet_element.find_elements(By.CSS_SELECTOR, "div[role='button']")
                # Фильтруем по тексту
                show_more_buttons = [b for b in show_more_buttons if 'Show more' in b.text or 'Показать' in b.text]
            except:
                show_more_buttons = []

        # Если нашли кнопки раскрытия, нажимаем на них
        if show_more_buttons:
            logger.info(f"Найдено {len(show_more_buttons)} кнопок раскрытия")
            for button in show_more_buttons:
                try:
                    # Пробуем несколько методов клика
                    methods = [
                        # Стандартный клик
                        lambda: button.click(),
                        # Клик через JavaScript
                        lambda: driver.execute_script("arguments[0].click();", button),
                        # Клик через ActionChains
                        lambda: ActionChains(driver).move_to_element(button).click().perform()
                    ]

                    for method in methods:
                        try:
                            method()
                            # Ждем немного для применения клика и раскрытия контента
                            time.sleep(2)
                            logger.info("Контент успешно раскрыт")
                            expanded = True
                            break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Ошибка при попытке раскрытия: {e}")

        # Если не удалось найти и нажать кнопки "Show more",
        # попробуем проверить наличие многоточия в конце текста
        if not expanded:
            try:
                tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                tweet_text = tweet_text_element.text.strip()
                if tweet_text.endswith('…') or tweet_text.endswith('...'):
                    logger.info("Найдено многоточие в конце текста, твит может быть обрезан")
                    # В этом случае возвращаем False, чтобы позже попытаться открыть твит отдельно
                    return False
            except:
                pass

        return expanded

    except Exception as e:
        logger.error(f"Ошибка при раскрытии твита: {e}")
        return False


def find_all_tweets(driver):
    """
    Расширенный поиск твитов с несколькими стратегиями
    """
    tweets = []

    # Стратегия 1: Стандартный селектор
    standard_tweets = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
    if standard_tweets:
        tweets.extend(standard_tweets)
        logger.info(f"Найдено {len(standard_tweets)} твитов по стандартному селектору")

    # Стратегия 2: Расширенный селектор
    if len(tweets) < 5:  # Если нашли мало твитов
        timeline_items = driver.find_elements(By.CSS_SELECTOR, '[data-testid="cellInnerDiv"]')
        new_tweets = []
        for item in timeline_items:
            # Проверяем, содержит ли элемент время (признак твита)
            if item.find_elements(By.TAG_NAME, 'time'):
                if item not in tweets:
                    new_tweets.append(item)
        if new_tweets:
            tweets.extend(new_tweets)
            logger.info(f"Найдено дополнительно {len(new_tweets)} твитов по расширенному селектору")

    logger.info(f"Всего найдено твитов: {len(tweets)}")
    return tweets


def expand_tweet_content_improved(driver, tweet_element):
    """
    Улучшенная функция раскрытия твита
    """
    expanded = False

    try:
        # Прокручиваем к элементу
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet_element)
        time.sleep(1)

        # Проверяем разные селекторы для кнопок раскрытия
        selectors = [
            './/div[@role="button" and contains(text(), "Show more")]',
            './/span[contains(text(), "Show more")]',
            './/div[contains(@class, "r-1sg46qm")]'
        ]

        for selector in selectors:
            buttons = tweet_element.find_elements(By.XPATH, selector)
            if buttons:
                for button in buttons:
                    try:
                        # Клик через JavaScript
                        driver.execute_script("arguments[0].click();", button)
                        time.sleep(2)  # Увеличенное время ожидания
                        expanded = True
                        logger.info("Твит раскрыт успешно")
                        break
                    except Exception as e:
                        logger.warning(f"Ошибка при клике на кнопку раскрытия: {e}")

                if expanded:
                    break

        return expanded
    except Exception as e:
        logger.error(f"Ошибка при раскрытии твита: {e}")
        return False


def process_tweet_fallback(driver, tweet_url, username):
    """
    Резервный метод обработки твита, если стандартный метод не сработал
    Автоматически запускается при обнаружении проблемного твита
    """
    tweet_data = None
    current_window = driver.current_window_handle

    try:
        # Открываем новую вкладку
        driver.execute_script("window.open('');")
        time.sleep(1)
        driver.switch_to.window(driver.window_handles[-1])

        # Загружаем твит напрямую
        logger.info(f"Применяем резервный метод обработки для твита: {tweet_url}")
        driver.get(tweet_url)

        # Ждем загрузки твита
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'article[data-testid="tweet"], div[data-testid="tweetText"]'))
        )

        # Извлекаем данные твита
        tweet_data = {
            "text": "",
            "created_at": "",
            "url": tweet_url,
            "stats": {"likes": 0, "retweets": 0, "replies": 0},
            "images": [],
            "is_retweet": False,
            "original_author": None,
            "is_truncated": False
        }

        # Извлекаем текст твита (используем несколько селекторов)
        for selector in ['div[data-testid="tweetText"]', 'article[data-testid="tweet"] div[lang]']:
            try:
                text_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if text_elements:
                    tweet_data["text"] = text_elements[0].text
                    break
            except:
                continue

        # Извлекаем время публикации
        time_elements = driver.find_elements(By.TAG_NAME, 'time')
        if time_elements:
            tweet_data["created_at"] = time_elements[0].get_attribute('datetime')

        # Извлекаем статистику
        tweet_element = driver.find_element(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        tweet_data["stats"] = extract_tweet_stats(tweet_element)

        # Извлекаем изображения
        tweet_data["images"] = extract_images_from_tweet(tweet_element, username)

        # Определяем, является ли твит ретвитом
        retweet_info = extract_retweet_info_enhanced(tweet_element)
        tweet_data["is_retweet"] = retweet_info["is_retweet"]
        tweet_data["original_author"] = retweet_info["original_author"]

        logger.info(f"Успешно применен резервный метод для твита")

    except Exception as e:
        logger.error(f"Ошибка при резервной обработке твита: {e}")
    finally:
        # Закрываем вкладку и возвращаемся
        try:
            driver.close()
            driver.switch_to.window(current_window)
        except:
            pass

    return tweet_data


def get_tweet_from_api(tweet_url):
    """
    Получает твит через API
    """
    try:
        # Импортируем функции API
        from twitter_api_client import get_tweet_by_id, process_api_tweet_data

        # Извлекаем ID твита из URL
        if "/status/" in tweet_url:
            tweet_id = tweet_url.split("/status/")[1].split("?")[0]
        else:
            return None

        # Получаем данные через API
        api_data = get_tweet_by_id(tweet_id)

        # Преобразуем в нужный формат
        tweet_data = process_api_tweet_data(api_data, tweet_url)

        return tweet_data
    except Exception as e:
        logger.error(f"Ошибка при запросе твита через API: {e}")
        return None

def get_tweets_with_selenium(username, driver, db_connection=None, max_tweets=10, use_cache=True,
                             cache_duration_hours=1, time_filter_hours=24, force_refresh=False,
                             extract_articles=True, extract_full_tweets=True, extract_links=True,
                             dependencies=None, html_cache_dir="twitter_html_cache"):
    """
    Получает твиты пользователя с помощью Selenium, включая:
    - изображения
    - ретвиты
    - полные тексты длинных твитов
    - связанные статьи
    - все ссылки внутри твитов

    Args:
        username: Имя пользователя Twitter
        driver: Экземпляр Selenium WebDriver
        db_connection: Соединение с базой данных MySQL
        max_tweets: Максимальное количество твитов для извлечения
        use_cache: Использовать ли кэш
        cache_duration_hours: Срок действия кэша в часах
        time_filter_hours: Фильтр по времени публикации твитов в часах
        force_refresh: Принудительное обновление данных
        extract_articles: Извлекать ли статьи из твитов
        extract_full_tweets: Извлекать ли полные версии длинных твитов
        extract_links: Извлекать ли все ссылки из твитов
        dependencies: Словарь с необходимыми функциями

    Returns:
        dict: Словарь с результатами
    """
    # Проверяем, что все зависимости переданы
    if dependencies is None:
        dependencies = {}

    # Получаем необходимые функции
    debug_print = dependencies.get('debug_print', lambda *args, **kwargs: None)
    save_user_to_db = dependencies.get('save_user_to_db', lambda *args, **kwargs: None)
    save_tweet_to_db = dependencies.get('save_tweet_to_db', lambda *args, **kwargs: None)
    filter_recent_tweets = dependencies.get('filter_recent_tweets', lambda *args, **kwargs: [])
    extract_tweet_stats = dependencies.get('extract_tweet_stats', lambda *args, **kwargs: {})
    extract_images_from_tweet = dependencies.get('extract_images_from_tweet', lambda *args, **kwargs: [])
    extract_retweet_info_enhanced = dependencies.get('extract_retweet_info_enhanced',
                                                     dependencies.get('extract_retweet_info',
                                                                      lambda *args, **kwargs: {}))
    is_tweet_truncated = dependencies.get('is_tweet_truncated', lambda *args, **kwargs: False)
    get_full_tweet_text = dependencies.get('get_full_tweet_text', lambda *args, **kwargs: "")
    process_article_from_tweet = dependencies.get('process_article_from_tweet', lambda *args, **kwargs: None)
    save_links_to_db = dependencies.get('save_links_to_db', lambda *args, **kwargs: None)
    extract_all_links_from_tweet = dependencies.get('extract_all_links_from_tweet', lambda *args, **kwargs: {})

    print(f"Начинаем получение твитов для @{username}...")
    logger.info(f"Начинаем получение твитов для @{username}...")
    cache_file = os.path.join(CACHE_DIR, f"{username}_tweets_selenium.json")

    # Создаем результат по умолчанию
    result = {"username": username, "name": username, "tweets": []}

    # Проверяем кэш, если разрешено и не требуется обновление
    if use_cache and os.path.exists(cache_file) and not force_refresh:
        try:
            print(f"Проверка кэша для @{username}...")
            logger.info(f"Проверка кэша для @{username}...")
            file_modified_time = os.path.getmtime(cache_file)
            current_time = time.time()
            # Если кэш не устарел
            if current_time - file_modified_time < cache_duration_hours * 3600:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    print(f"Используем кэшированные данные для @{username}")
                    logger.info(f"Используем кэшированные данные для @{username}")

                    # Фильтруем по времени
                    result["name"] = cached_data.get("name", username)

                    # Применяем фильтр по времени
                    recent_tweets = filter_recent_tweets(cached_data.get('tweets', []), time_filter_hours)
                    result["tweets"] = recent_tweets[:max_tweets]

                    if recent_tweets:
                        return result
                    else:
                        print(f"В кэше нет твитов за последние {time_filter_hours} часов, запрашиваем свежие данные")
                        logger.info(
                            f"В кэше нет твитов за последние {time_filter_hours} часов, запрашиваем свежие данные")
        except Exception as e:
            print(f"Ошибка при чтении кэша: {e}")
            logger.error(f"Ошибка при чтении кэша: {e}")
    elif force_refresh:
        print(f"Принудительное обновление данных для @{username}")
        logger.info(f"Принудительное обновление данных для @{username}")

    try:
        print(f"Загружаем страницу профиля @{username}...")
        logger.info(f"Загружаем страницу профиля @{username}...")

        # Открываем страницу профиля
        profile_url = f"https://twitter.com/{username}"
        print(f"Переходим по URL: {profile_url}")
        driver.get(profile_url)

        # Ждем загрузки страницы
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]'))
            )
            print("Страница загружена, твиты найдены")
            logger.info("Страница загружена, твиты найдены")
        except TimeoutException:
            print("Таймаут при ожидании загрузки твитов, продолжаем выполнение")
            logger.warning("Таймаут при ожидании загрузки твитов, продолжаем выполнение")
            # Дополнительная задержка на случай медленной загрузки
            time.sleep(10)

        # Проверяем, авторизованы ли мы
        page_source = driver.page_source
        print(f"Длина исходного кода страницы: {len(page_source)} символов")
        if "Log in" in page_source and "Sign up" in page_source and "The timeline is empty" not in page_source:
            print("ВНИМАНИЕ: Признаки авторизации не обнаружены. Возможно, сессия истекла.")
            logger.warning("Признаки авторизации не обнаружены. Возможно, сессия истекла.")
            return result

        # Проверяем, найден ли аккаунт
        if "This account doesn't exist" in page_source or "Hmm...this page doesn't exist" in page_source:
            print(f"Ошибка: Аккаунт @{username} не существует или недоступен")
            logger.error(f"Аккаунт @{username} не существует или недоступен")
            return result

        # Сохраняем HTML для анализа
        html_file = os.path.join(html_cache_dir, f"{username}_selenium.html")
        print(f"Сохраняем HTML страницы в файл: {html_file}")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.info(f"HTML-страница сохранена в файл {html_file}")

        # Извлекаем имя пользователя из заголовка
        try:
            title = driver.title
            print(f"Заголовок страницы: {title}")
            if "(" in title:
                name = title.split("(")[0].strip()
                result["name"] = name
                print(f"Извлечено имя пользователя: {name}")
                logger.info(f"Извлечено имя пользователя: {name}")
        except Exception as e:
            print(f"Ошибка при извлечении имени: {e}")
            logger.error(f"Ошибка при извлечении имени: {e}")

        # Сохраняем пользователя в базу данных
        user_id = None
        if db_connection and save_user_to_db:
            print(f"Сохранение информации о пользователе @{username} в базу данных...")
            user_id = save_user_to_db(db_connection, username, result["name"])
            if not user_id:
                print(f"Ошибка при сохранении пользователя {username} в базу данных")
                logger.error(f"Ошибка при сохранении пользователя {username} в базу данных")
            else:
                print(f"Пользователь сохранен в БД с ID: {user_id}")
                logger.info(f"Пользователь сохранен в БД с ID: {user_id}")

        # Множество для хранения идентификаторов обработанных твитов
        processed_tweet_ids = set()
        tweets_data = []

        # Параметры скроллинга
        scroll_attempts = 0
        max_scroll_attempts = 40  # Увеличенное количество попыток скроллинга
        no_new_tweets_count = 0
        max_no_new_tweets = 5  # Останавливаем скроллинг если 5 попыток не дали новых твитов

        # Высота каждого шага скроллинга (в пикселах)
        scroll_step = 1000

        # Счетчик текущей позиции скролла
        current_scroll_position = 0

        print("Начинаем пошаговый скроллинг для загрузки твитов...")
        logger.info("Начинаем пошаговый скроллинг для загрузки твитов...")

        while scroll_attempts < max_scroll_attempts and no_new_tweets_count < max_no_new_tweets and len(
                tweets_data) < max_tweets:
            scroll_attempts += 1

            print(f"Попытка скроллинга #{scroll_attempts}...")
            logger.info(f"Попытка скроллинга #{scroll_attempts}...")

            # Прокручиваем на один шаг вниз
            current_scroll_position += scroll_step
            driver.execute_script(f"window.scrollTo(0, {current_scroll_position});")

            # Ждем загрузки новых твитов
            time.sleep(3)

            # Находим все текущие твиты
            tweet_elements = find_all_tweets(driver)
            print(f"Найдено {len(tweet_elements)} твитов на странице")

            # Отслеживаем, сколько новых твитов добавлено в этой итерации
            new_tweets_this_iteration = 0

            # Обрабатываем найденные твиты
            for tweet_element in tweet_elements:
                try:
                    # Получаем URL твита для идентификации
                    tweet_url = ""
                    tweet_id = ""

                    for link in tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]'):
                        href = link.get_attribute('href')
                        if href and "/status/" in href:
                            tweet_url = href
                            tweet_id = href.split("/status/")[1].split("?")[0]
                            break

                    # Если твит без URL или уже обработан, пропускаем
                    if not tweet_id or tweet_id in processed_tweet_ids:
                        continue
                    # После извлечения URL и ID твита, перед обработкой

                    # Сначала пробуем получить данные через API
                    api_tweet_data = get_tweet_from_api(tweet_url)
                    if api_tweet_data and api_tweet_data.get("text"):
                        # Если получилось, используем данные из API
                        tweets_data.append(api_tweet_data)
                        new_tweets_this_iteration += 1
                        logger.info(f"Твит {tweet_id} успешно получен через API")

                        # Сохраняем в БД
                        if db_connection and user_id:
                            tweet_db_id = save_tweet_to_db(db_connection, user_id, api_tweet_data)
                            # ... остальной код сохранения в БД

                        # Пропускаем стандартную обработку
                        continue
                    # Добавляем ID в множество обработанных
                    processed_tweet_ids.add(tweet_id)

                    print(f"Обработка твита ID: {tweet_id}")
                    logger.info(f"Обработка твита ID: {tweet_id}")

                    # Скроллируем к элементу, чтобы убедиться что он полностью загружен
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet_element)
                        time.sleep(1)  # Ждем немного для полной загрузки

                        # ВАЖНО: Сначала раскрываем содержимое твита, если оно обрезано
                        was_expanded = expand_tweet_content_improved(driver, tweet_element)
                        if was_expanded:
                            print("Твит был успешно раскрыт на странице")
                            logger.info("Твит был успешно раскрыт на странице")
                            # Даем время для полного раскрытия
                            time.sleep(2)
                    except:
                        print("Не удалось прокрутить к элементу")
                        logger.warning("Не удалось прокрутить к элементу")

                    # Определяем, является ли твит ретвитом (используем улучшенную функцию)
                    retweet_info = extract_retweet_info_enhanced(tweet_element)

                    # Извлекаем текст твита ПОСЛЕ раскрытия содержимого
                    tweet_text = ""
                    try:
                        tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                        tweet_text = tweet_text_element.text
                    except NoSuchElementException:
                        # Если текста нет, возможно это только изображение
                        pass

                    # После извлечения текста твита в get_tweets_with_selenium
                    if tweet_text:
                        # Проверяем, длинный ли твит и нужно ли нам извлечь полный текст
                        if len(tweet_text) > 100 or is_tweet_truncated(tweet_element):
                            logger.info(f"Обнаружен потенциально обрезанный твит, пробуем извлечь полный текст")
                            full_text = extract_full_tweet_text_from_html(driver, tweet_url)
                            if full_text and len(full_text) > len(tweet_text):
                                logger.info(f"Успешно извлечен полный текст твита ({len(full_text)} символов)")
                                tweet_text = full_text
                    # Проверяем, нужно ли получить полный текст через отдельное открытие твита
                    is_truncated = False
                    need_full_text = False

                    # Проверяем признаки обрезанного текста даже после попытки раскрытия на странице
                    if tweet_text and (tweet_text.strip().endswith('…') or tweet_text.strip().endswith('...')):
                        need_full_text = True

                    # Если твит нужно открыть отдельно для получения полного текста
                    if extract_full_tweets and tweet_id and tweet_text and need_full_text and get_full_tweet_text:
                        print(f"Твит всё ещё обрезан, получаем полную версию через отдельное открытие...")
                        logger.info(f"Твит всё ещё обрезан, получаем полную версию через отдельное открытие...")

                        full_text = get_full_tweet_text(driver, tweet_url, max_attempts=3)

                        if full_text and len(full_text) > len(tweet_text):
                            print(f"Получен полный текст твита ({len(full_text)} символов)")
                            logger.info(f"Получен полный текст твита ({len(full_text)} символов)")
                            tweet_text = full_text
                            is_truncated = True

                    # Извлекаем время публикации
                    created_at = ""
                    try:
                        time_element = tweet_element.find_element(By.TAG_NAME, 'time')
                        created_at = time_element.get_attribute('datetime')
                    except NoSuchElementException:
                        # Если нет времени, это может быть специальный элемент
                        continue

                    # Извлекаем статистику и изображения
                    stats = extract_tweet_stats(tweet_element)
                    image_paths = extract_images_from_tweet(tweet_element, username)

                    print(f"Извлеченная статистика твита: {stats}")
                    if stats['likes'] == 0 and stats['retweets'] == 0:
                        print("ВНИМАНИЕ: Не удалось извлечь статистику лайков и ретвитов!")
                        logger.warning("Не удалось извлечь статистику лайков и ретвитов!")

                    # Создаем данные твита
                    # Проверка успешности стандартного метода
                    success = False
                    if tweet_text or len(image_paths) > 0:
                        success = True
                        tweet_data = {
                            "text": tweet_text,
                            "created_at": created_at,
                            "url": tweet_url,
                            "stats": stats,
                            "images": image_paths,
                            "is_retweet": retweet_info["is_retweet"],
                            "original_author": retweet_info["original_author"],
                            "is_truncated": False  # По умолчанию твит не обрезан
                        }
                    else:
                        logger.warning(f"Стандартный метод не смог извлечь данные твита {tweet_id}")

                    # Если стандартный метод не сработал, применяем резервный
                    if not success and tweet_url:
                        fallback_tweet_data = process_tweet_fallback(driver, tweet_url, username)
                        if fallback_tweet_data and (
                                fallback_tweet_data.get("text") or len(fallback_tweet_data.get("images", [])) > 0):
                            tweet_data = fallback_tweet_data
                            success = True
                            logger.info(f"Резервный метод успешно извлек данные твита {tweet_id}")
                        else:
                            logger.warning(f"Не удалось обработать твит {tweet_id} никаким методом")

                    # Если успех, добавляем твит в список
                    if success:
                        tweets_data.append(tweet_data)
                        new_tweets_this_iteration += 1

                    # Сохраняем твит в базу данных и обрабатываем статьи
                    tweet_db_id = None
                    if db_connection and user_id and save_tweet_to_db:
                        # Сохраняем твит в БД
                        tweet_db_id = save_tweet_to_db(db_connection, user_id, tweet_data)

                        # Сохраняем ссылки в БД, если включено извлечение ссылок
                        if extract_links and tweet_db_id and tweet_data.get("links") and save_links_to_db:
                            save_links_to_db(db_connection, tweet_db_id, tweet_data["links"])
                            logger.info(f"Ссылки из твита сохранены в БД")

                        # Проверяем наличие статей в твите
                        if extract_articles and tweet_db_id and process_article_from_tweet:
                            print(f"Проверка наличия статей в твите...")
                            logger.info(f"Проверка наличия статей в твите...")
                            article_data = process_article_from_tweet(
                                driver, tweet_element, tweet_db_id, username,
                                db_connection, use_cache=use_cache
                            )

                            if article_data:
                                tweet_data["article"] = article_data
                                print(f"К твиту привязана статья: {article_data.get('title', '')}")
                                logger.info(f"К твиту привязана статья: {article_data.get('title', '')}")

                    print(f"Добавлен твит: {created_at} | {tweet_text[:50]}..." if len(
                        tweet_text) > 50 else f"Добавлен твит: {created_at} | {tweet_text}")
                    logger.info(f"Добавлен твит ID: {tweet_id}")

                except Exception as e:
                    print(f"Ошибка при обработке твита: {e}")
                    logger.error(f"Ошибка при обработке твита: {e}")

            # Обновляем счетчик попыток без новых твитов
            if new_tweets_this_iteration == 0:
                no_new_tweets_count += 1
                print(f"Не найдено новых твитов. Счетчик: {no_new_tweets_count}/{max_no_new_tweets}")
                logger.info(f"Не найдено новых твитов. Счетчик: {no_new_tweets_count}/{max_no_new_tweets}")
            else:
                no_new_tweets_count = 0
                print(f"Добавлено {new_tweets_this_iteration} новых твитов в этой итерации")
                logger.info(f"Добавлено {new_tweets_this_iteration} новых твитов в этой итерации")

            # Проверяем, достигли ли мы конца страницы
            viewport_height = driver.execute_script("return window.innerHeight")
            document_height = driver.execute_script("return document.documentElement.scrollHeight")

            if current_scroll_position >= document_height - viewport_height:
                print("Достигнут конец страницы")
                logger.info("Достигнут конец страницы")
                # Ждем немного, чтобы подгрузились возможные дополнительные твиты
                time.sleep(5)

                # Проверяем, изменилась ли высота документа
                new_document_height = driver.execute_script("return document.documentElement.scrollHeight")
                if new_document_height <= document_height:
                    print("Больше твитов не загружается, завершаем скроллинг")
                    logger.info("Больше твитов не загружается, завершаем скроллинг")
                    break

        print(f"Завершен скроллинг после {scroll_attempts} попыток")
        logger.info(f"Завершен скроллинг после {scroll_attempts} попыток")
        print(f"Всего уникальных твитов обнаружено: {len(processed_tweet_ids)}")
        logger.info(f"Всего уникальных твитов обнаружено: {len(processed_tweet_ids)}")
        print(f"Всего твитов сохранено: {len(tweets_data)}")
        logger.info(f"Всего твитов сохранено: {len(tweets_data)}")

        # Дополнительная проверка - возможно некоторые твиты были пропущены при постепенном скроллинге
        print("Выполняем дополнительную проверку на пропущенные твиты...")
        logger.info("Выполняем дополнительную проверку на пропущенные твиты...")

        # Обновляем страницу полностью, чтобы получить весь DOM
        driver.get(profile_url)
        time.sleep(5)

        # Скроллим несколько раз до самого низа, чтобы загрузить все твиты
        last_height = 0
        for _ in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        # Анализируем HTML через BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        tweets_bs4 = soup.select('article[data-testid="tweet"]')
        print(f"BeautifulSoup: найдено {len(tweets_bs4)} твитов")
        logger.info(f"BeautifulSoup: найдено {len(tweets_bs4)} твитов")

        for tweet in tweets_bs4:
            try:
                # Извлекаем URL твита
                tweet_url = ""
                tweet_id = ""
                for link in tweet.select('a[href*="/status/"]'):
                    href = link.get('href')
                    if href and "/status/" in href:
                        tweet_url = f"https://twitter.com{href}"
                        tweet_id = href.split("/status/")[1].split("?")[0]
                        break

                # Если уже обработали этот твит, пропускаем
                if not tweet_id or tweet_id in processed_tweet_ids:
                    continue

                processed_tweet_ids.add(tweet_id)
                print(f"BS4: Найден новый пропущенный твит с ID {tweet_id}")
                logger.info(f"BS4: Найден новый пропущенный твит с ID {tweet_id}")

                # Обрабатываем твит через BS4
                # (упрощенная версия, без изображений и ссылок)
                tweet_text_elem = tweet.select_one('div[data-testid="tweetText"]')
                tweet_text = tweet_text_elem.text if tweet_text_elem else ""

                time_elem = tweet.find('time')
                created_at = time_elem.get('datetime') if time_elem else ""

                is_retweet = bool(tweet.select_one('span:-soup-contains("Retweeted")') or
                                  tweet.select_one('span:-soup-contains("reposted")'))

                tweet_data = {
                    "text": tweet_text,
                    "created_at": created_at,
                    "url": tweet_url,
                    "stats": {"likes": 0, "retweets": 0, "replies": 0},
                    "images": [],
                    "is_retweet": is_retweet,
                    "original_author": None,
                    "is_truncated": False
                }

                tweets_data.append(tweet_data)

                # Сохраняем в базу данных
                if db_connection and user_id and save_tweet_to_db:
                    tweet_db_id = save_tweet_to_db(db_connection, user_id, tweet_data)
                    logger.info(f"BS4: Твит сохранен в БД")

            except Exception as e:
                print(f"BS4: Ошибка при обработке пропущенного твита: {e}")
                logger.error(f"BS4: Ошибка при обработке пропущенного твита: {e}")

        # Фильтруем твиты за последние N часов
        print(f"Фильтрация твитов за последние {time_filter_hours} часов...")
        logger.info(f"Фильтрация твитов за последние {time_filter_hours} часов...")
        recent_tweets = filter_recent_tweets(tweets_data, time_filter_hours)
        print(f"Из них свежих твитов: {len(recent_tweets)}")
        logger.info(f"Из них свежих твитов: {len(recent_tweets)}")

        # Сохраняем все твиты в кэш
        cached_result = {
            "username": username,
            "name": result["name"],
            "tweets": tweets_data,
        }

        if use_cache:
            try:
                print(f"Сохранение {len(tweets_data)} твитов в кэш: {cache_file}")
                logger.info(f"Сохранение {len(tweets_data)} твитов в кэш: {cache_file}")
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cached_result, f, ensure_ascii=False, indent=2)
                print(f"Кэш успешно сохранен")
                logger.info(f"Кэш успешно сохранен")
            except Exception as e:
                print(f"Ошибка при сохранении кэша: {e}")
                logger.error(f"Ошибка при сохранении кэша: {e}")

        # Возвращаем только свежие твиты
        result["tweets"] = recent_tweets[:max_tweets]
        print(f"Возвращаем {len(result['tweets'])} свежих твитов для @{username}")
        logger.info(f"Возвращаем {len(result['tweets'])} свежих твитов для @{username}")

        return result

    except Exception as e:
        print(f"Ошибка при получении твитов для @{username} через Selenium: {e}")
        logger.error(f"Ошибка при получении твитов для @{username} через Selenium: {e}")
        import traceback
        traceback.print_exc()
        return result