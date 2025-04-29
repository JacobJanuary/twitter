#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для извлечения твитов из Twitter.
РЕФАКТОРИНГ: Убрана индивидуальная вставка в БД, функция возвращает все собранные твиты.
РЕФАКТОРИНГ: Улучшена обработка StaleElementReferenceException.
ИСПРАВЛЕНО: Исправлены ошибки синтаксиса/отступов.
"""

import os
import json
import time
import logging
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, WebDriverException
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
def expand_tweet_content(driver, tweet_element):
    """Расширяет содержимое твита"""
    # (Код без изменений)
    expanded = False; wait_timeout = 3; click_wait_timeout = 5
    try: # Outer try block
        show_more_selectors_xpath = [ './/div[@role="button" and (contains(., "Show more") or contains(., "Показать ещё"))]', './/span[contains(., "Show more") or contains(., "Показать ещё")]' ]
        show_more_button = None
        for selector in show_more_selectors_xpath:
            try: # Inner try 1
                buttons = tweet_element.find_elements(By.XPATH, selector)
                for button in buttons:
                     if button.is_displayed(): show_more_button = button; logger.debug(f"Найдена видимая кнопка 'Show more' через: {selector}"); break
                if show_more_button: break
            except (NoSuchElementException, StaleElementReferenceException): continue
            except Exception as find_err: logger.warning(f"Ошибка поиска кнопки Show more ({selector}): {find_err}")
        if show_more_button:
            try: # Inner try 2 - Попытка клика и ожидания
                initial_text = "";
                try: initial_text = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]').text
                except (NoSuchElementException, StaleElementReferenceException): logger.debug("Не удалось получить начальный текст перед кликом 'Show more'.")
                except Exception as text_err: logger.warning(f"Ошибка получения начального текста: {text_err}")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", show_more_button); time.sleep(0.3)
                clickable_button = WebDriverWait(driver, wait_timeout).until(EC.element_to_be_clickable(show_more_button))
                clickable_button.click(); logger.info("Кликнули 'Show more'.")
                try: # Inner try 4 - Ожидание обновления
                    WebDriverWait(driver, click_wait_timeout).until(EC.any_of(EC.staleness_of(show_more_button), lambda d: d.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]').text != initial_text))
                    logger.info("Контент твита раскрыт (подтверждено ожиданием)."); expanded = True
                except TimeoutException: logger.warning("Не удалось дождаться результата клика 'Show more' (таймаут)."); expanded = False
                except StaleElementReferenceException: logger.info("Кнопка 'Show more' исчезла после клика (ожидаемо)."); expanded = True
                except Exception as wait_err: logger.warning(f"Ошибка ожидания после клика Show more: {wait_err}"); expanded = False
            except Exception as e: logger.warning(f"Ошибка при попытке раскрытия (клик/ожидание): {e}"); expanded = False
        if not expanded:
            try: # Inner try 5 - Проверка многоточия
                tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                if tweet_text_element.text.strip().endswith(('…', '...')):
                    logger.debug("Твит все еще содержит многоточие после попытки раскрытия.")
            except (NoSuchElementException, StaleElementReferenceException): logger.debug("Не удалось проверить текст на многоточие.")
            except Exception as check_err: logger.warning(f"Ошибка при проверке текста на многоточие: {check_err}")
        return expanded
    except StaleElementReferenceException: logger.warning("Элемент твита устарел во время expand_tweet_content."); return False
    except Exception as e:
        if "stale element reference" not in str(e).lower(): logger.error(f"Неожиданная ошибка при раскрытии твита: {e}")
        return False


def find_all_tweets(driver):
    """Расширенный поиск твитов"""
    # (Код без изменений)
    tweets = []; processed_elements_ids = set(); wait_timeout = 5; tweet_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
    try:
        standard_tweets = WebDriverWait(driver, wait_timeout).until(EC.presence_of_all_elements_located(tweet_locator))
        if standard_tweets:
            for tweet in standard_tweets:
                try:
                     if tweet.id not in processed_elements_ids: tweets.append(tweet); processed_elements_ids.add(tweet.id)
                except StaleElementReferenceException: logger.debug("Найденный твит устарел (стандартный поиск)."); continue
            logger.debug(f"Найдено {len(tweets)} твитов по стандартному селектору (WebDriverWait)")
    except TimeoutException: logger.debug(f"Твиты по стандартному селектору не найдены за {wait_timeout} сек.")
    except Exception as e: logger.warning(f"Ошибка поиска по стандартному селектору: {e}")
    try:
        timeline_items = driver.find_elements(By.CSS_SELECTOR, '[data-testid="cellInnerDiv"]'); new_tweets_count = 0
        for item in timeline_items:
            try:
                if item.id not in processed_elements_ids and item.find_elements(By.TAG_NAME, 'time'):
                    if item.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]'):
                         inner_article = item.find_element(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
                         if inner_article.id not in processed_elements_ids: tweets.append(inner_article); processed_elements_ids.add(inner_article.id); new_tweets_count += 1
            except StaleElementReferenceException: logger.debug("Найденный элемент timeline устарел (расширенный поиск)."); continue
            except NoSuchElementException: continue
        if new_tweets_count > 0: logger.debug(f"Найдено дополнительно {new_tweets_count} твитов по расширенному селектору")
    except Exception as e: logger.warning(f"Ошибка поиска по расширенному селектору: {e}")
    logger.debug(f"Всего найдено уникальных элементов твитов на странице: {len(tweets)}")
    return tweets


def expand_tweet_content_improved(driver, tweet_element):
    """Улучшенная функция раскрытия твита (использует expand_tweet_content)"""
    return expand_tweet_content(driver, tweet_element)


def get_original_tweet_data_selenium(driver, original_tweet_url, extract_full_tweets=True):
    """Получает данные оригинального твита В ТОЙ ЖЕ ВКЛАДКЕ."""
    # (Код без изменений)
    logger.info(f"Получаем данные оригинального твита (в той же вкладке): {original_tweet_url}")
    original_data = None; current_url = driver.current_url; wait_timeout = 15
    try:
        logger.debug(f"Переход на {original_tweet_url}"); driver.get(original_tweet_url)
        tweet_article_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        try:
            WebDriverWait(driver, wait_timeout).until(EC.all_of(EC.presence_of_element_located(tweet_article_locator), EC.url_contains(original_tweet_url.split('/')[-1].split('?')[0])))
            logger.debug("Элемент оригинального твита найден."); time.sleep(1); original_tweet_element = driver.find_element(*tweet_article_locator)
        except TimeoutException: logger.error(f"Таймаут при загрузке оригинала: {original_tweet_url}"); raise
        except Exception as e: logger.error(f"Ошибка ожидания оригинала {original_tweet_url}: {e}"); raise
        original_text = ""; original_created_at = ""; original_stats = {"likes": 0, "retweets": 0, "replies": 0}; original_author_info = {"username": None}; is_truncated_flag = False
        try: text_locator = (By.CSS_SELECTOR, 'div[data-testid="tweetText"]'); text_element = WebDriverWait(original_tweet_element, 5).until(EC.presence_of_element_located(text_locator)); original_text = text_element.text
        except (TimeoutException, NoSuchElementException, StaleElementReferenceException): logger.warning("Текст оригинала не найден.")
        except Exception as e: logger.warning(f"Ошибка извлечения текста оригинала: {e}")
        if extract_full_tweets and original_text and is_tweet_truncated(original_tweet_element):
             logger.info("Оригинал обрезан, получаем полный текст..."); full_original_text = get_full_tweet_text(driver, original_tweet_url)
             if full_original_text and len(full_original_text) > len(original_text): original_text = full_original_text; is_truncated_flag = True; logger.info("Полный текст оригинала получен.")
             else: logger.warning("Не удалось получить полный текст оригинала."); is_truncated_flag = True
        try: time_locator = (By.CSS_SELECTOR, 'a[href*="/status/"] time'); time_element = WebDriverWait(original_tweet_element, 5).until(EC.presence_of_element_located(time_locator)); original_created_at = time_element.get_attribute('datetime')
        except (TimeoutException, NoSuchElementException, StaleElementReferenceException): logger.warning("Дата оригинала не найдена.")
        except Exception as e: logger.warning(f"Ошибка извлечения даты оригинала: {e}")
        original_stats = extract_tweet_stats(original_tweet_element); original_author_info = get_author_info(original_tweet_element); original_author_name = original_author_info.get("username")
        original_tweet_id = original_tweet_url.split("/")[-1].split("?")[0] if original_tweet_url else None
        if original_tweet_id and original_tweet_id.isdigit():
            original_data = {"text": original_text, "created_at": original_created_at, "stats": original_stats, "original_author": original_author_name, "original_tweet_id": original_tweet_id, "original_tweet_url": original_tweet_url, "url": original_tweet_url, "tweet_id": original_tweet_id, "is_retweet": False, "is_truncated": is_truncated_flag}
            logger.info(f"Данные оригинала (@{original_author_name}) получены.")
        else: logger.warning(f"Некорректный ID из URL оригинала: {original_tweet_url}"); original_data = None
    except WebDriverException as e: logger.error(f"Ошибка WebDriver при получении оригинала ({original_tweet_url}): {e}"); original_data = None
    except Exception as e: logger.error(f"Общая ошибка при получении оригинала ({original_tweet_url}): {e}"); import traceback; logger.error(traceback.format_exc()); original_data = None
    finally:
        try:
            if driver.current_url != current_url: logger.info(f"Возвращаемся на: {current_url}"); driver.get(current_url); WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]'))); logger.debug("Успешно вернулись.")
            else: logger.debug("Уже на исходной странице.")
        except Exception as back_err:
            logger.error(f"Критическая ошибка возврата на {current_url}: {back_err}")
            try: logger.warning(f"Повторная попытка загрузить {current_url}"); driver.get(current_url); WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]')))
            except Exception as retry_err: logger.critical(f"Не удалось вернуться на {current_url}: {retry_err}.")
    return original_data


def get_tweets_with_selenium(username, driver, db_connection=None, max_tweets=10, use_cache=True,
                             cache_duration_hours=1, time_filter_hours=24, force_refresh=False,
                             extract_full_tweets=True,
                             dependencies=None, html_cache_dir="twitter_html_cache"):
    """
    Получает твиты пользователя. Собирает все данные в список и возвращает его.
    НЕ СОХРАНЯЕТ В БД. Улучшена обработка Stale Elements.
    """
    if dependencies is None: dependencies = {}
    save_user_to_db = dependencies.get('save_user_to_db'); filter_recent_tweets = dependencies.get('filter_recent_tweets')
    extract_retweet_info_enhanced = dependencies.get('extract_retweet_info_enhanced'); is_tweet_truncated = dependencies.get('is_tweet_truncated')
    get_full_tweet_text = dependencies.get('get_full_tweet_text'); extract_tweet_stats = dependencies.get('extract_tweet_stats')
    get_author_info = dependencies.get('get_author_info')

    logger.info(f"Начинаем сбор твитов для @{username} (без немедленной записи в БД)...")
    cache_file = os.path.join(CACHE_DIR, f"{username}_tweets_selenium.json"); user_info = {"username": username, "name": username}
    all_collected_tweets = []; wait_timeout = 15; user_id = None

    if use_cache and os.path.exists(cache_file) and not force_refresh:
        try:
            logger.debug(f"Проверка кэша @{username}..."); file_modified_time = os.path.getmtime(cache_file); current_time = time.time()
            if current_time - file_modified_time < cache_duration_hours * 3600:
                with open(cache_file, 'r', encoding='utf-8') as f: cached_data = json.load(f)
                logger.info(f"Используем кэш @{username} ({len(cached_data.get('tweets', []))} записей)")
                user_info["name"] = cached_data.get("name", username); user_id_from_cache = cached_data.get("user_id")
                return {"user_info": user_info, "user_id": user_id_from_cache, "tweets": cached_data.get('tweets', [])}
            else: logger.info(f"Кэш @{username} устарел.")
        except Exception as e: logger.error(f"Ошибка чтения кэша @{username}: {e}.")
    elif force_refresh: logger.info(f"Принудительное обновление @{username}.")
    else: logger.info(f"Кэш не используется/не найден для @{username}.")

    try:
        logger.info(f"Загружаем страницу @{username}..."); profile_url = f"https://twitter.com/{username}"; driver.get(profile_url)
        tweet_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        try: WebDriverWait(driver, wait_timeout).until(EC.presence_of_element_located(tweet_locator)); logger.info("Страница загружена.")
        except TimeoutException:
            logger.warning(f"Таймаут ожидания твитов @{username}."); page_content = driver.page_source
            if "This account doesn't exist" in page_content or "Hmm...this page doesn't exist" in page_content: logger.error(f"Аккаунт @{username} не существует."); return {"user_info": user_info, "user_id": None, "tweets": []}
            elif "Something went wrong" in page_content: logger.warning(f"Ошибка 'Something went wrong' @{username}.")
            else: logger.warning("Твиты не загрузились @{username}.")
        except Exception as e: logger.error(f"Ошибка загрузки страницы @{username}: {e}"); return {"user_info": user_info, "user_id": None, "tweets": []}

        if html_cache_dir:
             html_file = os.path.join(html_cache_dir, f"{username}_selenium.html")
             try:
                 with open(html_file, "w", encoding="utf-8") as f: f.write(driver.page_source); logger.debug(f"HTML сохранен: {html_file}")
             except Exception as e: logger.error(f"Не удалось сохранить HTML: {e}")

        try: # Outer try for name extraction
            name_locator_xpath = '//h2[@aria-level="2"]//span[not(contains(text(),"@"))]/span'
            try: # Inner try for WebDriverWait
                 name_element = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, name_locator_xpath)))
                 if name_element and name_element.text.strip():
                      user_info["name"] = name_element.text.strip()
                 else: # Fallback 1 (if element found but no text)
                      user_info["name"] = driver.title.split("(")[0].strip() if "(" in driver.title else username
            except TimeoutException: # Fallback 2 (if element not found)
                 logger.warning("Не удалось найти имя пользователя по основному селектору, используем title.")
                 user_info["name"] = driver.title.split("(")[0].strip() if "(" in driver.title else username
            logger.info(f"Извлечено имя пользователя: {user_info['name']}")
        except Exception as e: # Belongs to Outer try
             logger.warning(f"Ошибка при извлечении имени: {e}")
             user_info["name"] = username
             logger.info(f"Установлено имя пользователя по умолчанию: {user_info['name']}")

        if db_connection and save_user_to_db:
            user_id = save_user_to_db(db_connection, username, user_info["name"])
            if user_id: logger.info(f"Пользователь @{username} сохранен/обновлен (ID: {user_id})")
            else: logger.error(f"Ошибка сохранения пользователя {username}")
        elif not db_connection: logger.warning("Работа без БД, user_id не будет определен.")

        processed_element_ids = set(); processed_tweet_ids = set()
        scroll_attempts = 0; max_scroll_attempts = 40; no_new_tweets_count = 0; max_no_new_tweets = 5
        scroll_step = 1000; current_scroll_position = 0; last_tweet_count = 0
        max_tweets_to_collect = 100

        logger.info("Начинаем скроллинг и сбор...")
        while scroll_attempts < max_scroll_attempts and no_new_tweets_count < max_no_new_tweets and len(all_collected_tweets) < max_tweets_to_collect:
            scroll_attempts += 1; logger.debug(f"Скроллинг #{scroll_attempts}...")
            last_height = driver.execute_script("return document.documentElement.scrollHeight")
            current_scroll_position += scroll_step; driver.execute_script(f"window.scrollTo(0, {current_scroll_position});")
            try:
                WebDriverWait(driver, 7).until(lambda d: len(find_all_tweets(d)) > last_tweet_count or d.execute_script("return document.documentElement.scrollHeight") > last_height + 100)
                logger.debug("Обнаружено изменение контента.")
            except TimeoutException: logger.debug("Контент не изменился."); time.sleep(1)
            except Exception as scroll_wait_err: logger.warning(f"Ошибка ожидания после скролла: {scroll_wait_err}"); time.sleep(1)

            tweet_elements = find_all_tweets(driver); current_tweet_count_on_page = len(tweet_elements)
            if current_tweet_count_on_page == last_tweet_count: logger.debug("Кол-во твитов не изменилось.")
            else: logger.debug(f"Найдено твитов: {current_tweet_count_on_page} (было {last_tweet_count})")
            last_tweet_count = current_tweet_count_on_page
            new_tweets_this_iteration = 0

            for tweet_element in tweet_elements:
                element_id_selenium = tweet_element.id
                if element_id_selenium in processed_element_ids: continue

                element_url = ""; tweet_numeric_id = None; final_tweet_data = None; retweet_url_for_log = None
                tweet_text = ""; created_at = ""; stats = {"likes": 0, "retweets": 0, "replies": 0}; author_info = {}; is_truncated_flag = False; is_truncated_initially = False;
                is_retweet = False; original_author = None; original_tweet_url = None; original_tweet_id = None;

                try:
                    time_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
                    found_link = False
                    for link in time_links:
                         try: href = link.get_attribute('href')
                         except StaleElementReferenceException: continue
                         if href and '/status/' in href and link.find_elements(By.TAG_NAME, 'time'):
                              element_url = href.split("?")[0]; status_part = element_url.split("/status/")[-1]; potential_id = status_part.split("/")[0]
                              if potential_id.isdigit(): tweet_numeric_id = potential_id; found_link = True; break
                    if not found_link and time_links:
                         try: href = time_links[0].get_attribute('href')
                         except StaleElementReferenceException: href = None
                         if href and '/status/' in href: element_url = href.split("?")[0]; status_part = element_url.split("/status/")[-1]; potential_id = status_part.split("/")[0]
                         if potential_id.isdigit(): tweet_numeric_id = potential_id
                         else: tweet_numeric_id = None
                    if not tweet_numeric_id: logger.warning(f"Не найден числовой ID твита для {element_id_selenium}."); processed_element_ids.add(element_id_selenium); continue
                    if tweet_numeric_id in processed_tweet_ids: processed_element_ids.add(element_id_selenium); continue
                    retweet_url_for_log = element_url

                    try: time_locator = (By.CSS_SELECTOR, 'a[href*="/status/"] time'); time_element = WebDriverWait(tweet_element, 2).until(EC.presence_of_element_located(time_locator)); created_at = time_element.get_attribute('datetime')
                    except (TimeoutException, NoSuchElementException, StaleElementReferenceException): logger.warning(f"Не найдено время для {tweet_numeric_id}")
                    try: text_locator = (By.CSS_SELECTOR, 'div[data-testid="tweetText"]'); text_element = WebDriverWait(tweet_element, 2).until(EC.presence_of_element_located(text_locator)); tweet_text = text_element.text
                    except (TimeoutException, NoSuchElementException, StaleElementReferenceException): logger.warning(f"Не найден текст для {tweet_numeric_id}")
                    stats = extract_tweet_stats(tweet_element)
                    author_info = get_author_info(tweet_element)
                    is_truncated_initially = is_tweet_truncated(tweet_element)
                    retweet_info = extract_retweet_info_enhanced(tweet_element)
                    is_retweet = retweet_info["is_retweet"]; original_author = retweet_info["original_author"]
                    original_tweet_url = retweet_info["original_tweet_url"]
                    original_tweet_id = original_tweet_url.split("/")[-1].split("?")[0] if original_tweet_url and original_tweet_url.split("/")[-1].split("?")[0].isdigit() else None
                    logger.debug(f"Предв. данные {tweet_numeric_id}: Retweet={is_retweet}, Truncated={is_truncated_initially}, Author='{author_info.get('username')}'")

                except StaleElementReferenceException: logger.warning(f"Элемент {element_id_selenium} устарел при первичном сборе."); continue
                except Exception as initial_extract_err: logger.error(f"Ошибка первичного сбора {element_id_selenium}: {initial_extract_err}"); continue

                try: # Отдельный try для основной логики и навигации
                    if is_retweet and original_tweet_url and original_tweet_id:
                        id_to_process = original_tweet_id
                        if id_to_process in processed_tweet_ids: logger.debug(f"Оригинал {id_to_process} уже обработан."); processed_element_ids.add(element_id_selenium); continue
                        logger.info(f"Ретвит {tweet_numeric_id}. Получаем оригинал: {original_tweet_url}")
                        original_data = get_original_tweet_data_selenium(driver, original_tweet_url, extract_full_tweets)
                        if original_data:
                             final_tweet_data = {
                                 "url": original_data.get("url"), "tweet_id": id_to_process, "retweet_url_for_log": retweet_url_for_log, "is_retweet": True,
                                 "original_author": original_data.get("original_author") or original_author, "original_tweet_id": original_data.get("original_tweet_id") or original_tweet_id,
                                 "original_tweet_url": original_data.get("original_tweet_url") or original_tweet_url, "text": original_data.get("text", ""),
                                 "created_at": original_data.get("created_at", ""), "stats": original_data.get("stats", {}), "is_truncated": original_data.get("is_truncated", False),
                                 "retweeting_user_id": user_id }
                             logger.info(f"Данные оригинала (@{final_tweet_data['original_author']}) получены для ретвита {tweet_numeric_id}")
                        else: logger.error(f"Не удалось получить данные оригинала {original_tweet_url}."); processed_element_ids.add(element_id_selenium); continue
                    else:
                        id_to_process = tweet_numeric_id
                        if id_to_process in processed_tweet_ids: logger.debug(f"Твит {id_to_process} уже обработан."); processed_element_ids.add(element_id_selenium); continue
                        logger.debug(f"Обработка твита {id_to_process}")
                        expand_tweet_content(driver, tweet_element)
                        is_truncated_flag = is_truncated_initially # Начинаем с начального состояния
                        if extract_full_tweets and is_truncated_initially:
                            logger.info(f"Твит {id_to_process} был обрезан, получаем полную версию...")
                            full_text = get_full_tweet_text(driver, element_url)
                            if full_text and len(full_text) > len(tweet_text):
                                tweet_text = full_text; is_truncated_flag = False # Успешно раскрыли
                                logger.info(f"Полный текст твита {id_to_process} получен.")
                            else: logger.warning(f"Не удалось получить полный текст твита {id_to_process}."); is_truncated_flag = True # Остался обрезанным
                        final_tweet_data = {
                            "url": element_url, "tweet_id": id_to_process, "is_retweet": False, "original_author": None, "original_tweet_id": None, "original_tweet_url": None,
                            "text": tweet_text, "created_at": created_at, "stats": stats, "is_truncated": is_truncated_flag,
                            "author_user_id": user_id if author_info.get("username") == username else None, "author_username": author_info.get("username") }
                        logger.info(f"Твит {id_to_process} от @{author_info.get('username')} обработан.")

                    if final_tweet_data:
                        processed_tweet_ids.add(final_tweet_data['tweet_id'])
                        all_collected_tweets.append(final_tweet_data)
                        new_tweets_this_iteration += 1
                    processed_element_ids.add(element_id_selenium)

                except StaleElementReferenceException: logger.warning(f"Элемент {element_id_selenium} устарел во время основной обработки."); continue
                except Exception as process_err: logger.error(f"Ошибка основной обработки {element_id_selenium}: {process_err}"); continue
            # --- Конец for tweet_element ---

            if new_tweets_this_iteration == 0: no_new_tweets_count += 1; logger.info(f"Нет новых твитов. Счетчик 'нет новых': {no_new_tweets_count}/{max_no_new_tweets}")
            else: no_new_tweets_count = 0; logger.info(f"Добавлено {new_tweets_this_iteration} новых твитов/ретвитов")

            # --- ИСПРАВЛЕННЫЙ БЛОК ПРОВЕРКИ КОНЦА СТРАНИЦЫ ---
            try: # Outer try for end-of-page check
                viewport_height = driver.execute_script("return window.innerHeight"); document_height = driver.execute_script("return document.documentElement.scrollHeight"); current_scroll = driver.execute_script("return window.pageYOffset")
                if current_scroll + viewport_height >= document_height - 300:
                    logger.info("Достигнут конец видимой страницы.")
                    try: # Inner try for loading indicator
                         loading_indicator = driver.find_element(By.CSS_SELECTOR, '[role="progressbar"]')
                         # --- ИСПРАВЛЕНИЕ: Разделяем команды ---
                         if loading_indicator.is_displayed():
                              logger.info("Индикатор загрузки виден...")
                              time.sleep(3)
                              continue # Продолжаем цикл while, чтобы дать время загрузиться
                         # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
                    except NoSuchElementException: # Если индикатора нет
                         logger.debug("Индикатор загрузки не найден.")
                         if no_new_tweets_count >= max_no_new_tweets:
                              logger.info("Достигнут конец и новые твиты не появляются.")
                              break # Выходим из цикла while
                    # Конец Inner try...except
            except Exception as e: # Belongs to Outer try
                 logger.warning(f"Ошибка проверки конца страницы: {e}")
            # Конец Outer try
            # --- КОНЕЦ ИСПРАВЛЕННОГО БЛОКА ---

        # --- Конец цикла while ---

        logger.info(f"Завершен скроллинг ({scroll_attempts} попыток)")
        logger.info(f"Уникальных элементов Selenium обработано: {len(processed_element_ids)}")
        logger.info(f"Уникальных твитов/ретвитов собрано: {len(all_collected_tweets)}")

        cached_result_data = {"username": username, "name": user_info["name"], "user_id": user_id, "tweets": all_collected_tweets}
        if use_cache or force_refresh:
            try:
                logger.info(f"Сохранение {len(all_collected_tweets)} твитов в кэш: {cache_file}");
                with open(cache_file, 'w', encoding='utf-8') as f: json.dump(cached_result_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Кэш сохранен")
            except Exception as e: logger.error(f"Ошибка сохранения кэша: {e}")

        logger.info(f"Возвращаем {len(all_collected_tweets)} собранных твитов для @{username}.")
        final_result = {"user_info": user_info, "user_id": user_id, "tweets": all_collected_tweets}
        return final_result

    except Exception as e:
        print(f"Критическая ошибка при сборе твитов @{username}: {e}")
        logger.critical(f"Критическая ошибка при сборе твитов @{username}: {e}")
        import traceback; logger.error(traceback.format_exc())
        return {"user_info": user_info, "user_id": user_id, "tweets": []}

