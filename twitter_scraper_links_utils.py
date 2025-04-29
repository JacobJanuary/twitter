#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы с текстом твитов.
Содержит функции для определения обрезанных твитов и получения полного текста.
Заменены time.sleep на WebDriverWait.
"""

import os
import re
import logging
from selenium.webdriver.common.by import By
# Добавляем импорты WebDriverWait
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
# Импорты requests, BeautifulSoup, mysql.connector удалены

# Настройка логирования
logger = logging.getLogger('twitter_scraper.links')
if not logger.handlers:
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Функции extract_all_links_from_tweet и save_links_to_db удалены ---


def is_tweet_truncated(tweet_element):
    """
    Улучшенное определение обрезанных твитов
    """
    # (Без изменений по сравнению с v3)
    try:
        truncated_classes = ['r-1sg46qm', 'r-1iusvr4', 'r-linkify']
        for class_name in truncated_classes:
            try:
                 elements = tweet_element.find_elements(By.CSS_SELECTOR, f'[class*="{class_name}"]')
                 if elements:
                      for elem in elements:
                           if '…' in elem.text or '...' in elem.text: logger.debug(f"Твит обрезан (класс: {class_name})"); return True
            except StaleElementReferenceException: pass
        xpath_indicators = [
            './/div[@role="button" and (contains(text(), "Show more") or contains(text(), "Показать ещё"))]',
            './/span[contains(text(), "Show more") or contains(text(), "Показать ещё")]'
        ]
        for xpath in xpath_indicators:
            try:
                 if tweet_element.find_elements(By.XPATH, xpath): logger.debug(f"Твит обрезан (кнопка: {xpath})"); return True
            except StaleElementReferenceException: pass
        try:
            tweet_text_elements = tweet_element.find_elements(By.CSS_SELECTOR, 'div[data-testid="tweetText"], [lang]')
            for elem in tweet_text_elements:
                try:
                     if elem.text.strip().endswith(('…', '...')): logger.debug("Твит обрезан (многоточие)"); return True
                except StaleElementReferenceException: pass
        except StaleElementReferenceException: pass
        return False
    except Exception as e:
        if "stale element reference" not in str(e).lower(): logger.error(f"Ошибка проверки обрезанности: {e}")
        return False


def get_full_tweet_text(driver, tweet_url, max_attempts=3):
    """
    Улучшенное получение полного текста твита с WebDriverWait.
    """
    full_text = ""
    current_window = None
    new_window_handle = None
    opened_new_window = False
    wait_timeout = 10 # Таймаут для ожиданий

    try:
        clean_url = tweet_url.split('?')[0].split('#')[0]
        logger.info(f"Загружаем полную версию твита: {clean_url}")
        current_window = driver.current_window_handle
        initial_window_count = len(driver.window_handles)

        # Открываем новую вкладку
        driver.execute_script("window.open('');")
        opened_new_window = True

        # Ждем открытия новой вкладки
        WebDriverWait(driver, wait_timeout).until(EC.number_of_windows_to_be(initial_window_count + 1))
        all_windows = driver.window_handles
        new_window_handle = [window for window in all_windows if window != current_window][0]
        driver.switch_to.window(new_window_handle)
        logger.debug("Переключились на новую вкладку.")

        # Загружаем твит напрямую
        driver.get(clean_url)

        # Ждем загрузки основного элемента твита
        try:
            tweet_article_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
            WebDriverWait(driver, wait_timeout + 5).until( # Увеличенный таймаут для загрузки страницы
                EC.presence_of_element_located(tweet_article_locator)
            )
            logger.debug("Основной элемент твита загружен.")
        except TimeoutException:
            logger.warning(f"Таймаут при загрузке твита {clean_url}, пробуем извлечь текст как есть.")
            # Не выходим, попробуем извлечь текст из того что загрузилось

        # Принудительное раскрытие текста
        for attempt in range(max_attempts):
            logger.debug(f"Попытка раскрытия текста #{attempt + 1}")
            clicked_show_more = False
            try:
                show_more_selectors_xpath = [
                    './/div[@role="button" and (contains(., "Show more") or contains(., "Показать ещё"))]',
                    './/span[contains(., "Show more") or contains(., "Показать ещё")]',
                    './/div[contains(@class, "r-1sg46qm")]',
                ]
                # Используем основной элемент твита для поиска кнопки внутри него
                tweet_element = driver.find_element(*tweet_article_locator)

                for selector in show_more_selectors_xpath:
                    try:
                        buttons = tweet_element.find_elements(By.XPATH, selector)
                        if buttons:
                            for button in buttons:
                                try:
                                    # Проверяем, видима ли кнопка перед кликом
                                    if button.is_displayed():
                                         driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                         time.sleep(0.5) # Короткая пауза для прокрутки
                                         # Используем WebDriverWait для кликабельности
                                         WebDriverWait(driver, 3).until(EC.element_to_be_clickable(button))
                                         button.click()
                                         clicked_show_more = True
                                         logger.info("Кликнули 'Show more'. Ждем обновления текста...")
                                         # Ждем, пока кнопка исчезнет или текст изменится (сложно надежно)
                                         # Простая пауза после клика может быть надежнее здесь
                                         time.sleep(2)
                                         break
                                except (TimeoutException, StaleElementReferenceException, Exception) as click_err:
                                    logger.debug(f"Не удалось кликнуть 'Show more' ({selector}): {click_err}")
                            if clicked_show_more: break
                    except (NoSuchElementException, StaleElementReferenceException): continue # Кнопка может исчезнуть
                if clicked_show_more: logger.debug("'Show more' обработана.")

            except Exception as e: logger.debug(f"Ошибка при поиске/клике 'Show more': {e}")

            # Извлекаем текст после попыток раскрытия
            # Используем WebDriverWait для ожидания элемента с текстом
            current_text = ""
            try:
                 text_locator = (By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                 text_element = WebDriverWait(driver, 5).until(EC.presence_of_element_located(text_locator))
                 current_text = text_element.text.strip()
                 logger.debug(f"Извлечен текст (попытка {attempt + 1}): {len(current_text)} символов")
            except TimeoutException:
                 logger.warning(f"Не удалось найти элемент текста [data-testid=\"tweetText\"] на {clean_url}")
                 # Попробуем другой селектор
                 try:
                      lang_elements = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"] div[lang]')
                      if lang_elements: current_text = " ".join(el.text.strip() for el in lang_elements if el.text.strip())
                 except Exception as lang_err: logger.warning(f"Ошибка поиска текста по [lang]: {lang_err}")


            # Проверка наличия многоточия в конце
            if current_text and not current_text.endswith('…') and not current_text.endswith('...'):
                if len(current_text) > len(full_text): full_text = current_text
                logger.info(f"Полный текст найден (длина {len(full_text)}).")
                break
            elif len(current_text) > len(full_text):
                full_text = current_text
                logger.info(f"Найден частично раскрытый текст ({len(full_text)}), пробуем еще раз...")

            if attempt < max_attempts - 1:
                 # Небольшая пауза перед следующей попыткой
                 time.sleep(1)

        # Извлечение через JS как резервный метод
        if not full_text or (full_text.endswith('…') or full_text.endswith('...')):
             try:
                 logger.debug("Пробуем извлечь текст через JavaScript...")
                 js_text = driver.execute_script("""
                     const article = document.querySelector('article[data-testid="tweet"]');
                     if (!article) return "";
                     const textElement = article.querySelector('[data-testid="tweetText"]');
                     return textElement ? textElement.textContent.trim() : "";
                 """)
                 if js_text and len(js_text) > len(full_text):
                      # Проверяем, не обрезан ли JS текст
                      if not js_text.endswith('…') and not js_text.endswith('...'):
                           full_text = js_text
                           logger.info(f"Извлечен полный текст через JavaScript: {len(full_text)} символов")
                      elif len(js_text) > len(full_text): # Если JS текст длиннее, но обрезан
                           full_text = js_text
                           logger.warning(f"Извлечен обрезанный текст через JavaScript: {len(full_text)} символов")

             except Exception as e: logger.debug(f"Не удалось извлечь текст через JavaScript: {e}")


    except Exception as e:
        logger.error(f"Ошибка при получении полного текста твита {tweet_url}: {e}")
        import traceback; logger.error(traceback.format_exc())
    finally:
        # Закрываем новую вкладку и возвращаемся
        try:
            if opened_new_window and new_window_handle and new_window_handle in driver.window_handles:
                 driver.close()
            if current_window and current_window in driver.window_handles:
                 driver.switch_to.window(current_window)
            else: # Если исходное окно закрылось, переключаемся на первое доступное
                 if driver.window_handles:
                      driver.switch_to.window(driver.window_handles[0])
        except Exception as close_err: logger.error(f"Ошибка при закрытии вкладки/переключении: {close_err}")

    if not full_text: logger.warning(f"Не удалось извлечь полный текст твита: {tweet_url}")
    else: logger.info(f"Итоговый извлеченный текст для {tweet_url}: {len(full_text)} символов")

    return full_text or ""

# Функция extract_full_tweet_text_from_html удалена, так как get_full_tweet_text теперь основная
