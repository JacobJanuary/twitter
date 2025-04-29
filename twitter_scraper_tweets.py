#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для извлечения твитов из Twitter.
Обрабатывает ретвиты, сохраняя данные оригинального твита.
API вызовы отключены.
"""

import os
import json
import time
import logging
import re
# BeautifulSoup больше не нужен
# from bs4 import BeautifulSoup
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
    # extract_full_tweet_text_from_html # get_full_tweet_text теперь основная
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
# (Код этих функций опущен для краткости, он идентичен v3)
def expand_tweet_content(driver, tweet_element):
    """Расширяет содержимое твита (код из v3)"""
    expanded = False
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
                if selector.startswith('.'): buttons = tweet_element.find_elements(By.XPATH, selector)
                else: buttons = tweet_element.find_elements(By.CSS_SELECTOR, selector)
                if buttons: show_more_buttons.extend(buttons)
            except Exception as e:
                 if "stale element reference" not in str(e).lower(): logger.warning(f"Ошибка поиска кнопки раскрытия: {e}")
                 continue
        show_more_buttons = list(dict.fromkeys(show_more_buttons))
        if show_more_buttons:
            for button in show_more_buttons:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(0.5)
                    try: button.click()
                    except: driver.execute_script("arguments[0].click();", button)
                    time.sleep(2)
                    logger.debug("Контент твита раскрыт")
                    expanded = True; break
                except Exception as e: logger.warning(f"Ошибка при попытке раскрытия: {e}")
        if not expanded:
            try:
                tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                tweet_text = tweet_text_element.text.strip()
                if tweet_text.endswith('…') or tweet_text.endswith('...'): return False
            except: pass
        return expanded
    except Exception as e:
        if "stale element reference" not in str(e).lower(): logger.error(f"Ошибка при раскрытии твита: {e}")
        return False

def find_all_tweets(driver):
    """Расширенный поиск твитов (код из v3)"""
    tweets = []
    processed_elements = set()
    try:
        standard_tweets = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        if standard_tweets:
            for tweet in standard_tweets:
                if tweet.id not in processed_elements: tweets.append(tweet); processed_elements.add(tweet.id)
    except Exception as e: logger.warning(f"Ошибка поиска по стандартному селектору: {e}")
    if len(tweets) < 5:
        try:
            timeline_items = driver.find_elements(By.CSS_SELECTOR, '[data-testid="cellInnerDiv"]')
            for item in timeline_items:
                if item.id not in processed_elements and item.find_elements(By.TAG_NAME, 'time'):
                    if item.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]'):
                         tweets.append(item); processed_elements.add(item.id)
        except Exception as e: logger.warning(f"Ошибка поиска по расширенному селектору: {e}")
    return tweets

def expand_tweet_content_improved(driver, tweet_element):
    """Улучшенная функция раскрытия твита (код из v3)"""
    expanded = False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet_element)
        time.sleep(1)
        selectors = [
            './/div[@role="button" and (contains(text(), "Show more") or contains(text(), "Показать ещё"))]',
            './/span[contains(text(), "Show more") or contains(text(), "Показать ещё")]',
            './/div[contains(@class, "r-1sg46qm")]'
        ]
        for selector in selectors:
            try:
                buttons = tweet_element.find_elements(By.XPATH, selector)
                if buttons:
                    for button in buttons:
                        try:
                            driver.execute_script("arguments[0].click();", button); time.sleep(2)
                            expanded = True; logger.debug("Твит раскрыт успешно (improved)"); break
                        except Exception as e: logger.warning(f"Ошибка при клике на кнопку раскрытия (improved): {e}")
                    if expanded: break
            except Exception as e:
                 if "stale element reference" not in str(e).lower(): logger.warning(f"Ошибка поиска кнопки раскрытия (improved): {e}")
        return expanded
    except Exception as e:
        if "stale element reference" not in str(e).lower(): logger.error(f"Ошибка при раскрытии твита (improved): {e}")
        return False


def get_original_tweet_data_selenium(driver, original_tweet_url, extract_full_tweets=True):
    """
    Использует Selenium для перехода по URL оригинального твита и извлечения его данных.
    Возвращает словарь с данными оригинального твита или None.
    """
    # (Код без изменений, как в v3)
    logger.info(f"Получаем данные оригинального твита через Selenium: {original_tweet_url}")
    original_data = None
    current_window = driver.current_window_handle
    new_window_handle = None
    opened_new_window = False

    try:
        driver.execute_script(f"window.open('{original_tweet_url}', '_blank');")
        opened_new_window = True
        time.sleep(1)
        all_windows = driver.window_handles
        if len(all_windows) > 1:
             new_window_handle = [window for window in all_windows if window != current_window][-1]
             driver.switch_to.window(new_window_handle)
             time.sleep(3)
        else:
             logger.error("Не удалось открыть новую вкладку для оригинального твита.")
             return None

        try:
            original_tweet_element = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]'))
            )
            logger.debug("Элемент оригинального твита найден.")
        except TimeoutException:
            logger.error(f"Не удалось загрузить оригинальный твит по URL: {original_tweet_url}")
            if opened_new_window: driver.close()
            driver.switch_to.window(current_window)
            return None

        original_text = ""
        original_created_at = ""
        original_stats = {"likes": 0, "retweets": 0, "replies": 0}
        original_author_info = {"username": None}
        is_truncated_flag = False

        try:
            text_element = original_tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
            original_text = text_element.text
        except NoSuchElementException: logger.warning("Текст оригинального твита не найден.")

        if extract_full_tweets and original_text and is_tweet_truncated(original_tweet_element):
             logger.info("Оригинальный твит обрезан, получаем полный текст...")
             # Важно: get_full_tweet_text откроет ЕЩЕ одну вкладку.
             # Передаем текущий URL оригинала.
             full_original_text = get_full_tweet_text(driver, original_tweet_url)
             if full_original_text and len(full_original_text) > len(original_text):
                  original_text = full_original_text
                  is_truncated_flag = True # Отмечаем, что текст был получен полностью
                  logger.info("Полный текст оригинального твита получен.")

        try:
            time_element = original_tweet_element.find_element(By.TAG_NAME, 'time')
            original_created_at = time_element.get_attribute('datetime')
        except NoSuchElementException: logger.warning("Дата оригинального твита не найдена.")

        original_stats = extract_tweet_stats(original_tweet_element)
        original_author_info = get_author_info(original_tweet_element)
        original_author_name = original_author_info.get("username")
        original_tweet_id = original_tweet_url.split("/")[-1].split("?")[0]

        original_data = {
            "text": original_text,
            "created_at": original_created_at,
            "stats": original_stats,
            "original_author": original_author_name,
            "original_tweet_id": original_tweet_id,
            "original_tweet_url": original_tweet_url,
            "url": original_tweet_url, # URL оригинала
            "tweet_id": original_tweet_id, # ID оригинала
            "is_retweet": False, # Это сам оригинал
            "is_truncated": is_truncated_flag
        }
        logger.info(f"Данные оригинального твита (@{original_author_name}) получены через Selenium.")

    except Exception as e:
        logger.error(f"Ошибка при получении данных оригинального твита ({original_tweet_url}) через Selenium: {e}")
        import traceback; logger.error(traceback.format_exc())
        original_data = None
    finally:
        try:
            if opened_new_window and new_window_handle and new_window_handle in driver.window_handles:
                 driver.close()
            driver.switch_to.window(current_window)
        except Exception as close_err: logger.error(f"Ошибка при закрытии вкладки оригинального твита: {close_err}")

    return original_data


def get_tweets_with_selenium(username, driver, db_connection=None, max_tweets=10, use_cache=True,
                             cache_duration_hours=1, time_filter_hours=24, force_refresh=False,
                             extract_full_tweets=True,
                             dependencies=None, html_cache_dir="twitter_html_cache"):
    """
    Получает твиты пользователя с помощью Selenium.
    Для ретвитов извлекает и сохраняет данные оригинального твита.
    API вызовы отключены.
    """
    if dependencies is None: dependencies = {}

    # Получаем зависимости
    save_user_to_db = dependencies.get('save_user_to_db')
    save_tweet_to_db = dependencies.get('save_tweet_to_db')
    filter_recent_tweets = dependencies.get('filter_recent_tweets')
    extract_retweet_info_enhanced = dependencies.get('extract_retweet_info_enhanced')
    # API функции больше не нужны
    # get_tweet_by_id = dependencies.get('get_tweet_by_id')
    # process_api_tweet_data = dependencies.get('process_api_tweet_data')

    logger.info(f"Начинаем получение твитов для @{username}...")
    cache_file = os.path.join(CACHE_DIR, f"{username}_tweets_selenium.json")
    result = {"username": username, "name": username, "tweets": []}

    # --- Проверка кэша ---
    if use_cache and os.path.exists(cache_file) and not force_refresh:
        try:
            logger.debug(f"Проверка кэша для @{username}...")
            file_modified_time = os.path.getmtime(cache_file)
            current_time = time.time()
            if current_time - file_modified_time < cache_duration_hours * 3600:
                with open(cache_file, 'r', encoding='utf-8') as f: cached_data = json.load(f)
                logger.info(f"Используем кэшированные данные для @{username}")
                result["name"] = cached_data.get("name", username)
                recent_tweets = filter_recent_tweets(cached_data.get('tweets', []), time_filter_hours)
                result["tweets"] = recent_tweets[:max_tweets]
                if result["tweets"]: return result
                else: logger.info(f"В кэше нет свежих твитов для @{username}, запрашиваем новые.")
        except Exception as e: logger.error(f"Ошибка при чтении кэша для @{username}: {e}")
    elif force_refresh: logger.info(f"Принудительное обновление данных для @{username}")

    try:
        logger.info(f"Загружаем страницу профиля @{username}...")
        profile_url = f"https://twitter.com/{username}"
        driver.get(profile_url)

        # --- Ожидание загрузки, проверка авторизации, сохранение HTML, извлечение имени, сохранение пользователя ---
        try: WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]')))
        except TimeoutException: logger.warning("Таймаут при ожидании загрузки твитов"); time.sleep(10)
        page_source = driver.page_source
        if "Log in" in page_source and "Sign up" in page_source and "The timeline is empty" not in page_source: logger.warning("Признаки авторизации не обнаружены.")
        if "This account doesn't exist" in page_source or "Hmm...this page doesn't exist" in page_source: logger.error(f"Аккаунт @{username} не существует или недоступен"); return result
        if html_cache_dir:
             html_file = os.path.join(html_cache_dir, f"{username}_selenium.html")
             try:
                 with open(html_file, "w", encoding="utf-8") as f: f.write(driver.page_source)
                 logger.debug(f"HTML сохранен: {html_file}")
             except Exception as e: logger.error(f"Не удалось сохранить HTML: {e}")
        try:
            name_element = driver.find_element(By.CSS_SELECTOR, 'h2[aria-level="2"][role="heading"] span span')
            if name_element: result["name"] = name_element.text.strip()
            else:
                title = driver.title
                if "(" in title: result["name"] = title.split("(")[0].strip()
            logger.info(f"Извлечено имя пользователя: {result['name']}")
        except Exception as e: logger.error(f"Ошибка при извлечении имени: {e}")
        user_id = None
        if db_connection and save_user_to_db:
            user_id = save_user_to_db(db_connection, username, result["name"])
            if user_id: logger.info(f"Пользователь @{username} сохранен/обновлен в БД с ID: {user_id}")
            else: logger.error(f"Ошибка при сохранении пользователя {username} в базу данных")


        # --- Скроллинг и обработка твитов ---
        processed_tweet_ids = set()
        tweets_data_to_cache = []
        scroll_attempts = 0; max_scroll_attempts = 40; no_new_tweets_count = 0; max_no_new_tweets = 5
        scroll_step = 1000; current_scroll_position = 0

        logger.info("Начинаем скроллинг и обработку твитов...")

        while scroll_attempts < max_scroll_attempts and no_new_tweets_count < max_no_new_tweets and len(tweets_data_to_cache) < max_tweets * 3:
            scroll_attempts += 1
            logger.debug(f"Попытка скроллинга #{scroll_attempts}...")
            current_scroll_position += scroll_step
            driver.execute_script(f"window.scrollTo(0, {current_scroll_position});")
            time.sleep(3)

            tweet_elements = find_all_tweets(driver)
            new_tweets_this_iteration = 0

            for tweet_element in tweet_elements:
                element_url = "" # URL текущего элемента (может быть ретвит или твит)
                element_id = ""  # ID текущего элемента
                final_tweet_data = None

                try:
                    # Извлекаем URL и ID текущего элемента
                    time_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
                    found_link = False
                    for link in time_links:
                         href = link.get_attribute('href')
                         if href and '/status/' in href and link.find_elements(By.TAG_NAME, 'time'):
                              element_url = href.split("?")[0] # Убираем параметры
                              # Извлекаем ID, удаляя возможные /photo/1 и т.п.
                              status_part = element_url.split("/status/")[-1]
                              element_id = status_part.split("/")[0]
                              if element_id.isdigit(): # Проверяем, что ID - число
                                   found_link = True; break
                    # Если не нашли ссылку с time, берем первую попавшуюся
                    if not found_link and time_links:
                         href = time_links[0].get_attribute('href')
                         if href and '/status/' in href:
                              element_url = href.split("?")[0]
                              status_part = element_url.split("/status/")[-1]
                              element_id = status_part.split("/")[0]
                              if not element_id.isdigit(): element_id = None # Невалидный ID

                    if not element_id or element_id in processed_tweet_ids:
                        continue

                    processed_tweet_ids.add(element_id)
                    logger.debug(f"Обработка элемента с ID: {element_id} (URL: {element_url})")

                    # --- API вызовы удалены ---
                    # api_tweet_data_raw = get_tweet_by_id(element_id) ...

                    # Определяем, ретвит ли это, и получаем инфо об оригинале
                    retweet_info = extract_retweet_info_enhanced(tweet_element)
                    is_retweet = retweet_info["is_retweet"]
                    original_author = retweet_info["original_author"]
                    original_tweet_url = retweet_info["original_tweet_url"]
                    original_tweet_id = original_tweet_url.split("/")[-1].split("?")[0] if original_tweet_url else None

                    # --- Логика обработки ретвита ---
                    if is_retweet and original_tweet_url and original_tweet_id:
                        logger.info(f"Обнаружен ретвит {element_id}. Получаем данные оригинала: {original_tweet_url}")

                        # Получаем данные оригинала ТОЛЬКО через Selenium
                        original_data = get_original_tweet_data_selenium(driver, original_tweet_url, extract_full_tweets)

                        if original_data:
                             # Формируем данные для сохранения: ID/URL ретвита, остальное - от оригинала
                             final_tweet_data = {
                                 "url": element_url, # URL ретвита
                                 "tweet_id": element_id, # ID ретвита
                                 "is_retweet": True,
                                 "original_author": original_data.get("original_author") or original_author,
                                 "original_tweet_id": original_data.get("original_tweet_id") or original_tweet_id,
                                 "original_tweet_url": original_data.get("original_tweet_url") or original_tweet_url,
                                 "text": original_data.get("text", ""),
                                 "created_at": original_data.get("created_at", ""),
                                 "stats": original_data.get("stats", {"likes": 0, "retweets": 0, "replies": 0}),
                                 "is_truncated": original_data.get("is_truncated", False)
                             }
                             logger.info(f"Данные оригинального твита (@{final_tweet_data['original_author']}) успешно получены для ретвита {element_id}")
                        else:
                             logger.error(f"Не удалось получить данные оригинального твита {original_tweet_url} через Selenium.")
                             continue # Пропускаем этот ретвит

                    # --- Логика обработки обычного твита ---
                    else:
                        logger.debug(f"Обработка обычного твита {element_id} через Selenium")
                        # Раскрываем контент, если нужно
                        expand_tweet_content_improved(driver, tweet_element)
                        time.sleep(0.5) # Небольшая пауза

                        # Извлекаем текст
                        tweet_text = ""
                        try:
                            tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                            tweet_text = tweet_text_element.text
                        except NoSuchElementException:
                            logger.warning(f"Текст твита {element_id} не найден (Selenium)")

                        # Получаем полный текст, если нужно
                        is_truncated_flag = False
                        if extract_full_tweets and tweet_text and is_tweet_truncated(tweet_element):
                            logger.info(f"Твит {element_id} обрезан, получаем полную версию...")
                            full_text = get_full_tweet_text(driver, element_url) # Используем URL элемента
                            if full_text and len(full_text) > len(tweet_text):
                                tweet_text = full_text
                                is_truncated_flag = True
                                logger.info(f"Полный текст твита {element_id} получен.")

                        # Извлекаем дату
                        created_at = ""
                        try:
                            time_element = tweet_element.find_element(By.CSS_SELECTOR, 'a[href*="/status/"] time') # Ищем time внутри ссылки
                            created_at = time_element.get_attribute('datetime')
                        except NoSuchElementException:
                            logger.warning(f"Не удалось найти время для твита {element_id}")
                            # Можно попробовать найти time просто по тегу, но это менее надежно
                            try:
                                 time_element = tweet_element.find_element(By.TAG_NAME, 'time')
                                 created_at = time_element.get_attribute('datetime')
                            except NoSuchElementException: pass


                        # Извлекаем статистику
                        stats = extract_tweet_stats(tweet_element)

                        # Формируем данные
                        final_tweet_data = {
                            "url": element_url,
                            "tweet_id": element_id,
                            "is_retweet": False,
                            "original_author": None,
                            "original_tweet_id": None,
                            "original_tweet_url": None,
                            "text": tweet_text,
                            "created_at": created_at,
                            "stats": stats,
                            "is_truncated": is_truncated_flag
                        }
                        logger.info(f"Твит {element_id} обработан через Selenium.")


                    # --- Сохранение результата ---
                    if final_tweet_data:
                        tweets_data_to_cache.append(final_tweet_data)
                        new_tweets_this_iteration += 1

                        # Сохраняем в базу данных
                        if db_connection and user_id and save_tweet_to_db:
                            save_tweet_to_db(db_connection, user_id, final_tweet_data)

                except StaleElementReferenceException:
                    logger.warning(f"Элемент твита устарел, пропускаем: {element_id}")
                    if element_id in processed_tweet_ids: processed_tweet_ids.remove(element_id)
                except Exception as e:
                    print(f"Ошибка при обработке элемента твита ID={element_id}: {e}")
                    logger.error(f"Ошибка при обработке элемента твита ID={element_id}: {e}")
                    import traceback; logger.error(traceback.format_exc())

            # --- Обновление счетчика и проверка конца страницы ---
            if new_tweets_this_iteration == 0:
                no_new_tweets_count += 1
                logger.info(f"Не найдено новых твитов. Счетчик: {no_new_tweets_count}/{max_no_new_tweets}")
            else:
                no_new_tweets_count = 0
                logger.info(f"Добавлено {new_tweets_this_iteration} новых твитов/ретвитов в этой итерации")
            try:
                viewport_height = driver.execute_script("return window.innerHeight")
                document_height = driver.execute_script("return document.documentElement.scrollHeight")
                if current_scroll_position >= document_height - viewport_height - 200:
                    logger.info("Достигнут конец страницы (или близко к нему)")
                    time.sleep(5)
                    new_document_height = driver.execute_script("return document.documentElement.scrollHeight")
                    if new_document_height <= document_height:
                        logger.info("Больше твитов не загружается, завершаем скроллинг")
                        break
            except Exception as e: logger.warning(f"Ошибка при проверке конца страницы: {e}")


        logger.info(f"Завершен скроллинг после {scroll_attempts} попыток")
        logger.info(f"Всего уникальных элементов обработано: {len(processed_tweet_ids)}")
        logger.info(f"Всего твитов/ретвитов собрано для кэша: {len(tweets_data_to_cache)}")

        # --- Фильтрация по времени и сохранение в кэш ---
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

        # Возвращаем отфильтрованные и ограниченные результаты
        result["tweets"] = recent_tweets[:max_tweets]
        logger.info(f"Возвращаем {len(result['tweets'])} свежих твитов/ретвитов для @{username}")
        return result

    except Exception as e:
        print(f"Критическая ошибка при получении твитов для @{username} через Selenium: {e}")
        logger.critical(f"Критическая ошибка при получении твитов для @{username} через Selenium: {e}")
        import traceback; logger.error(traceback.format_exc())
        return result
