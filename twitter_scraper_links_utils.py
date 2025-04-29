#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы со ссылками и анализа содержимого твитов.
(Функционал извлечения ссылок удален)
Содержит функции для определения обрезанных твитов и получения полного текста.
"""

import os
import re
import logging
# requests и BeautifulSoup больше не нужны
# import requests
# from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
# mysql.connector больше не нужен
# from mysql.connector import Error
import time

# Настройка логирования
logger = logging.getLogger('twitter_scraper.links')

# Константы
# LINKS_CACHE_DIR больше не нужен
# LINKS_CACHE_DIR = "twitter_links_cache"
# os.makedirs(LINKS_CACHE_DIR, exist_ok=True)

# --- Функция extract_all_links_from_tweet удалена ---
# def extract_all_links_from_tweet(tweet_element, username, expand_first=True):
#     """
#     Улучшенное извлечение всех ссылок из твита (УДАЛЕНО)
#     """
#     # ... (код функции удален) ...

# --- Функция save_links_to_db удалена ---
# def save_links_to_db(connection, tweet_db_id, links):
#     """
#     Сохраняет ссылки из твита в базу данных (УДАЛЕНО)
#     """
#     # ... (код функции удален) ...


def is_tweet_truncated(tweet_element):
    """
    Улучшенное определение обрезанных твитов
    """
    # Эта функция остается, так как она нужна для получения полного текста
    try:
        # 1. Проверка по классам и стилям
        truncated_classes = [
            'r-1sg46qm',  # Класс для сокращенного текста
            'r-1iusvr4',  # Контейнер сокращенного текста
            'r-linkify'  # Содержимое с сокращённой ссылкой
        ]

        for class_name in truncated_classes:
            elements = tweet_element.find_elements(By.CSS_SELECTOR, f'[class*="{class_name}"]')
            if elements:
                for elem in elements:
                    # Проверяем наличие многоточия в тексте элемента
                    try:
                        if '…' in elem.text or '...' in elem.text:
                            logger.info(f"Обнаружен обрезанный твит (класс: {class_name})")
                            return True
                    except: # Игнорируем ошибки StaleElementReferenceException
                        pass

        # 2. Проверка по кнопкам "Show more" / "Показать еще"
        xpath_indicators = [
            './/div[@role="button" and (contains(text(), "Show more") or contains(text(), "Показать ещё"))]',
            './/span[contains(text(), "Show more") or contains(text(), "Показать ещё")]'
        ]

        for xpath in xpath_indicators:
            try:
                elements = tweet_element.find_elements(By.XPATH, xpath)
                if elements:
                    logger.info(f"Обнаружен обрезанный твит (кнопка: {xpath})")
                    return True
            except: # Игнорируем ошибки StaleElementReferenceException
                 pass

        # 3. Проверка по многоточию в конце основного текста твита
        try:
            tweet_text_elements = tweet_element.find_elements(By.CSS_SELECTOR, 'div[data-testid="tweetText"], [lang]')
            for elem in tweet_text_elements:
                try:
                    text = elem.text.strip()
                    if text.endswith('…') or text.endswith('...'):
                        logger.info("Обнаружен обрезанный твит (многоточие в конце)")
                        return True
                except: # Игнорируем ошибки StaleElementReferenceException
                    pass
        except:
            pass

        # 4. Проверка URL на параметры (менее надежно, но может помочь)
        try:
            for link in tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]'):
                try:
                    href = link.get_attribute('href')
                    if href and ('/status/' in href) and ('s=20' in href or 's=19' in href):
                        logger.info(f"Обнаружен обрезанный твит (параметр s= в URL)")
                        return True
                except: # Игнорируем ошибки StaleElementReferenceException
                    pass
        except:
            pass

        return False

    except Exception as e:
        # Логируем только если ошибка не StaleElementReferenceException
        if "stale element reference" not in str(e).lower():
             logger.error(f"Ошибка при проверке обрезанности твита: {e}")
        return False


