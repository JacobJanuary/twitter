#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для извлечения твитов из Twitter.
Обрабатывает ретвиты, сохраняя данные оригинального твита под ID оригинала.
URL также сохраняется от оригинала.
Использует WebDriverWait, API вызовы отключены.
"""

import os
import json
import time
import logging
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains

# Импорты утилит
from twitter_scraper_utils import extract_tweet_stats, parse_twitter_date, debug_print
from twitter_scraper_retweet_utils import extract_retweet_info_enhanced, get_author_info
from twitter_scraper_links_utils import (
    is_tweet_truncated,
    get_full_tweet_text,
)
# Импорт API клиента (заглушки)
from twitter_api_client import get_tweet_by_id, process_api_tweet_data

# Настройка логирования
logger = logging.getLogger('twitter_scraper.tweets')
if not logger.handlers:
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Директории для кэширования
CACHE_DIR = "twitter_cache"
os.makedirs(CACHE_DIR, exist_ok=True)
HTML_CACHE_DIR = "twitter_html_cache"
os.makedirs(HTML_CACHE_DIR, exist_ok=True)


# --- Функции expand_tweet_content, find_all_tweets, expand_tweet_content_improved ---
# (Код без изменений, как в v4)
def expand_tweet_content(driver, tweet_element):
    """Расширяет содержимое твита (код из v4)"""
    expanded = False; wait_timeout = 3; click_wait_timeout = 5
    try:
        show_more_selectors_xpath = [ './/div[@role="button" and (contains(., "Show more") or contains(., "Показать ещё"))]', './/span[contains(., "Show more") or contains(., "Показать ещё")]' ]
        show_more_button = None
        for selector in show_more_selectors_xpath:
            try:
                button = WebDriverWait(tweet_element, wait_timeout).until(EC.presence_of_element_located((By.XPATH, selector)))
                if button.is_displayed(): show_more_button = button; logger.debug(f"Найдена кнопка 'Show more' через: {selector}"); break
            except (TimeoutException, NoSuchElementException, StaleElementReferenceException): continue
        if show_more_button:
            try:
                initial_text = "";
                try: initial_text = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]').text
                except: pass
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", show_more_button)
                clickable_button = WebDriverWait(driver, wait_timeout).until(EC.element_to_be_clickable(show_more_button))
                clickable_button.click(); logger.info("Кликнули 'Show more'.")
                try:
                    WebDriverWait(driver, click_wait_timeout).until(EC.any_of(EC.staleness_of(show_more_button), EC.text_to_be_present_in_element((By.CSS_SELECTOR, 'div[data-testid="tweetText"]'), initial_text + " ") if initial_text else EC.staleness_of(show_more_button)))
                    logger.info("Контент твита раскрыт (подтверждено ожиданием)."); expanded = True
                except TimeoutException: logger.warning("Не удалось дождаться результата клика 'Show more'."); expanded = False
                except StaleElementReferenceException: logger.info("Кнопка 'Show more' исчезла после клика."); expanded = True
            except Exception as e: logger.warning(f"Ошибка при попытке раскрытия: {e}")
        if not expanded:
            try:
                tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                if tweet_text_element.text.strip().endswith(('…', '...')): return False
            except: pass
        return expanded
    except Exception as e:
        if "stale element reference" not in str(e).lower(): logger.error(f"Ошибка при раскрытии твита: {e}")
        return False

def find_all_tweets(driver):
    """Расширенный поиск твитов (код из v4)"""
    tweets = []; processed_elements = set(); wait_timeout = 5
    tweet_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
    try:
        standard_tweets = WebDriverWait(driver, wait_timeout).until(EC.presence_of_all_elements_located(tweet_locator))
        if standard_tweets:
            for tweet in standard_tweets:
                try:
                     if tweet.id not in processed_elements: tweets.append(tweet); processed_elements.add(tweet.id)
                except StaleElementReferenceException: continue
            logger.debug(f"Найдено {len(standard_tweets)} твитов по стандартному селектору (WebDriverWait)")
    except TimeoutException: logger.debug(f"Твиты по стандартному селектору не найдены за {wait_timeout} сек.")
    except Exception as e: logger.warning(f"Ошибка поиска по стандартному селектору: {e}")
    if len(tweets) < 5:
        try:
            timeline_items = driver.find_elements(By.CSS_SELECTOR, '[data-testid="cellInnerDiv"]')
            new_tweets_count = 0
            for item in timeline_items:
                try:
                    if item.id not in processed_elements and item.find_elements(By.TAG_NAME, 'time'):
                        if item.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]'):
                             tweets.append(item); processed_elements.add(item.id); new_tweets_count += 1
                except StaleElementReferenceException: continue
            if new_tweets_count > 0: logger.debug(f"Найдено дополнительно {new_tweets_count} твитов по расширенному селектору")
        except Exception as e: logger.warning(f"Ошибка поиска по расширенному селектору: {e}")
    logger.debug(f"Всего найдено уникальных твитов на странице: {len(tweets)}")
    return tweets

def expand_tweet_content_improved(driver, tweet_element):
    """Улучшенная функция раскрытия твита (код из v4)"""
    expanded = False; wait_timeout = 3; click_wait_timeout = 5
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet_element)
        selectors_xpath = [ './/div[@role="button" and (contains(text(), "Show more") or contains(text(), "Показать ещё"))]', './/span[contains(text(), "Show more") or contains(text(), "Показать ещё")]', './/div[contains(@class, "r-1sg46qm")]' ]
        show_more_button = None
        for selector in selectors_xpath:
            try:
                button = WebDriverWait(tweet_element, wait_timeout).until(EC.presence_of_element_located((By.XPATH, selector)))
                if button.is_displayed(): show_more_button = button; break
            except: continue
        if show_more_button:
            try:
                 initial_text = "";
                 try: initial_text = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]').text
                 except: pass
                 clickable_button = WebDriverWait(driver, wait_timeout).until(EC.element_to_be_clickable(show_more_button))
                 clickable_button.click(); logger.info("Кликнули 'Show more' (improved).")
                 try:
                    WebDriverWait(driver, click_wait_timeout).until(EC.any_of(EC.staleness_of(show_more_button), EC.text_to_be_present_in_element((By.CSS_SELECTOR, 'div[data-testid="tweetText"]'), initial_text + " ") if initial_text else EC.staleness_of(show_more_button)))
                    logger.info("Контент твита раскрыт (improved, подтверждено)."); expanded = True
                 except TimeoutException: logger.warning("Не удалось дождаться результата клика 'Show more' (improved)."); expanded = False
                 except StaleElementReferenceException: logger.info("Кнопка 'Show more' исчезла (improved)."); expanded = True
            except Exception as e: logger.warning(f"Ошибка при клике/ожидании 'Show more' (improved): {e}")
        return expanded
    except Exception as e:
        if "stale element reference" not in str(e).lower(): logger.error(f"Ошибка при раскрытии твита (improved): {e}")
        return False


def get_original_tweet_data_selenium(driver, original_tweet_url, extract_full_tweets=True):
    """
    Использует Selenium для перехода по URL оригинального твита и извлечения его данных.
    Возвращает словарь с данными оригинального твита или None.
    """
    # (Код без изменений, как в v4)
    logger.info(f"Получаем данные оригинального твита через Selenium: {original_tweet_url}")
    original_data = None; current_window = driver.current_window_handle; new_window_handle = None; opened_new_window = False; wait_timeout = 15
    try:
        initial_window_count = len(driver.window_handles)
        driver.execute_script(f"window.open('{original_tweet_url}', '_blank');"); opened_new_window = True
        WebDriverWait(driver, wait_timeout).until(EC.number_of_windows_to_be(initial_window_count + 1))
        all_windows = driver.window_handles
        if len(all_windows) > 1:
             new_window_handle = [window for window in all_windows if window != current_window][-1]
             driver.switch_to.window(new_window_handle); logger.debug("Переключились на новую вкладку для оригинала.")
        else: logger.error("Не удалось открыть новую вкладку для оригинального твита."); return None
        tweet_article_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        try:
            original_tweet_element = WebDriverWait(driver, wait_timeout).until(EC.presence_of_element_located(tweet_article_locator))
            logger.debug("Элемент оригинального твита найден.")
        except TimeoutException: logger.error(f"Не удалось загрузить оригинальный твит по URL: {original_tweet_url}"); raise
        original_text = ""; original_created_at = ""; original_stats = {"likes": 0, "retweets": 0, "replies": 0}; original_author_info = {"username": None}; is_truncated_flag = False
        try:
            text_locator = (By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
            text_element = WebDriverWait(original_tweet_element, 5).until(EC.presence_of_element_located(text_locator))
            original_text = text_element.text
        except TimeoutException: logger.warning("Текст оригинального твита не найден.")
        if extract_full_tweets and original_text and is_tweet_truncated(original_tweet_element):
             logger.info("Оригинальный твит обрезан, получаем полный текст...")
             full_original_text = get_full_tweet_text(driver, original_tweet_url)
             if full_original_text and len(full_original_text) > len(original_text): original_text = full_original_text; is_truncated_flag = True; logger.info("Полный текст оригинального твита получен.")
        try:
             time_locator = (By.TAG_NAME, 'time')
             time_element = WebDriverWait(original_tweet_element, 5).until(EC.presence_of_element_located(time_locator))
             original_created_at = time_element.get_attribute('datetime')
        except TimeoutException: logger.warning("Дата оригинального твита не найдена.")
        original_stats = extract_tweet_stats(original_tweet_element)
        original_author_info = get_author_info(original_tweet_element)
        original_author_name = original_author_info.get("username")
        original_tweet_id = original_tweet_url.split("/")[-1].split("?")[0] if original_tweet_url else None
        if original_tweet_id and original_tweet_id.isdigit():
            original_data = {
                "text": original_text, "created_at": original_created_at, "stats": original_stats,
                "original_author": original_author_name, "original_tweet_id": original_tweet_id,
                "original_tweet_url": original_tweet_url, # URL оригинала
                "url": original_tweet_url, # URL оригинала (для сохранения в колонку url)
                "tweet_id": original_tweet_id, # ID оригинала (для сохранения в колонку tweet_id)
                "is_retweet": False, # Это сам оригинал
                "is_truncated": is_truncated_flag
            }
            logger.info(f"Данные оригинального твита (@{original_author_name}) получены через Selenium.")
        else: logger.warning(f"Не удалось извлечь корректный ID из URL оригинала: {original_tweet_url}"); original_data = None
    except Exception as e:
        logger.error(f"Ошибка при получении данных оригинального твита ({original_tweet_url}) через Selenium: {e}")
        import traceback; logger.error(traceback.format_exc()); original_data = None
    finally:
        try:
            if opened_new_window and new_window_handle and new_window_handle in driver.window_handles: driver.close()
            if current_window and current_window in driver.window_handles: driver.switch_to.window(current_window)
            elif driver.window_handles: driver.switch_to.window(driver.window_handles[0])
        except Exception as close_err: logger.error(f"Ошибка при закрытии вкладки/переключении: {close_err}")
    return original_data


def get_tweets_with_selenium(username, driver, db_connection=None, max_tweets=10, use_cache=True,
                             cache_duration_hours=1, time_filter_hours=24, force_refresh=False,
                             extract_full_tweets=True,
                             dependencies=None, html_cache_dir="twitter_html_cache"):
    """
    Получает твиты пользователя с помощью Selenium.
    Для ретвитов извлекает данные оригинала и сохраняет их под ID и URL оригинала.
    Использует WebDriverWait. API отключен.
    """
    if dependencies is None: dependencies = {}

    save_user_to_db = dependencies.get('save_user_to_db')
    save_tweet_to_db = dependencies.get('save_tweet_to_db')
    filter_recent_tweets = dependencies.get('filter_recent_tweets')
    extract_retweet_info_enhanced = dependencies.get('extract_retweet_info_enhanced')
    is_tweet_truncated = dependencies.get('is_tweet_truncated')
    get_full_tweet_text = dependencies.get('get_full_tweet_text')

    logger.info(f"Начинаем получение твитов для @{username}...")
    cache_file = os.path.join(CACHE_DIR, f"{username}_tweets_selenium.json")
    result = {"username": username, "name": username, "tweets": []}
    wait_timeout = 15

    # --- Проверка кэша ---
    if use_cache and os.path.exists(cache_file) and not force_refresh:
        try:
            logger.debug(f"Проверка кэша для @{username}...")
            file_modified_time = os.path.getmtime(cache_file); current_time = time.time()
            if current_time - file_modified_time < cache_duration_hours * 3600:
                with open(cache_file, 'r', encoding='utf-8') as f: cached_data = json.load(f)
                logger.info(f"Используем кэшированные данные для @{username}")
                result["name"] = cached_data.get("name", username)
                recent_tweets_from_cache = filter_recent_tweets(cached_data.get('tweets', []), time_filter_hours)
                result["tweets"] = recent_tweets_from_cache[:max_tweets]
                if result["tweets"]: logger.info(f"Найдено {len(result['tweets'])} свежих твитов в кэше."); return result
                else: logger.info(f"В кэше нет свежих твитов для @{username}, запрашиваем новые.")
        except Exception as e: logger.error(f"Ошибка при чтении кэша для @{username}: {e}")
    elif force_refresh: logger.info(f"Принудительное обновление данных для @{username}")

    try:
        logger.info(f"Загружаем страницу профиля @{username}...")
        profile_url = f"https://twitter.com/{username}"; driver.get(profile_url)

        # --- Ожидание загрузки страницы ---
        tweet_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        try: WebDriverWait(driver, wait_timeout).until(EC.presence_of_element_located(tweet_locator)); logger.info("Страница профиля загружена.")
        except TimeoutException:
            logger.warning(f"Таймаут ({wait_timeout} сек) при ожидании твитов на странице @{username}.")
            if "This account doesn't exist" in driver.page_source or "Hmm...this page doesn't exist" in driver.page_source: logger.error(f"Аккаунт @{username} не существует."); return result
            elif "Something went wrong" in driver.page_source: logger.warning(f"Ошибка 'Something went wrong' на странице @{username}.")
            else: logger.warning("Твиты не загрузились, но страница не пуста. Попробуем продолжить.")

        # --- Проверка авторизации, сохранение HTML, извлечение имени, сохранение пользователя ---
        page_source = driver.page_source
        if "Log in" in page_source and "Sign up" in page_source and "Timeline: Verification" not in page_source: logger.warning("Признаки авторизации не обнаружены.")
        if html_cache_dir:
             html_file = os.path.join(html_cache_dir, f"{username}_selenium.html")
             try:
                 with open(html_file, "w", encoding="utf-8") as f: f.write(driver.page_source); logger.debug(f"HTML сохранен: {html_file}")
             except Exception as e: logger.error(f"Не удалось сохранить HTML: {e}")
        try:
            name_locator = (By.CSS_SELECTOR, 'h2[aria-level="2"][role="heading"] span span')
            name_element = WebDriverWait(driver, 5).until(EC.presence_of_element_located(name_locator))
            if name_element: result["name"] = name_element.text.strip()
            else: result["name"] = driver.title.split("(")[0].strip() if "(" in driver.title else username
            logger.info(f"Извлечено имя пользователя: {result['name']}")
        except Exception as e: logger.error(f"Ошибка при извлечении имени: {e}")
        user_id = None
        if db_connection and save_user_to_db:
            user_id = save_user_to_db(db_connection, username, result["name"])
            if user_id: logger.info(f"Пользователь @{username} сохранен/обновлен в БД с ID: {user_id}")
            else: logger.error(f"Ошибка при сохранении пользователя {username} в базу данных")

        # --- Скроллинг и обработка твитов ---
        processed_element_ids = set(); tweets_data_to_cache = []
        scroll_attempts = 0; max_scroll_attempts = 40; no_new_tweets_count = 0; max_no_new_tweets = 5
        scroll_step = 1000; current_scroll_position = 0; last_tweet_count = 0

        logger.info("Начинаем скроллинг и обработку твитов...")

        while scroll_attempts < max_scroll_attempts and no_new_tweets_count < max_no_new_tweets and len(tweets_data_to_cache) < max_tweets * 3:
            scroll_attempts += 1; logger.debug(f"Попытка скроллинга #{scroll_attempts}...")
            last_height = driver.execute_script("return document.documentElement.scrollHeight")
            current_scroll_position += scroll_step; driver.execute_script(f"window.scrollTo(0, {current_scroll_position});")
            try: # Ожидание после скролла
                WebDriverWait(driver, 5).until(lambda d: len(d.find_elements(*tweet_locator)) > last_tweet_count or d.execute_script("return document.documentElement.scrollHeight") > last_height)
                logger.debug("Обнаружено изменение контента после скролла.")
            except TimeoutException: logger.debug("Контент не изменился после скролла за 5 сек."); time.sleep(1)

            tweet_elements = find_all_tweets(driver); current_tweet_count = len(tweet_elements)
            if current_tweet_count == last_tweet_count: logger.debug("Количество твитов не изменилось.")
            last_tweet_count = current_tweet_count
            new_tweets_this_iteration = 0

            for tweet_element in tweet_elements:
                element_url = ""; element_id = ""; final_tweet_data = None; retweet_url_for_log = None
                try:
                    # --- Извлечение ID и URL элемента ---
                    time_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
                    found_link = False
                    for link in time_links:
                         href = link.get_attribute('href')
                         if href and '/status/' in href and link.find_elements(By.TAG_NAME, 'time'):
                              element_url = href.split("?")[0]
                              status_part = element_url.split("/status/")[-1]; element_id = status_part.split("/")[0]
                              if element_id.isdigit(): found_link = True; break
                    if not found_link and time_links:
                         href = time_links[0].get_attribute('href')
                         if href and '/status/' in href:
                              element_url = href.split("?")[0]; status_part = element_url.split("/status/")[-1]; element_id = status_part.split("/")[0]
                              if not element_id.isdigit(): element_id = None

                    if not element_id or element_id in processed_element_ids: continue
                    processed_element_ids.add(element_id); logger.debug(f"Обработка элемента ID: {element_id}")
                    retweet_url_for_log = element_url # Сохраняем URL ретвита для логов

                    # --- API вызовы отключены ---

                    retweet_info = extract_retweet_info_enhanced(tweet_element)
                    is_retweet = retweet_info["is_retweet"]; original_author = retweet_info["original_author"]
                    original_tweet_url = retweet_info["original_tweet_url"]
                    original_tweet_id = original_tweet_url.split("/")[-1].split("?")[0] if original_tweet_url and original_tweet_url.split("/")[-1].split("?")[0].isdigit() else None

                    # --- Обработка ретвита ---
                    if is_retweet and original_tweet_url and original_tweet_id:
                        logger.info(f"Ретвит {element_id}. Получаем оригинал: {original_tweet_url}")
                        original_data = get_original_tweet_data_selenium(driver, original_tweet_url, extract_full_tweets)
                        if original_data:
                             final_tweet_data = {
                                 "url": original_data.get("url"), # URL ОРИГИНАЛА
                                 "tweet_id": original_data.get("tweet_id"), # ID ОРИГИНАЛА
                                 "retweet_url_for_log": retweet_url_for_log, # Добавляем URL ретвита для логов
                                 "is_retweet": True,
                                 "original_author": original_data.get("original_author") or original_author,
                                 "original_tweet_id": original_data.get("original_tweet_id") or original_tweet_id,
                                 "original_tweet_url": original_data.get("original_tweet_url") or original_tweet_url,
                                 "text": original_data.get("text", ""),
                                 "created_at": original_data.get("created_at", ""),
                                 "stats": original_data.get("stats", {}),
                                 "is_truncated": original_data.get("is_truncated", False)
                             }
                             logger.info(f"Данные оригинала (@{final_tweet_data['original_author']}) получены для ретвита {element_id}")
                        else: logger.error(f"Не удалось получить данные оригинала {original_tweet_url}. Пропускаем ретвит."); continue

                    # --- Обработка обычного твита ---
                    else:
                        logger.debug(f"Обработка твита {element_id} через Selenium")
                        expand_tweet_content_improved(driver, tweet_element)

                        tweet_text = ""; created_at = ""; stats = {"likes": 0, "retweets": 0, "replies": 0}; is_truncated_flag = False
                        try:
                            text_locator = (By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                            text_element = WebDriverWait(tweet_element, 5).until(EC.presence_of_element_located(text_locator))
                            tweet_text = text_element.text
                        except TimeoutException: logger.warning(f"Текст твита {element_id} не найден.")

                        if extract_full_tweets and tweet_text and is_tweet_truncated(tweet_element):
                            logger.info(f"Твит {element_id} обрезан, получаем полную версию...")
                            full_text = get_full_tweet_text(driver, element_url)
                            if full_text and len(full_text) > len(tweet_text):
                                tweet_text = full_text; is_truncated_flag = True
                                logger.info(f"Полный текст твита {element_id} получен.")

                        try:
                            time_locator = (By.CSS_SELECTOR, 'a[href*="/status/"] time')
                            time_element = WebDriverWait(tweet_element, 5).until(EC.presence_of_element_located(time_locator))
                            created_at = time_element.get_attribute('datetime')
                        except TimeoutException: logger.warning(f"Не удалось найти время для твита {element_id}")

                        stats = extract_tweet_stats(tweet_element)

                        final_tweet_data = {
                            "url": element_url, # URL самого твита
                            "tweet_id": element_id, # ID самого твита
                            "is_retweet": False,
                            "original_author": None, "original_tweet_id": None, "original_tweet_url": None,
                            "text": tweet_text, "created_at": created_at, "stats": stats, "is_truncated": is_truncated_flag
                        }
                        logger.info(f"Твит {element_id} обработан через Selenium.")

                    # --- Сохранение результата ---
                    if final_tweet_data:
                        tweets_data_to_cache.append(final_tweet_data)
                        new_tweets_this_iteration += 1
                        if db_connection and user_id and save_tweet_to_db:
                            save_tweet_to_db(db_connection, user_id, final_tweet_data)

                except StaleElementReferenceException:
                    logger.warning(f"Элемент твита устарел, пропускаем: {element_id}")
                    if element_id in processed_element_ids: processed_element_ids.remove(element_id)
                except Exception as e:
                    print(f"Ошибка обработки элемента ID={element_id}: {e}")
                    logger.error(f"Ошибка обработки элемента ID={element_id}: {e}")
                    import traceback; logger.error(traceback.format_exc())

            # --- Обновление счетчика и проверка конца страницы ---
            if new_tweets_this_iteration == 0: no_new_tweets_count += 1; logger.info(f"Не найдено новых твитов. Счетчик: {no_new_tweets_count}/{max_no_new_tweets}")
            else: no_new_tweets_count = 0; logger.info(f"Добавлено {new_tweets_this_iteration} новых твитов/ретвитов")
            try:
                viewport_height = driver.execute_script("return window.innerHeight"); document_height = driver.execute_script("return document.documentElement.scrollHeight")
                if current_scroll_position >= document_height - viewport_height - 200:
                    logger.info("Достигнут конец страницы."); time.sleep(3)
                    new_document_height = driver.execute_script("return document.documentElement.scrollHeight")
                    if new_document_height <= document_height + 10: logger.info("Больше твитов не загружается."); break
            except Exception as e: logger.warning(f"Ошибка при проверке конца страницы: {e}")

        logger.info(f"Завершен скроллинг после {scroll_attempts} попыток")
        logger.info(f"Всего уникальных элементов обработано: {len(processed_element_ids)}")
        logger.info(f"Всего твитов/ретвитов собрано для кэша: {len(tweets_data_to_cache)}")

        # --- Фильтрация и сохранение в кэш ---
        logger.info(f"Фильтрация твитов за последние {time_filter_hours} часов...")
        recent_tweets = filter_recent_tweets(tweets_data_to_cache, time_filter_hours)
        logger.info(f"Из них свежих твитов/ретвитов: {len(recent_tweets)}")

        cached_result = {"username": username, "name": result["name"], "tweets": tweets_data_to_cache}
        if use_cache:
            try:
                logger.info(f"Сохранение {len(tweets_data_to_cache)} твитов в кэш: {cache_file}")
                with open(cache_file, 'w', encoding='utf-8') as f: json.dump(cached_result, f, ensure_ascii=False, indent=2)
                logger.info(f"Кэш успешно сохранен")
            except Exception as e: logger.error(f"Ошибка при сохранении кэша: {e}")

        result["tweets"] = recent_tweets[:max_tweets]
        logger.info(f"Возвращаем {len(result['tweets'])} свежих твитов/ретвитов для @{username}")
        return result

    except Exception as e:
        print(f"Критическая ошибка при получении твитов для @{username} через Selenium: {e}")
        logger.critical(f"Критическая ошибка при получении твитов для @{username} через Selenium: {e}")
        import traceback; logger.error(traceback.format_exc())
        return result
