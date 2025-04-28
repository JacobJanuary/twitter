#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для извлечения твитов из Twitter
Содержит функции для получения твитов, их обработки и сохранения
(Функционал обработки статей удален, time.sleep заменен на WebDriverWait)
"""

import os
import json
import time # Оставляем для редких случаев, где WebDriverWait не подходит
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
from twitter_scraper_utils import extract_tweet_stats
from twitter_scraper_retweet_utils import extract_retweet_info_enhanced
from twitter_scraper_links_utils import (
    extract_all_links_from_tweet,
    is_tweet_truncated,
    get_full_tweet_text,
    extract_full_tweet_text_from_html
)

# Настройка логирования
logger = logging.getLogger('twitter_scraper.tweets')

# Директории для кэширования
CACHE_DIR = "twitter_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

HTML_CACHE_DIR = "twitter_html_cache"
os.makedirs(HTML_CACHE_DIR, exist_ok=True)

# --- Функции expand_tweet_content и find_all_tweets остаются без изменений,
# --- так как они не используют time.sleep для ожидания ---
def expand_tweet_content(driver, tweet_element):
    """
    Расширяет содержимое твита, нажимая на кнопку "Показать ещё" или "Show more".
    Использует WebDriverWait для ожидания кнопки.
    """
    expanded = False
    wait = WebDriverWait(driver, 5) # Короткое ожидание для кнопки
    show_more_selectors = [
        ".//div[@role='button' and (contains(., 'Show more') or contains(., 'Показать ещё'))]",
        ".//span[contains(., 'Show more') or contains(., 'Показать ещё')]",
        # Дополнительные селекторы, если стандартные не сработают
        ".//div[contains(@class, 'r-1777fci') and contains(., 'more')]" # Пример класса
    ]

    for selector in show_more_selectors:
        try:
            # Используем find_elements для проверки наличия без выбрасывания исключения
            buttons = tweet_element.find_elements(By.XPATH, selector)
            if buttons:
                logger.info(f"Найдена кнопка раскрытия через селектор: {selector}")
                button_to_click = buttons[0] # Берем первую найденную
                try:
                    # Прокручиваем к кнопке и ждем кликабельности
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button_to_click)
                    clickable_button = wait.until(EC.element_to_be_clickable(button_to_click))

                    # Пробуем кликнуть
                    try:
                        clickable_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", clickable_button) # Резервный JS клик

                    # Ждем исчезновения кнопки или изменения текста (сложно надежно определить)
                    # Вместо sleep, можно подождать немного или проверить текст
                    time.sleep(1.5) # Короткий sleep после клика может быть оправдан
                    logger.info("Клик по кнопке 'Show more' выполнен.")
                    expanded = True
                    return expanded # Выходим после успешного клика
                except TimeoutException:
                    logger.warning(f"Кнопка '{selector}' найдена, но не стала кликабельной вовремя.")
                except Exception as e:
                    logger.warning(f"Ошибка при клике на кнопку '{selector}': {e}")
        except Exception as e:
            # Игнорируем ошибки поиска, пробуем следующий селектор
            logger.debug(f"Ошибка при поиске кнопки '{selector}': {e}")
            continue

    # Проверка на многоточие как резервный вариант
    if not expanded:
        try:
            tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
            tweet_text = tweet_text_element.text.strip()
            if tweet_text.endswith('…') or tweet_text.endswith('...'):
                logger.info("Найдено многоточие в конце текста, твит может быть обрезан (кнопка 'Show more' не найдена/не сработала)")
                return False # Указываем, что нужно открыть отдельно
        except NoSuchElementException:
            pass # Текст твита не найден

    return expanded # Возвращаем False, если не удалось раскрыть

def find_all_tweets(driver):
    """
    Расширенный поиск твитов с несколькими стратегиями.
    Не использует time.sleep.
    """
    tweets = []
    try:
        # Стратегия 1: Стандартный селектор
        standard_tweets = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        if standard_tweets:
            tweets.extend(standard_tweets)
            logger.debug(f"Найдено {len(standard_tweets)} твитов по стандартному селектору")

        # Стратегия 2: Расширенный селектор (если мало твитов)
        if len(tweets) < 5:
            timeline_items = driver.find_elements(By.CSS_SELECTOR, '[data-testid="cellInnerDiv"]')
            new_tweets = []
            for item in timeline_items:
                # Проверяем, содержит ли элемент время (признак твита)
                # и не является ли он уже добавленным твитом
                if item.find_elements(By.TAG_NAME, 'time') and item not in tweets:
                     # Дополнительная проверка, что это действительно твит (например, по наличию User-Name)
                     if item.find_elements(By.CSS_SELECTOR, '[data-testid="User-Name"]'):
                         new_tweets.append(item)
            if new_tweets:
                tweets.extend(new_tweets)
                logger.debug(f"Найдено дополнительно {len(new_tweets)} твитов по расширенному селектору")
    except Exception as e:
        logger.error(f"Ошибка при поиске твитов: {e}")

    logger.info(f"Всего найдено твитов на странице: {len(tweets)}")
    return tweets


# Функция expand_tweet_content_improved удалена, т.к. логика объединена в expand_tweet_content

def process_tweet_fallback(driver, tweet_url, username):
    """
    Резервный метод обработки твита. Использует WebDriverWait.
    """
    tweet_data = None
    current_window = driver.current_window_handle
    wait = WebDriverWait(driver, 20) # Ожидание для загрузки страницы твита

    try:
        # Открываем новую вкладку
        driver.execute_script("window.open('');")
        # time.sleep(1) # Заменено ожиданием
        wait.until(EC.number_of_windows_to_be(len(driver.window_handles))) # Ждем открытия новой вкладки
        driver.switch_to.window(driver.window_handles[-1])

        # Загружаем твит напрямую
        logger.info(f"Применяем резервный метод обработки для твита: {tweet_url}")
        driver.get(tweet_url)

        # Ждем загрузки основного элемента твита
        tweet_container_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        tweet_element = wait.until(EC.presence_of_element_located(tweet_container_locator))
        logger.info("Основной контейнер твита загружен (резервный метод).")

        # Извлекаем данные твита
        tweet_data = {
            "text": "",
            "created_at": "",
            "url": tweet_url,
            "stats": {"likes": 0, "retweets": 0, "replies": 0},
            "is_retweet": False,
            "original_author": None,
            "is_truncated": False
        }

        # Извлекаем текст твита (ждем появления элемента с текстом)
        text_locator = (By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
        try:
            text_element = wait.until(EC.visibility_of_element_located(text_locator))
            tweet_data["text"] = text_element.text
        except TimeoutException:
            logger.warning("Не удалось найти текст твита (резервный метод).")
            # Попробуем другой селектор
            try:
                 alt_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[lang]')
                 tweet_data["text"] = alt_text_element.text
            except NoSuchElementException:
                 logger.warning("Альтернативный селектор текста также не найден.")


        # Извлекаем время публикации (ждем появления time)
        time_locator = (By.TAG_NAME, 'time')
        try:
            time_element = wait.until(EC.presence_of_element_located(time_locator))
            tweet_data["created_at"] = time_element.get_attribute('datetime')
        except TimeoutException:
             logger.warning("Не удалось найти время публикации твита (резервный метод).")

        # Извлекаем статистику (элементы статистики могут подгружаться позже)
        try:
            # Ждем появления хотя бы одной кнопки статистики
            stats_button_locator = (By.CSS_SELECTOR, 'div[data-testid="reply"], div[data-testid="retweet"], div[data-testid="like"]')
            wait.until(EC.presence_of_element_located(stats_button_locator))
            # Извлекаем статистику, используя функцию из utils
            tweet_data["stats"] = extract_tweet_stats(tweet_element)
        except TimeoutException:
            logger.warning("Не удалось дождаться элементов статистики (резервный метод).")
        except Exception as e:
             logger.error(f"Ошибка при извлечении статистики (резервный метод): {e}")


        # Определяем, является ли твит ретвитом
        try:
            retweet_info = extract_retweet_info_enhanced(tweet_element)
            tweet_data["is_retweet"] = retweet_info["is_retweet"]
            tweet_data["original_author"] = retweet_info["original_author"]
        except Exception as e:
             logger.error(f"Ошибка при определении ретвита (резервный метод): {e}")


        logger.info(f"Успешно применен резервный метод для твита")

    except TimeoutException:
         logger.error(f"Таймаут при загрузке страницы твита (резервный метод): {tweet_url}")
    except Exception as e:
        logger.error(f"Ошибка при резервной обработке твита {tweet_url}: {e}")
    finally:
        # Закрываем вкладку и возвращаемся
        try:
            if len(driver.window_handles) > 1: # Закрываем только если есть доп. вкладка
                driver.close()
            driver.switch_to.window(current_window)
        except Exception as e:
            logger.error(f"Ошибка при закрытии вкладки или переключении: {e}")
            # Попытка переключиться на основное окно в любом случае
            try:
                driver.switch_to.window(current_window)
            except:
                 pass

    return tweet_data


def get_tweet_from_api(tweet_url):
    """
    Получает твит через API (без изменений).
    """
    try:
        from twitter_api_client import get_tweet_by_id, process_api_tweet_data
        if "/status/" in tweet_url:
            tweet_id = tweet_url.split("/status/")[1].split("?")[0]
        else:
            return None
        api_data = get_tweet_by_id(tweet_id)
        tweet_data = process_api_tweet_data(api_data, tweet_url)
        return tweet_data
    except Exception as e:
        logger.error(f"Ошибка при запросе твита через API: {e}")
        return None

def get_tweets_with_selenium(username, driver, db_connection=None, max_tweets=10, use_cache=True,
                             cache_duration_hours=1, time_filter_hours=24, force_refresh=False,
                             extract_full_tweets=True, extract_links=True,
                             dependencies=None, html_cache_dir="twitter_html_cache"):
    """
    Получает твиты пользователя с помощью Selenium. Использует WebDriverWait.
    """
    if dependencies is None: dependencies = {}
    # Получаем функции из зависимостей
    debug_print = dependencies.get('debug_print', lambda *args, **kwargs: None)
    save_user_to_db = dependencies.get('save_user_to_db', lambda *args, **kwargs: None)
    save_tweet_to_db = dependencies.get('save_tweet_to_db', lambda *args, **kwargs: None)
    filter_recent_tweets = dependencies.get('filter_recent_tweets', lambda *args, **kwargs: [])
    extract_tweet_stats = dependencies.get('extract_tweet_stats', lambda *args, **kwargs: {})
    # Используем enhanced версию, если она есть, иначе базовую
    extract_retweet_info_func = dependencies.get('extract_retweet_info_enhanced',
                                                 dependencies.get('extract_retweet_info', lambda *args, **kwargs: {}))
    is_tweet_truncated = dependencies.get('is_tweet_truncated', lambda *args, **kwargs: False)
    get_full_tweet_text = dependencies.get('get_full_tweet_text', lambda *args, **kwargs: "")
    save_links_to_db = dependencies.get('save_links_to_db', lambda *args, **kwargs: None)
    extract_all_links_from_tweet = dependencies.get('extract_all_links_from_tweet', lambda *args, **kwargs: {})

    print(f"Начинаем получение твитов для @{username}...")
    logger.info(f"Начинаем получение твитов для @{username}...")
    cache_file = os.path.join(CACHE_DIR, f"{username}_tweets_selenium.json")
    result = {"username": username, "name": username, "tweets": []}
    wait = WebDriverWait(driver, 20) # Основное ожидание для страницы профиля

    # --- Логика кэширования остается прежней ---
    if use_cache and os.path.exists(cache_file) and not force_refresh:
        try:
            # ... (код проверки кэша) ...
            file_modified_time = os.path.getmtime(cache_file)
            current_time = time.time()
            if current_time - file_modified_time < cache_duration_hours * 3600:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                logger.info(f"Используем кэшированные данные для @{username}")
                result["name"] = cached_data.get("name", username)
                recent_tweets = filter_recent_tweets(cached_data.get('tweets', []), time_filter_hours)
                result["tweets"] = recent_tweets[:max_tweets]
                if recent_tweets:
                    return result
                else:
                    logger.info(f"В кэше нет свежих твитов, запрашиваем новые.")
        except Exception as e:
            logger.error(f"Ошибка при чтении кэша для @{username}: {e}")
    elif force_refresh:
        logger.info(f"Принудительное обновление данных для @{username}")

    try:
        profile_url = f"https://twitter.com/{username}"
        logger.info(f"Загружаем страницу профиля: {profile_url}")
        driver.get(profile_url)

        # Ждем загрузки первого твита или сообщения об ошибке/пустой ленте
        first_tweet_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        error_message_locator = (By.XPATH, "//*[contains(text(), \"This account doesn’t exist\") or contains(text(), \"Hmm...this page doesn’t exist\")]")
        empty_timeline_locator = (By.XPATH, "//*[contains(text(), \"The timeline is empty\")]") # Пример

        try:
            # Ждем появления одного из этих состояний
            wait.until(EC.any_of(
                EC.presence_of_element_located(first_tweet_locator),
                EC.presence_of_element_located(error_message_locator),
                EC.presence_of_element_located(empty_timeline_locator)
            ))
            logger.info("Страница профиля загружена (или обнаружено сообщение об ошибке/пустой ленте).")
        except TimeoutException:
            logger.warning("Таймаут при ожидании загрузки твитов/сообщений на странице профиля. Попытка продолжить...")
            # Можно добавить проверку на наличие признаков незалогиненности
            page_source_check = driver.page_source
            if "Log in" in page_source_check and "Sign up" in page_source_check:
                 logger.warning("Обнаружены признаки отсутствия авторизации.")
                 # Можно вернуть пустой результат или попытаться авторизоваться
                 return result # Возвращаем пустой результат в этом случае

        # Проверяем наличие ошибок или пустой ленты уже после ожидания
        if driver.find_elements(*error_message_locator):
            logger.error(f"Аккаунт @{username} не существует или недоступен.")
            return result
        if driver.find_elements(*empty_timeline_locator):
             logger.info(f"Лента твитов для @{username} пуста.")
             # Сохраняем пустой результат в кэш, если нужно
             if use_cache:
                 try:
                     cached_result = {"username": username, "name": result["name"], "tweets": []}
                     with open(cache_file, 'w', encoding='utf-8') as f:
                         json.dump(cached_result, f, ensure_ascii=False, indent=2)
                     logger.info(f"Пустой результат сохранен в кэш для @{username}")
                 except Exception as e:
                     logger.error(f"Ошибка при сохранении пустого кэша: {e}")
             return result


        # --- Логика извлечения имени и сохранения пользователя остается прежней ---
        try:
            # Попробуем извлечь имя из заголовка страницы
            title = driver.title
            if "(" in title:
                name = title.split("(")[0].strip()
                result["name"] = name
                logger.info(f"Извлечено имя пользователя из title: {name}")
            else:
                # Попробуем извлечь имя из data-testid="UserName"
                try:
                    name_element = wait.until(EC.visibility_of_element_located(
                        (By.CSS_SELECTOR, '[data-testid="UserName"] span span')
                    ))
                    result["name"] = name_element.text.strip()
                    logger.info(f"Извлечено имя пользователя из data-testid: {result['name']}")
                except TimeoutException:
                    logger.warning("Не удалось извлечь имя пользователя.")
                    result["name"] = username # Используем username как запасной вариант
        except Exception as e:
            logger.error(f"Ошибка при извлечении имени пользователя: {e}")
            result["name"] = username

        user_id = None
        if db_connection and save_user_to_db:
            logger.info(f"Сохранение/обновление пользователя @{username} в БД...")
            user_id = save_user_to_db(db_connection, username, result["name"])
            if user_id:
                logger.info(f"Пользователь @{username} сохранен/обновлен в БД с ID: {user_id}")
            else:
                logger.error(f"Ошибка при сохранении пользователя @{username} в БД.")

        # --- Логика скроллинга с WebDriverWait ---
        processed_tweet_ids = set()
        tweets_data = []
        scroll_attempts = 0
        max_scroll_attempts = 30 # Уменьшаем немного, т.к. ждем явно
        no_new_tweets_count = 0
        max_no_new_tweets = 4 # Уменьшаем немного

        logger.info("Начинаем скроллинг и сбор твитов...")
        last_tweet_count = 0

        while scroll_attempts < max_scroll_attempts and no_new_tweets_count < max_no_new_tweets and len(tweets_data) < max_tweets:
            scroll_attempts += 1
            logger.debug(f"Попытка скроллинга #{scroll_attempts}...")

            # Находим текущие твиты
            current_tweet_elements = find_all_tweets(driver)
            current_tweet_count = len(current_tweet_elements)
            logger.debug(f"Найдено {current_tweet_count} твитов на странице.")

            # Обрабатываем только новые твиты (сравниваем элементы, не только ID)
            new_tweets_processed_this_iteration = 0
            for tweet_element in current_tweet_elements:
                 # Получаем URL и ID твита
                 tweet_url = ""
                 tweet_id = ""
                 try:
                     # Ищем ссылку на статус внутри элемента
                     status_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
                     for link in status_links:
                         href = link.get_attribute('href')
                         # Проверяем, что ссылка содержит /status/ и не ведет на аналитику и т.п.
                         if href and "/status/" in href and not any(x in href for x in ["/analytics", "/likes", "/retweets"]):
                             tweet_url = href
                             tweet_id = href.split("/status/")[1].split("?")[0]
                             break # Берем первую подходящую ссылку
                 except StaleElementReferenceException:
                      logger.warning("Элемент твита устарел при поиске URL, пропуск.")
                      continue
                 except Exception as e:
                      logger.error(f"Неожиданная ошибка при поиске URL твита: {e}")
                      continue


                 # Если твит без ID или уже обработан, пропускаем
                 if not tweet_id or tweet_id in processed_tweet_ids:
                     continue

                 # --- Попытка получить через API (остается без изменений) ---
                 api_tweet_data = get_tweet_from_api(tweet_url)
                 if api_tweet_data and api_tweet_data.get("text"):
                     tweets_data.append(api_tweet_data)
                     processed_tweet_ids.add(tweet_id)
                     new_tweets_processed_this_iteration += 1
                     logger.info(f"Твит {tweet_id} успешно получен через API.")
                     # Сохраняем в БД
                     if db_connection and user_id:
                         tweet_db_id = save_tweet_to_db(db_connection, user_id, api_tweet_data)
                         if extract_links and tweet_db_id and api_tweet_data.get("links") and save_links_to_db:
                             save_links_to_db(db_connection, tweet_db_id, api_tweet_data["links"])
                     continue # Переходим к следующему элементу

                 # --- Обработка через Selenium ---
                 processed_tweet_ids.add(tweet_id) # Добавляем ID, чтобы не обрабатывать повторно
                 logger.debug(f"Обработка твита ID: {tweet_id} через Selenium...")

                 tweet_data_selenium = {} # Данные из Selenium
                 try:
                     # Прокручиваем к элементу для надежности (опционально, может замедлить)
                     # driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet_element)
                     # time.sleep(0.5) # Короткая пауза после прокрутки

                     # Раскрываем твит, если нужно
                     was_expanded = expand_tweet_content(driver, tweet_element)
                     if was_expanded:
                         logger.debug(f"Твит {tweet_id} был раскрыт.")
                         # После раскрытия элементы могут обновиться, лучше найти их заново
                         # Но для простоты пока оставим так

                     # Извлекаем текст
                     tweet_text = ""
                     try:
                         text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                         tweet_text = text_element.text
                     except NoSuchElementException:
                         logger.debug(f"Текст не найден в data-testid='tweetText' для {tweet_id}")
                         # Попробуем другой селектор
                         try:
                             alt_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[lang]')
                             tweet_text = alt_text_element.text
                         except NoSuchElementException:
                              logger.warning(f"Текст твита {tweet_id} не найден.")


                     # Проверка на необходимость полного текста
                     is_truncated_flag = False
                     if extract_full_tweets and tweet_text and is_tweet_truncated(tweet_element):
                          logger.info(f"Твит {tweet_id} помечен как обрезанный, получаем полную версию...")
                          full_text = get_full_tweet_text(driver, tweet_url) # Эта функция уже использует WebDriverWait
                          if full_text and len(full_text) > len(tweet_text):
                               logger.info(f"Получен полный текст для {tweet_id} ({len(full_text)} симв.)")
                               tweet_text = full_text
                               is_truncated_flag = True
                          else:
                               logger.warning(f"Не удалось получить полный текст для {tweet_id} или он не длиннее.")


                     # Извлекаем время
                     created_at = ""
                     try:
                         time_element = tweet_element.find_element(By.TAG_NAME, 'time')
                         created_at = time_element.get_attribute('datetime')
                     except NoSuchElementException:
                         logger.warning(f"Время публикации для {tweet_id} не найдено.")

                     # Извлекаем статистику
                     stats = extract_tweet_stats(tweet_element)

                     # Информация о ретвите
                     retweet_info = extract_retweet_info_func(tweet_element)

                     # Собираем данные
                     if tweet_text: # Сохраняем только если есть текст
                         tweet_data_selenium = {
                             "text": tweet_text,
                             "created_at": created_at,
                             "url": tweet_url,
                             "stats": stats,
                             "is_retweet": retweet_info.get("is_retweet", False),
                             "original_author": retweet_info.get("original_author"),
                             "is_truncated": is_truncated_flag
                         }

                         # Извлекаем ссылки
                         if extract_links and extract_all_links_from_tweet:
                              tweet_data_selenium["links"] = extract_all_links_from_tweet(tweet_element, username, expand_first=False)

                         tweets_data.append(tweet_data_selenium)
                         new_tweets_processed_this_iteration += 1
                         logger.info(f"Добавлен твит {tweet_id} (Selenium).")

                         # Сохраняем в БД
                         if db_connection and user_id:
                             tweet_db_id = save_tweet_to_db(db_connection, user_id, tweet_data_selenium)
                             if extract_links and tweet_db_id and tweet_data_selenium.get("links") and save_links_to_db:
                                 save_links_to_db(db_connection, tweet_db_id, tweet_data_selenium["links"])

                     else:
                         # Если текста нет, но есть URL, возможно стоит применить fallback
                         logger.warning(f"Нет текста для твита {tweet_id}, пропуск (или нужен fallback).")
                         # Можно добавить вызов process_tweet_fallback здесь, если нужно

                 except StaleElementReferenceException:
                     logger.warning(f"Элемент твита {tweet_id} устарел во время обработки, пропуск.")
                     processed_tweet_ids.remove(tweet_id) # Убираем ID, чтобы попробовать снова на след. итерации
                 except Exception as e:
                     logger.error(f"Ошибка при обработке твита {tweet_id} через Selenium: {e}", exc_info=True)


            # --- Логика скроллинга и проверки остановки ---
            if new_tweets_processed_this_iteration == 0 and current_tweet_count == last_tweet_count:
                 no_new_tweets_count += 1
                 logger.info(f"Новых твитов не добавлено. Счетчик остановки: {no_new_tweets_count}/{max_no_new_tweets}")
            else:
                 no_new_tweets_count = 0 # Сбрасываем счетчик, если были добавлены новые твиты
                 logger.info(f"Добавлено {new_tweets_processed_this_iteration} новых твитов в этой итерации.")

            last_tweet_count = current_tweet_count # Обновляем счетчик для следующей итерации

            # Прокручиваем страницу вниз
            if no_new_tweets_count < max_no_new_tweets and len(tweets_data) < max_tweets:
                 driver.execute_script("window.scrollBy(0, 1000);") # Скроллим на 1000 пикселей
                 # Вместо sleep, ждем изменения высоты страницы или появления нового твита
                 try:
                      # Ждем, пока количество твитов не увеличится или не пройдет таймаут
                      wait_short = WebDriverWait(driver, 5) # Короткое ожидание после скролла
                      wait_short.until(lambda d: len(find_all_tweets(d)) > current_tweet_count)
                      logger.debug("Обнаружены новые твиты после скролла.")
                 except TimeoutException:
                      logger.debug("Новые твиты не появились сразу после скролла (или таймаут).")
                      # Можно добавить проверку на достижение конца страницы
                      viewport_height = driver.execute_script("return window.innerHeight")
                      document_height = driver.execute_script("return document.documentElement.scrollHeight")
                      current_scroll_y = driver.execute_script("return window.scrollY")
                      if current_scroll_y + viewport_height >= document_height - 10: # Небольшой допуск
                           logger.info("Вероятно, достигнут конец страницы.")
                           break # Выходим из цикла скроллинга


        logger.info(f"Завершен скроллинг после {scroll_attempts} попыток.")
        logger.info(f"Всего уникальных твитов обнаружено/обработано: {len(processed_tweet_ids)}")
        logger.info(f"Всего твитов собрано в список: {len(tweets_data)}")

        # --- Дополнительная проверка через BeautifulSoup остается без изменений, т.к. не использует Selenium waits ---
        # ... (код BS4 проверки) ...
        logger.info("Выполняем дополнительную проверку на пропущенные твиты через BeautifulSoup...")
        try:
            # Скроллим до конца еще раз для надежности
            last_h = driver.execute_script("return document.body.scrollHeight")
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5) # Короткий sleep здесь может быть оправдан
                new_h = driver.execute_script("return document.body.scrollHeight")
                if new_h == last_h:
                    break
                last_h = new_h

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            tweets_bs4 = soup.select('article[data-testid="tweet"]')
            logger.info(f"BeautifulSoup: найдено {len(tweets_bs4)} твитов для доп. проверки.")
            bs4_added_count = 0
            for tweet_bs in tweets_bs4:
                # ... (логика извлечения ID и данных из BS4) ...
                tweet_url_bs = ""
                tweet_id_bs = ""
                link_bs = tweet_bs.select_one('a[href*="/status/"]')
                if link_bs:
                    href_bs = link_bs.get('href')
                    if href_bs and "/status/" in href_bs:
                         tweet_url_bs = f"https://twitter.com{href_bs}"
                         tweet_id_bs = href_bs.split("/status/")[1].split("?")[0]

                if not tweet_id_bs or tweet_id_bs in processed_tweet_ids:
                    continue

                processed_tweet_ids.add(tweet_id_bs) # Добавляем, чтобы не дублировать
                logger.info(f"BS4: Найден новый/пропущенный твит с ID {tweet_id_bs}")

                # ... (извлечение текста, времени и т.д. из BS4) ...
                text_bs = tweet_bs.select_one('div[data-testid="tweetText"]')
                text_bs = text_bs.text if text_bs else ""
                time_bs = tweet_bs.find('time')
                created_at_bs = time_bs.get('datetime') if time_bs else ""
                is_retweet_bs = bool(tweet_bs.select_one('span:-soup-contains("Retweeted")') or
                                     tweet_bs.select_one('span:-soup-contains("reposted")'))

                if text_bs: # Добавляем только если есть текст
                    tweet_data_bs = {
                        "text": text_bs, "created_at": created_at_bs, "url": tweet_url_bs,
                        "stats": {"likes": 0, "retweets": 0, "replies": 0}, # Статистику из BS4 не берем
                        "is_retweet": is_retweet_bs, "original_author": None, "is_truncated": False
                    }
                    tweets_data.append(tweet_data_bs)
                    bs4_added_count += 1
                    # Сохраняем в БД
                    if db_connection and user_id:
                        save_tweet_to_db(db_connection, user_id, tweet_data_bs) # Ссылки из BS4 не извлекаем
            logger.info(f"BS4: Добавлено {bs4_added_count} твитов.")
        except Exception as e:
             logger.error(f"Ошибка во время дополнительной проверки BS4: {e}")


        # --- Фильтрация и сохранение в кэш остаются прежними ---
        logger.info(f"Фильтрация твитов за последние {time_filter_hours} часов...")
        recent_tweets = filter_recent_tweets(tweets_data, time_filter_hours)
        logger.info(f"Из них свежих твитов: {len(recent_tweets)}")

        # Сохраняем все найденные (не только свежие) твиты в кэш
        if use_cache:
            try:
                cached_result = {"username": username, "name": result["name"], "tweets": tweets_data}
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cached_result, f, ensure_ascii=False, indent=2)
                logger.info(f"Кэш ({len(tweets_data)} твитов) сохранен: {cache_file}")
            except Exception as e:
                logger.error(f"Ошибка при сохранении кэша: {e}")

        # Возвращаем только свежие твиты, не более max_tweets
        result["tweets"] = recent_tweets[:max_tweets]
        logger.info(f"Возвращаем {len(result['tweets'])} свежих твитов для @{username}")

        return result

    except Exception as e:
        logger.error(f"Общая ошибка при получении твитов для @{username}: {e}", exc_info=True)
        # import traceback # Раскомментируйте для детальной трассировки
        # traceback.print_exc()
        return result # Возвращаем пустой или частично заполненный результат