def get_full_tweet_text(driver, tweet_url, max_attempts=3):
    """
    Улучшенное получение полного текста твита с надежным методом раскрытия контента
    """
    # Эта функция остается, так как она нужна для получения полного текста
    full_text = ""
    current_window = None
    opened_new_window = False

    try:
        # Очищаем URL от параметров запроса
        clean_url = tweet_url.split('?')[0].split('#')[0]
        logger.info(f"Загружаем полную версию твита: {clean_url}")

        current_window = driver.current_window_handle

        # Открываем новую вкладку
        driver.execute_script("window.open('');")
        opened_new_window = True
        time.sleep(1)
        driver.switch_to.window(driver.window_handles[-1])

        # Загружаем твит напрямую
        driver.get(clean_url)
        time.sleep(3)  # Даем странице время на первичную загрузку

        # Ждем загрузки твита
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.common.exceptions import TimeoutException

            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'article[data-testid="tweet"], div[data-testid="tweetText"]'))
            )
        except TimeoutException:
            logger.warning("Таймаут при загрузке твита, пробуем альтернативный селектор")
            time.sleep(5)

        # Принудительное раскрытие текста
        for attempt in range(max_attempts):
             # 1. Попробуем найти и кликнуть по элементам "Show more"
            try:
                show_more_selectors = [
                    '//div[@role="button" and (contains(., "Show more") or contains(., "Показать ещё"))]',
                    '//span[contains(., "Show more") or contains(., "Показать ещё")]',
                    '//div[@data-testid="tweet"]//div[@role="button" and contains(., "more")]',
                    '//div[contains(@class, "css-1dbjc4n") and contains(., "…")]',
                    '//div[contains(@class, "r-1sg46qm")]',
                ]

                clicked_show_more = False
                for selector in show_more_selectors:
                    buttons = driver.find_elements(By.XPATH, selector)
                    if buttons:
                        for button in buttons:
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(0.5)
                                try:
                                    button.click()
                                except:
                                    driver.execute_script("arguments[0].click();", button)
                                time.sleep(2) # Ожидание после клика
                                logger.info("Успешно раскрыт твит через кнопку Show more")
                                clicked_show_more = True
                                break # Выходим из внутреннего цикла по кнопкам
                            except Exception as e:
                                logger.debug(f"Не удалось кликнуть на кнопку: {e}")
                        if clicked_show_more:
                            break # Выходим из цикла по селекторам

            except Exception as e:
                logger.debug(f"Ошибка при поиске кнопок Show more: {e}")

            # 2. Извлекаем текст после попыток раскрытия
            all_text_elements = []
            selectors = [
                'div[data-testid="tweetText"]',
                'article[data-testid="tweet"] div[lang]',
                'div[lang][dir="auto"]',
                'div[role="group"] div[dir="auto"]'
            ]

            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    all_text_elements.extend(elements)
                except:
                    pass # Игнорируем ошибки поиска

            # Собираем весь текст из найденных элементов
            current_text = ""
            processed_texts = set() # Для удаления дубликатов
            for elem in all_text_elements:
                 try:
                    elem_text = elem.text.strip()
                    # Если текст не пустой и не дублирует существующий
                    if elem_text and elem_text not in processed_texts:
                        if current_text:
                            current_text += " "
                        current_text += elem_text
                        processed_texts.add(elem_text)
                 except:
                    pass # Игнорируем ошибки получения текста

            # Проверка наличия многоточия в конце
            if current_text and not current_text.endswith('…') and not current_text.endswith('...'):
                if len(current_text) > len(full_text):
                    full_text = current_text
                    logger.info(f"Найден полный текст длиной {len(full_text)} символов (Попытка {attempt+1})")
                break # Полный текст найден
            elif len(current_text) > len(full_text):
                full_text = current_text # Сохраняем самый длинный найденный текст
                logger.info(f"Найден частично раскрытый текст ({len(full_text)} символов), пробуем еще раз")

            # Дополнительно прокручиваем страницу и ждем раскрытия
            if attempt < max_attempts - 1: # Не делаем на последней попытке
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.1);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)

        # 3. Извлечение текста через JavaScript (может обойти обрезание)
        try:
            js_text = driver.execute_script("""
                const tweetTextElements = document.querySelectorAll('[data-testid="tweetText"] span, [data-testid="tweetText"] div');
                let fullText = '';
                const processed = new Set();
                for (const element of tweetTextElements) {
                    // Проверяем, что элемент видим и содержит текст, но не содержит вложенных img/svg
                    if (element.offsetParent !== null && element.textContent && !element.querySelector('img, svg')) {
                         const text = element.textContent.trim();
                         if (text && !processed.has(text)) {
                            fullText += text + ' ';
                            processed.add(text);
                         }
                    }
                }
                return fullText.trim();
            """)

            if js_text and len(js_text) > len(full_text):
                full_text = js_text
                logger.info(f"Извлечен текст через JavaScript: {len(full_text)} символов")
        except Exception as e:
            logger.debug(f"Не удалось извлечь текст через JavaScript: {e}")

        # Закрываем вкладку и возвращаемся
        driver.close()
        opened_new_window = False
        driver.switch_to.window(current_window)

        if not full_text:
            logger.warning(f"Не удалось извлечь текст твита по URL: {tweet_url}")
        else:
            logger.info(f"Итоговый извлеченный текст: {len(full_text)} символов")

        return full_text

    except Exception as e:
        logger.error(f"Ошибка при получении полного текста твита: {e}")
        import traceback
        traceback.print_exc()

        # Возвращаемся к основной вкладке в случае ошибки
        try:
            if opened_new_window:
                driver.close()
            if current_window:
                driver.switch_to.window(current_window)
        except:
            pass

        return full_text or ""


