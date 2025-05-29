#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для извлечения твитов из Twitter
Содержит функции для получения твитов, их обработки и сохранения
(Функционал извлечения изображений, ссылок и статей удален)
Заменены time.sleep() на WebDriverWait там, где это возможно.
"""

import os
import json
import time
import logging
import re
# requests больше не нужен напрямую здесь
# import requests
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains

# Импорты для резервного метода и утилит
# extract_images_from_tweet удален
from twitter_scraper_utils import extract_tweet_stats
# ИЗМЕНЕНО: Импортируем функцию из retweet_utils, которая больше не возвращает original_author
from twitter_scraper_retweet_utils import extract_retweet_info_enhanced
# extract_all_links_from_tweet удален
from twitter_scraper_links_utils import (
    is_tweet_truncated,
    get_full_tweet_text,
    extract_full_tweet_text_from_html
)
# Импорт API клиента
from twitter_api_client import get_tweet_by_id, process_api_tweet_data

# Настройка логирования
logger = logging.getLogger('twitter_scraper.tweets')

# Директории для кэширования
CACHE_DIR = "twitter_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

HTML_CACHE_DIR = "twitter_html_cache" # Оставляем для отладки HTML
os.makedirs(HTML_CACHE_DIR, exist_ok=True)


def expand_tweet_content(driver, tweet_element, timeout=5):
    """
    Расширяет содержимое твита, нажимая на кнопку "Показать ещё" или "Show more".
    Использует WebDriverWait для ожидания после клика.
    """
    expanded = False
    clicked_button = None # Сохраним кнопку, по которой кликнули
    try:
        show_more_selectors = [
            ".//div[@role='button' and (contains(., 'Show more') or contains(., 'Показать ещё'))]",
            ".//span[contains(., 'Show more') or contains(., 'Показать ещё')]",
            "div[role='button']:has-text('Show more')",
            "div[role='button']:has-text('Показать ещё')"
        ]

        show_more_buttons = []
        for selector in show_more_selectors:
            try:
                # Пробуем XPath
                if selector.startswith('.'):
                     buttons = tweet_element.find_elements(By.XPATH, selector)
                # Пробуем CSS
                else:
                     buttons = tweet_element.find_elements(By.CSS_SELECTOR, selector)

                if buttons:
                    show_more_buttons.extend(buttons)
                    logger.info(f"Найдены кнопки раскрытия через селектор: {selector}")
            except Exception as e:
                 if "stale element reference" not in str(e).lower():
                     logger.warning(f"Ошибка поиска кнопки раскрытия: {e}")
                 continue

        show_more_buttons = list(dict.fromkeys(show_more_buttons))

        if show_more_buttons:
            logger.info(f"Найдено {len(show_more_buttons)} кнопок раскрытия")
            for button in show_more_buttons:
                try:
                    # Прокручиваем к кнопке
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    # Убрали time.sleep(0.5)
                    # Пробуем кликнуть
                    try:
                        # Добавляем ожидание кликабельности
                        WebDriverWait(driver, 3).until(EC.element_to_be_clickable(button))
                        button.click()
                        clicked_button = button # Сохраняем кнопку
                    except Exception as click_err:
                        logger.warning(f"Стандартный клик не удался ({click_err}), пробуем JavaScript клик.")
                        driver.execute_script("arguments[0].click();", button)
                        clicked_button = button # Сохраняем кнопку

                    # ЗАМЕНА: Ждем, пока кнопка не исчезнет (станет устаревшей)
                    try:
                        WebDriverWait(driver, timeout).until(EC.staleness_of(clicked_button))
                        logger.info(f"Кнопка раскрытия стала устаревшей после клика (ожидание {timeout} сек).")
                    except TimeoutException:
                        logger.warning(f"Кнопка раскрытия НЕ стала устаревшей за {timeout} сек. Возможно, контент раскрылся иначе.")
                    # time.sleep(2) # Заменено на WebDriverWait

                    logger.info("Контент успешно раскрыт (или попытка раскрытия выполнена)")
                    expanded = True
                    break
                except StaleElementReferenceException:
                     logger.warning("Кнопка раскрытия устарела перед кликом.")
                     continue # Попробуем следующую кнопку, если есть
                except Exception as e:
                    logger.warning(f"Ошибка при попытке раскрытия: {e}")

        # Проверка на многоточие (если клик не удался или не было кнопки)
        if not expanded:
            try:
                tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                tweet_text = tweet_text_element.text.strip()
                if tweet_text.endswith('…') or tweet_text.endswith('...'):
                    logger.info("Найдено многоточие в конце текста, твит может быть обрезан")
                    return False
            except:
                pass

        return expanded # Возвращаем True, если была попытка клика

    except Exception as e:
        if "stale element reference" not in str(e).lower():
            logger.error(f"Ошибка при раскрытии твита: {e}")
        return False


def find_all_tweets(driver):
    """
    Расширенный поиск твитов с несколькими стратегиями.
    (Остается без изменений)
    """
    tweets = []
    processed_elements = set() # Чтобы избежать дубликатов

    # Стратегия 1: Стандартный селектор
    try:
        standard_tweets = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        if standard_tweets:
            for tweet in standard_tweets:
                # Добавим проверку видимости, чтобы не брать скрытые элементы
                try:
                    if tweet.is_displayed() and tweet.id not in processed_elements:
                        tweets.append(tweet)
                        processed_elements.add(tweet.id)
                except StaleElementReferenceException:
                    continue # Пропускаем устаревший элемент
            logger.info(f"Найдено {len(standard_tweets)} видимых твитов по стандартному селектору")
    except Exception as e:
         logger.warning(f"Ошибка поиска по стандартному селектору: {e}")


    # Стратегия 2: Расширенный селектор (если нашли мало)
    if len(tweets) < 5:
        try:
            timeline_items = driver.find_elements(By.CSS_SELECTOR, '[data-testid="cellInnerDiv"]')
            new_tweets_count = 0
            for item in timeline_items:
                 try:
                    # Проверяем, содержит ли элемент время (признак твита) и не обработан ли он уже
                    if item.is_displayed() and item.id not in processed_elements and item.find_elements(By.TAG_NAME, 'time'):
                        tweets.append(item)
                        processed_elements.add(item.id)
                        new_tweets_count += 1
                 except StaleElementReferenceException:
                     continue # Пропускаем устаревший элемент
            if new_tweets_count > 0:
                 logger.info(f"Найдено дополнительно {new_tweets_count} видимых твитов по расширенному селектору")
        except Exception as e:
             logger.warning(f"Ошибка поиска по расширенному селектору: {e}")


    logger.info(f"Всего найдено уникальных видимых твитов на странице: {len(tweets)}")
    return tweets


def expand_tweet_content_improved(driver, tweet_element, timeout=5):
    """
    Улучшенная функция раскрытия твита.
    Использует WebDriverWait.
    """
    expanded = False
    clicked_element = None
    try:
        # Прокручиваем к элементу и ждем его видимости
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet_element)
            WebDriverWait(driver, timeout).until(EC.visibility_of(tweet_element))
            # time.sleep(1) # Заменено на ожидание видимости
        except TimeoutException:
            logger.warning("Таймаут ожидания видимости элемента для раскрытия.")
            return False
        except Exception as scroll_err:
            logger.warning(f"Ошибка при прокрутке/ожидании видимости элемента для раскрытия: {scroll_err}")
            return False


        selectors = [
            './/div[@role="button" and (contains(text(), "Show more") or contains(text(), "Показать ещё"))]',
            './/span[contains(text(), "Show more") or contains(text(), "Показать ещё")]',
            './/div[contains(@class, "r-1sg46qm")]' # Класс для сокращенного текста
        ]

        for selector in selectors:
            try:
                buttons = tweet_element.find_elements(By.XPATH, selector)
                if buttons:
                    for button in buttons:
                        try:
                            # Ждем кликабельности перед кликом
                            WebDriverWait(driver, 3).until(EC.element_to_be_clickable(button))
                            driver.execute_script("arguments[0].click();", button)
                            clicked_element = button # Сохраняем элемент, по которому кликнули

                            # Ждем, пока элемент не станет устаревшим
                            try:
                                WebDriverWait(driver, timeout).until(EC.staleness_of(clicked_element))
                                logger.info(f"Элемент раскрытия ({selector}) стал устаревшим после клика.")
                            except TimeoutException:
                                logger.warning(f"Элемент раскрытия ({selector}) НЕ стал устаревшим за {timeout} сек.")
                            # time.sleep(2) # Заменено

                            expanded = True
                            logger.info("Твит раскрыт успешно (или попытка выполнена)")
                            break
                        except StaleElementReferenceException:
                            logger.warning("Кнопка/элемент раскрытия устарел(а) перед/во время клика.")
                            continue
                        except Exception as e:
                            logger.warning(f"Ошибка при клике на кнопку раскрытия ({selector}): {e}")
                    if expanded:
                        break
            except StaleElementReferenceException:
                 logger.warning(f"Элемент твита устарел при поиске кнопки раскрытия ({selector}).")
                 continue # Пробуем следующий селектор
            except Exception as e:
                 if "stale element reference" not in str(e).lower():
                     logger.warning(f"Ошибка поиска кнопки раскрытия (improved) ({selector}): {e}")

        return expanded
    except Exception as e:
        if "stale element reference" not in str(e).lower():
            logger.error(f"Ошибка при раскрытии твита (improved): {e}")
        return False

# --- Функция process_tweet_fallback удалена ---

# get_tweet_from_api остается в twitter_api_client.py

def get_tweets_with_selenium(username, driver, db_connection=None, max_tweets=10, use_cache=True,
                             cache_duration_hours=1, time_filter_hours=24, force_refresh=False,
                             extract_full_tweets=True,
                             dependencies=None, html_cache_dir="twitter_html_cache",
                             scroll_timeout=10, page_load_timeout=20):
    """
    Получает твиты пользователя с помощью Selenium, используя WebDriverWait.
    (Функционал изображений, ссылок и статей удален)

    Args:
        username: Имя пользователя Twitter
        driver: Экземпляр Selenium WebDriver
        db_connection: Соединение с базой данных MySQL
        max_tweets: Максимальное количество твитов для извлечения
        use_cache: Использовать ли кэш
        cache_duration_hours: Срок действия кэша в часах
        time_filter_hours: Фильтр по времени публикации твитов в часах
        force_refresh: Принудительное обновление данных
        extract_full_tweets: Извлекать ли полные версии длинных твитов
        dependencies: Словарь с необходимыми функциями
        html_cache_dir: Директория для сохранения HTML (для отладки)
        scroll_timeout: Макс. время ожидания новых твитов после скролла (сек)
        page_load_timeout: Макс. время ожидания загрузки страницы профиля (сек)

    Returns:
        dict: Словарь с результатами
    """
    if dependencies is None:
        dependencies = {}

    # Получаем необходимые функции из зависимостей
    debug_print = dependencies.get('debug_print', lambda *args, **kwargs: None)
    save_user_to_db = dependencies.get('save_user_to_db', lambda *args, **kwargs: None)
    save_tweet_to_db = dependencies.get('save_tweet_to_db', lambda *args, **kwargs: None)
    filter_recent_tweets = dependencies.get('filter_recent_tweets', lambda *args, **kwargs: [])
    extract_tweet_stats = dependencies.get('extract_tweet_stats', lambda *args, **kwargs: {})
    extract_retweet_info_enhanced = dependencies.get('extract_retweet_info_enhanced', lambda *args, **kwargs: {})
    is_tweet_truncated = dependencies.get('is_tweet_truncated', lambda *args, **kwargs: False)
    get_full_tweet_text = dependencies.get('get_full_tweet_text', lambda *args, **kwargs: "")

    print(f"Начинаем получение твитов для @{username}...")
    logger.info(f"Начинаем получение твитов для @{username}...")
    cache_file = os.path.join(CACHE_DIR, f"{username}_tweets_selenium.json")

    result = {"username": username, "name": username, "tweets": []}

    # Проверка кэша (без изменений)
    if use_cache and os.path.exists(cache_file) and not force_refresh:
        try:
            debug_print(f"Проверка кэша для @{username}...")
            file_modified_time = os.path.getmtime(cache_file)
            current_time = time.time()
            if current_time - file_modified_time < cache_duration_hours * 3600:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                debug_print(f"Используем кэшированные данные для @{username}")
                logger.info(f"Используем кэшированные данные для @{username}")

                result["name"] = cached_data.get("name", username)
                recent_tweets = filter_recent_tweets(cached_data.get('tweets', []), time_filter_hours)
                result["tweets"] = recent_tweets[:max_tweets]

                if result["tweets"]:
                    return result
                else:
                    debug_print(f"В кэше нет твитов за последние {time_filter_hours} часов, запрашиваем свежие данные")
                    logger.info(f"В кэше нет твитов за последние {time_filter_hours} часов, запрашиваем свежие данные")
        except Exception as e:
            print(f"Ошибка при чтении кэша: {e}")
            logger.error(f"Ошибка при чтении кэша: {e}")
    elif force_refresh:
        debug_print(f"Принудительное обновление данных для @{username}")
        logger.info(f"Принудительное обновление данных для @{username}")

    try:
        debug_print(f"Загружаем страницу профиля @{username}...")
        logger.info(f"Загружаем страницу профиля @{username}...")

        profile_url = f"https://twitter.com/{username}"
        debug_print(f"Переходим по URL: {profile_url}")
        driver.get(profile_url)

        # Ждем загрузки страницы и появления первого твита
        try:
            WebDriverWait(driver, page_load_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]'))
            )
            debug_print("Страница загружена, твиты найдены")
            logger.info("Страница загружена, твиты найдены")
        except TimeoutException:
            debug_print(f"Таймаут ({page_load_timeout} сек) при ожидании загрузки твитов, пробуем продолжить...")
            logger.warning(f"Таймаут ({page_load_timeout} сек) при ожидании загрузки твитов, пробуем продолжить...")
            # Убрали time.sleep(10), проверка ниже обработает отсутствие твитов

        # Проверка авторизации и существования аккаунта (без изменений)
        page_source = driver.page_source
        debug_print(f"Длина исходного кода страницы: {len(page_source)} символов")
        if "Log in" in page_source and "Sign up" in page_source and "The timeline is empty" not in page_source:
            print("ВНИМАНИЕ: Признаки авторизации не обнаружены. Возможно, сессия истекла.")
            logger.warning("Признаки авторизации не обнаружены. Возможно, сессия истекла.")
        if "This account doesn't exist" in page_source or "Hmm...this page doesn't exist" in page_source:
            print(f"Ошибка: Аккаунт @{username} не существует или недоступен")
            logger.error(f"Аккаунт @{username} не существует или недоступен")
            return result

        # Сохраняем HTML для анализа (без изменений)
        if html_cache_dir:
             html_file = os.path.join(html_cache_dir, f"{username}_selenium.html")
             debug_print(f"Сохраняем HTML страницы в файл: {html_file}")
             try:
                 with open(html_file, "w", encoding="utf-8") as f:
                     f.write(driver.page_source)
                 logger.info(f"HTML-страница сохранена в файл {html_file}")
             except Exception as e:
                 logger.error(f"Не удалось сохранить HTML: {e}")


        # Извлекаем имя пользователя (без изменений)
        try:
            name_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'h2[aria-level="2"][role="heading"] span span'))
            )
            result["name"] = name_element.text.strip()
            # Резервный метод через title, если первый не сработал
            if not result["name"]:
                 title = driver.title
                 if "(" in title:
                     result["name"] = title.split("(")[0].strip()
            debug_print(f"Извлечено имя пользователя: {result['name']}")
            logger.info(f"Извлечено имя пользователя: {result['name']}")
        except TimeoutException:
            logger.error("Не удалось найти элемент с именем пользователя.")
            # Попробуем извлечь из title как резерв
            title = driver.title
            if "(" in title:
                result["name"] = title.split("(")[0].strip()
                logger.info(f"Извлечено имя пользователя из title: {result['name']}")
            else:
                 logger.error("Не удалось извлечь имя пользователя и из title.")
        except Exception as e:
            debug_print(f"Ошибка при извлечении имени: {e}")
            logger.error(f"Ошибка при извлечении имени: {e}")

        # Сохраняем пользователя в базу данных (без изменений)
        user_id = None
        if db_connection and save_user_to_db:
            debug_print(f"Сохранение информации о пользователе @{username} в базу данных...")
            user_id = save_user_to_db(db_connection, username, result["name"])
            if not user_id:
                print(f"Ошибка при сохранении пользователя {username} в базу данных")
                logger.error(f"Ошибка при сохранении пользователя {username} в базу данных")
            else:
                debug_print(f"Пользователь сохранен в БД с ID: {user_id}")
                logger.info(f"Пользователь сохранен в БД с ID: {user_id}")

        processed_tweet_ids = set()
        tweets_data = []

        # Параметры скроллинга (без изменений)
        scroll_attempts = 0
        max_scroll_attempts = 40
        no_new_tweets_count = 0
        max_no_new_tweets = 5
        scroll_step = 1000 # Пиксели для прокрутки
        last_height = driver.execute_script("return document.body.scrollHeight")

        debug_print("Начинаем пошаговый скроллинг для загрузки твитов...")
        logger.info("Начинаем пошаговый скроллинг для загрузки твитов...")

        while scroll_attempts < max_scroll_attempts and no_new_tweets_count < max_no_new_tweets and len(tweets_data) < max_tweets:
            scroll_attempts += 1
            debug_print(f"Попытка скроллинга #{scroll_attempts}...")
            logger.info(f"Попытка скроллинга #{scroll_attempts}...")

            initial_tweet_elements = find_all_tweets(driver)
            initial_tweet_count = len(initial_tweet_elements)
            debug_print(f"Твитов на странице до скролла: {initial_tweet_count}")

            # Прокручиваем
            driver.execute_script(f"window.scrollBy(0, {scroll_step});")

            # ЗАМЕНА: Ждем появления новых твитов или изменения высоты страницы
            try:
                WebDriverWait(driver, scroll_timeout).until(
                    lambda d: len(find_all_tweets(d)) > initial_tweet_count or d.execute_script("return document.body.scrollHeight") > last_height + 100 # Ждем существенного увеличения высоты
                )
                new_height = driver.execute_script("return document.body.scrollHeight")
                debug_print(f"Скролл успешен. Новая высота: {new_height} (была {last_height}). Твитов стало: {len(find_all_tweets(driver))}")
                last_height = new_height
            except TimeoutException:
                debug_print(f"Таймаут ({scroll_timeout} сек) ожидания новых твитов или изменения высоты после скролла.")
                logger.warning(f"Таймаут ({scroll_timeout} сек) ожидания новых твитов/изменения высоты после скролла.")
                # Проверяем, достигли ли мы конца страницы
                if driver.execute_script("return window.innerHeight + window.scrollY") >= driver.execute_script("return document.body.scrollHeight") - 10: # Небольшой допуск
                     logger.info("Похоже, достигнут конец страницы (по позиции скролла).")
                     no_new_tweets_count += 1 # Увеличиваем счетчик, если внизу страницы и ничего не загрузилось
                # Не прерываем цикл сразу, дадим шанс обработать уже загруженные

            # time.sleep(3) # Заменено на WebDriverWait

            tweet_elements = find_all_tweets(driver)
            debug_print(f"Найдено {len(tweet_elements)} твитов на странице после скролла/ожидания")

            new_tweets_this_iteration = 0

            for tweet_element in tweet_elements:
                tweet_url = ""
                tweet_id = ""
                try:
                    # Извлекаем URL и ID твита (без изменений)
                    links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
                    for link in links:
                        href = link.get_attribute('href')
                        if href and "/status/" in href:
                            if f"/{username}/status/" in href or tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"]'):
                                tweet_url = href
                                tweet_id = href.split("/status/")[1].split("?")[0]
                                break

                    if not tweet_id or tweet_id in processed_tweet_ids:
                        continue

                    processed_tweet_ids.add(tweet_id)
                    debug_print(f"Обработка твита ID: {tweet_id}")
                    logger.info(f"Обработка твита ID: {tweet_id}")

                    # Сначала пробуем получить данные через API (без изменений)
                    api_tweet_data_raw = get_tweet_by_id(tweet_id)
                    api_tweet_data = None
                    if api_tweet_data_raw:
                         api_tweet_data = process_api_tweet_data(api_tweet_data_raw, tweet_url)

                    if api_tweet_data and api_tweet_data.get("text"):
                        debug_print(f"Твит {tweet_id} успешно получен через API")
                        logger.info(f"Твит {tweet_id} успешно получен через API")
                        tweets_data.append(api_tweet_data)
                        new_tweets_this_iteration += 1
                        if db_connection and user_id and save_tweet_to_db:
                            save_tweet_to_db(db_connection, user_id, api_tweet_data)
                        continue

                    # Если API не сработал, используем Selenium
                    debug_print(f"API не вернул данные для {tweet_id}, используем Selenium")

                    # Скроллируем к элементу и ждем видимости перед раскрытием
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet_element)
                        WebDriverWait(driver, 5).until(EC.visibility_of(tweet_element))
                        # time.sleep(1) # Заменено
                        was_expanded = expand_tweet_content_improved(driver, tweet_element) # Эта функция теперь тоже содержит ожидания
                        if was_expanded:
                            debug_print("Попытка раскрытия твита выполнена")
                            logger.info("Попытка раскрытия твита выполнена")
                            # time.sleep(2) # Убрано, т.к. expand_tweet_content_improved уже ждет
                    except TimeoutException:
                        logger.warning(f"Таймаут ожидания видимости твита {tweet_id} перед раскрытием.")
                    except StaleElementReferenceException:
                         logger.warning(f"Твит {tweet_id} устарел перед попыткой раскрытия.")
                         continue # Пропускаем этот устаревший твит
                    except Exception as e:
                         if "stale element reference" not in str(e).lower():
                            debug_print(f"Не удалось прокрутить/раскрыть твит {tweet_id}: {e}")
                            logger.warning(f"Не удалось прокрутить/раскрыть твит {tweet_id}: {e}")

                    # Извлекаем текст твита (без изменений)
                    tweet_text = ""
                    try:
                        # Добавим небольшое ожидание текста, на случай если он подгружается после раскрытия
                        tweet_text_element = WebDriverWait(driver, 3).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="tweetText"]'))
                        )
                        # tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                        tweet_text = tweet_text_element.text
                    except TimeoutException:
                         logger.warning(f"Таймаут ожидания текста твита {tweet_id}")
                    except NoSuchElementException:
                        debug_print("Текст твита не найден стандартным селектором")
                        try:
                            lang_elements = tweet_element.find_elements(By.CSS_SELECTOR, '[lang][dir="auto"]')
                            if lang_elements:
                                tweet_text = lang_elements[0].text
                        except:
                             pass

                    # Проверяем, нужно ли получить полный текст (без изменений)
                    need_full_text = False
                    if extract_full_tweets and tweet_text and is_tweet_truncated(tweet_element):
                         need_full_text = True

                    if need_full_text and get_full_tweet_text:
                        debug_print(f"Твит обрезан, получаем полную версию через отдельное открытие...")
                        logger.info(f"Твит обрезан, получаем полную версию через отдельное открытие...")
                        full_text = get_full_tweet_text(driver, tweet_url, max_attempts=3) # get_full_tweet_text тоже использует ожидания
                        if full_text and len(full_text) > len(tweet_text):
                            debug_print(f"Получен полный текст твита ({len(full_text)} символов)")
                            logger.info(f"Получен полный текст твита ({len(full_text)} символов)")
                            tweet_text = full_text

                    # Извлекаем время публикации (без изменений)
                    created_at = ""
                    try:
                        time_element = tweet_element.find_element(By.TAG_NAME, 'time')
                        created_at = time_element.get_attribute('datetime')
                    except NoSuchElementException:
                        logger.warning(f"Не удалось найти время для твита {tweet_id}")
                        continue

                    # Извлекаем статистику (без изменений)
                    stats = extract_tweet_stats(tweet_element)
                    debug_print(f"Извлеченная статистика твита: {stats}")
                    if stats['likes'] == 0 and stats['retweets'] == 0 and stats['replies'] == 0:
                        debug_print("ВНИМАНИЕ: Не удалось извлечь статистику!")
                        logger.warning(f"Не удалось извлечь статистику для твита {tweet_id}")

                    # Определяем ретвит (без изменений)
                    retweet_info = extract_retweet_info_enhanced(tweet_element)

                    # Формируем данные твита (без изменений)
                    tweet_data = {
                        "text": tweet_text,
                        "created_at": created_at,
                        "url": tweet_url,
                        "stats": stats,
                        "is_retweet": retweet_info["is_retweet"],
                        "original_author": retweet_info.get("original_author", None),
                        "is_truncated": need_full_text
                    }

                    # Добавляем твит в список
                    tweets_data.append(tweet_data)
                    new_tweets_this_iteration += 1

                    # Сохраняем твит в базу данных (без изменений)
                    if db_connection and user_id and save_tweet_to_db:
                        tweet_db_id = save_tweet_to_db(db_connection, user_id, tweet_data)

                    debug_print(f"Добавлен твит: {created_at} | {tweet_text[:50]}...")
                    logger.info(f"Добавлен твит ID: {tweet_id}")

                except StaleElementReferenceException:
                    logger.warning(f"Элемент твита устарел, пропускаем: {tweet_id}")
                    if tweet_id and tweet_id in processed_tweet_ids:
                         processed_tweet_ids.remove(tweet_id)
                except KeyError as e:
                     logger.error(f"Ошибка KeyError при обработке твита {tweet_id}: {e}. Ключ '{e}' отсутствует в retweet_info: {retweet_info}")
                     continue
                except Exception as e:
                    print(f"Ошибка при обработке твита {tweet_id}: {e}")
                    logger.error(f"Ошибка при обработке твита {tweet_id}: {e}")
                    import traceback
                    logger.error(traceback.format_exc()) # Логируем полный traceback
                    # traceback.print_exc() # Печатаем traceback для детальной отладки

            # Обновляем счетчик попыток без новых твитов
            if new_tweets_this_iteration == 0:
                no_new_tweets_count += 1
                debug_print(f"Не найдено новых твитов в этой итерации скролла. Счетчик: {no_new_tweets_count}/{max_no_new_tweets}")
                logger.info(f"Не найдено новых твитов в этой итерации скролла. Счетчик: {no_new_tweets_count}/{max_no_new_tweets}")
            else:
                no_new_tweets_count = 0 # Сбрасываем счетчик, если нашли новые твиты
                debug_print(f"Добавлено {new_tweets_this_iteration} новых твитов в этой итерации")
                logger.info(f"Добавлено {new_tweets_this_iteration} новых твитов в этой итерации")

            # Проверка достижения конца страницы (улучшенная)
            try:
                current_height = driver.execute_script("return document.body.scrollHeight")
                # Если высота перестала значительно увеличиваться после скролла и ожидания
                if abs(current_height - last_height) < 50 and no_new_tweets_count > 0:
                    debug_print(f"Высота страницы почти не изменилась ({last_height} -> {current_height}) и нет новых твитов. Возможно, достигнут конец.")
                    logger.info(f"Высота страницы почти не изменилась ({last_height} -> {current_height}) и нет новых твитов. Возможно, достигнут конец.")
                    # Добавим еще одну проверку через пару секунд на всякий случай
                    time.sleep(2) # Короткая пауза перед финальной проверкой высоты
                    final_height = driver.execute_script("return document.body.scrollHeight")
                    if abs(final_height - current_height) < 50:
                         debug_print("Финальная проверка высоты подтверждает конец страницы. Завершаем скроллинг.")
                         logger.info("Финальная проверка высоты подтверждает конец страницы. Завершаем скроллинг.")
                         break
                    else:
                         last_height = final_height # Обновляем высоту, если она все же изменилась
                # else:
                #      last_height = current_height # Обновляем высоту для следующей итерации (перенесено выше в блок try ожидания)

            except Exception as e:
                 logger.warning(f"Ошибка при проверке конца страницы: {e}")


        debug_print(f"Завершен скроллинг после {scroll_attempts} попыток")
        logger.info(f"Завершен скроллинг после {scroll_attempts} попыток")
        debug_print(f"Всего уникальных твитов обнаружено: {len(processed_tweet_ids)}")
        logger.info(f"Всего уникальных твитов обнаружено: {len(processed_tweet_ids)}")
        debug_print(f"Всего твитов собрано до фильтрации: {len(tweets_data)}")
        logger.info(f"Всего твитов собрано до фильтрации: {len(tweets_data)}")

        # Фильтруем твиты по времени (без изменений)
        debug_print(f"Фильтрация твитов за последние {time_filter_hours} часов...")
        logger.info(f"Фильтрация твитов за последние {time_filter_hours} часов...")
        recent_tweets = filter_recent_tweets(tweets_data, time_filter_hours)
        debug_print(f"Из них свежих твитов: {len(recent_tweets)}")
        logger.info(f"Из них свежих твитов: {len(recent_tweets)}")

        # Сохраняем все собранные твиты в кэш (без изменений)
        cached_result = {
            "username": username,
            "name": result["name"],
            "tweets": tweets_data,
        }

        if use_cache:
            try:
                debug_print(f"Сохранение {len(tweets_data)} твитов в кэш: {cache_file}")
                logger.info(f"Сохранение {len(tweets_data)} твитов в кэш: {cache_file}")
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cached_result, f, ensure_ascii=False, indent=2)
                debug_print(f"Кэш успешно сохранен")
                logger.info(f"Кэш успешно сохранен")
            except Exception as e:
                print(f"Ошибка при сохранении кэша: {e}")
                logger.error(f"Ошибка при сохранении кэша: {e}")

        # Возвращаем только свежие твиты, ограниченные max_tweets (без изменений)
        result["tweets"] = recent_tweets[:max_tweets]
        print(f"Возвращаем {len(result['tweets'])} свежих твитов для @{username}")
        logger.info(f"Возвращаем {len(result['tweets'])} свежих твитов для @{username}")

        return result

    except Exception as e:
        print(f"Критическая ошибка при получении твитов для @{username} через Selenium: {e}")
        logger.critical(f"Критическая ошибка при получении твитов для @{username} через Selenium: {e}")
        import traceback
        logger.error(traceback.format_exc()) # Логируем полный traceback
        # traceback.print_exc()
        return result # Возвращаем то, что успели собрать