def extract_full_tweet_text_from_html(driver, tweet_url):
    """
    Извлекает полный текст твита из HTML страницы (используется как резервный)
    """
    # Эта функция остается, так как она нужна для получения полного текста
    current_window = None
    opened_new_window = False
    full_text = ""

    try:
        current_window = driver.current_window_handle
        # Открываем новую вкладку
        driver.execute_script("window.open('');")
        opened_new_window = True
        time.sleep(1)
        driver.switch_to.window(driver.window_handles[-1])

        # Загружаем твит напрямую
        driver.get(tweet_url)
        time.sleep(5)  # Увеличенное время ожидания загрузки

        # Вариант 1: Используем продвинутый XPath для поиска всех текстовых элементов внутри твита
        try:
            text_parts = []
            # Находим основные элементы твита с текстом, исключая дочерние элементы с картинками/иконками
            text_elements = driver.find_elements(By.XPATH,
                                                 "//article//div[@lang]//span[not(ancestor::a) and not(.//img) and not(.//svg)] | //article//div[@lang]/text()")

            processed_texts = set()
            for elem in text_elements:
                 try:
                    text = elem.text.strip() if hasattr(elem, 'text') else str(elem).strip()
                    if text and len(text) > 1 and text not in processed_texts:
                        # Исключаем имена пользователей и хэштеги, если они отдельные элементы
                        if not (text.startswith('@') or text.startswith('#')):
                            text_parts.append(text)
                            processed_texts.add(text)
                 except:
                    pass # Игнорируем ошибки

            if text_parts:
                full_text = ' '.join(text_parts)
        except Exception as e:
            logger.warning(f"Ошибка при извлечении текста методом 1 (HTML): {e}")

        # Если первый метод не сработал, пробуем другой
        if not full_text:
            try:
                lang_elements = driver.find_elements(By.CSS_SELECTOR, "[lang][dir='auto']")
                processed_texts = set()
                temp_text = ""
                for elem in lang_elements:
                    try:
                        text = elem.text.strip()
                        if text and text not in processed_texts:
                             temp_text += text + " "
                             processed_texts.add(text)
                    except:
                        pass # Игнорируем ошибки
                if len(temp_text.strip()) > len(full_text):
                    full_text = temp_text.strip()
            except Exception as e:
                logger.warning(f"Ошибка при извлечении текста методом 2 (HTML): {e}")

        # Третий метод - используем JavaScript для извлечения текста
        if not full_text or len(full_text) < 50:
            try:
                js_text = driver.execute_script("""
                    const article = document.querySelector('article[data-testid="tweet"]');
                    if (!article) return "";
                    const textElements = article.querySelectorAll('div[lang] > span, div[lang]');
                    let text = '';
                    const processed = new Set();
                    for (const el of textElements) {
                        if (el.offsetParent !== null && el.textContent && !el.querySelector('img, svg')) {
                             const currentText = el.textContent.trim();
                             if (currentText && !processed.has(currentText)) {
                                text += currentText + ' ';
                                processed.add(currentText);
                             }
                        }
                    }
                    return text.trim();
                """)

                if js_text and len(js_text) > len(full_text):
                    full_text = js_text
            except Exception as e:
                logger.warning(f"Ошибка при извлечении текста через JavaScript (HTML): {e}")

        # Закрываем вкладку и возвращаемся
        driver.close()
        opened_new_window = False
        driver.switch_to.window(current_window)

        return full_text

    except Exception as e:
        logger.error(f"Общая ошибка при извлечении текста твита (HTML): {e}")
        try:
            if opened_new_window:
                driver.close()
            if current_window:
                driver.switch_to.window(current_window)
        except:
            pass
        return full_text
