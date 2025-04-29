#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы с текстом твитов.
Содержит функции для определения обрезанных твитов и получения полного текста.
РЕФАКТОРИНГ: get_full_tweet_text использует навигацию в той же вкладке.
"""

import os
import re
import logging
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Настройка логирования
logger = logging.getLogger('twitter_scraper.links')
if not logger.handlers:
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def is_tweet_truncated(tweet_element):
    """
    Улучшенное определение обрезанных твитов (без изменений)
    """
    try:
        # 1. Проверка на наличие кнопки "Show more" / "Показать еще"
        show_more_selectors_xpath = [
            './/div[@role="button" and (contains(., "Show more") or contains(., "Показать ещё"))]',
            './/span[contains(., "Show more") or contains(., "Показать ещё")]'
        ]
        for xpath in show_more_selectors_xpath:
            try:
                button = tweet_element.find_element(By.XPATH, xpath)
                # Дополнительно проверяем, видима ли кнопка, т.к. она может быть в DOM, но скрыта
                if button.is_displayed():
                     logger.debug(f"Твит обрезан (найдена видимая кнопка: {xpath})")
                     return True
            except (NoSuchElementException, StaleElementReferenceException):
                continue # Ищем следующий селектор

        # 2. Проверка на наличие многоточия в конце видимого текста
        try:
            # Ищем основной контейнер текста
            text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
            visible_text = text_element.text.strip()
            if visible_text.endswith(('…', '...')):
                 logger.debug("Твит обрезан (видимое многоточие в data-testid='tweetText')")
                 return True

            # Иногда текст разбит на span'ы, проверяем последний видимый span
            spans = text_element.find_elements(By.XPATH, './/span[not(ancestor::*[@aria-hidden="true"])]') # Ищем видимые span'ы
            if spans:
                 last_visible_span_text = ""
                 for span in reversed(spans): # Идем с конца
                      try:
                           if span.is_displayed():
                                last_visible_span_text = span.text.strip()
                                break
                      except StaleElementReferenceException: continue
                 if last_visible_span_text.endswith(('…', '...')):
                      logger.debug("Твит обрезан (видимое многоточие в последнем span)")
                      return True

        except (NoSuchElementException, StaleElementReferenceException):
             logger.debug("Не удалось найти элемент текста или span'ы для проверки многоточия.")
        except Exception as e:
             logger.warning(f"Ошибка при проверке многоточия: {e}")


        # 3. Проверка на наличие специфичных классов, которые часто используются для обрезки
        # Этот метод менее надежен из-за изменчивости классов Twitter
        # truncated_classes = ['r-1jkjb', 'r-1pjcn9w', 'r-1bymd8e'] # Примерные классы (НУЖНО ПРОВЕРЯТЬ АКТУАЛЬНОСТЬ)
        # try:
        #     for class_name in truncated_classes:
        #         elements = tweet_element.find_elements(By.CSS_SELECTOR, f'.{class_name}')
        #         if elements:
        #             for elem in elements:
        #                 try:
        #                     if elem.is_displayed() and ('…' in elem.text or '...' in elem.text):
        #                         logger.debug(f"Твит обрезан (класс: {class_name})")
        #                         return True
        #                 except StaleElementReferenceException: continue
        # except (NoSuchElementException, StaleElementReferenceException):
        #     pass
        # except Exception as e:
        #      logger.warning(f"Ошибка при проверке классов обрезки: {e}")

        logger.debug("Признаков обрезки твита не найдено.")
        return False
    except StaleElementReferenceException:
        logger.warning("Элемент твита устарел во время проверки на обрезку.")
        return False # Не можем быть уверены
    except Exception as e:
        logger.error(f"Общая ошибка при проверке обрезанности твита: {e}")
        return False # В случае ошибки считаем, что не обрезан


# --- ИЗМЕНЕННАЯ ФУНКЦИЯ ---
def get_full_tweet_text(driver, tweet_url):
    """
    Получает полный текст твита, переходя по URL В ТОЙ ЖЕ ВКЛАДКЕ.
    Возвращает полный текст или пустую строку.
    """
    full_text = ""
    current_url = driver.current_url # Запоминаем URL для возврата
    wait_timeout = 15 # Таймаут ожидания загрузки твита
    max_attempts_expand = 3 # Попытки кликнуть "Show more"

    try:
        clean_url = tweet_url.split('?')[0].split('#')[0]
        logger.info(f"Загружаем полную версию твита (в той же вкладке): {clean_url}")

        # --- Переход на страницу твита ---
        driver.get(clean_url)

        # --- Ожидание загрузки твита ---
        tweet_article_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        text_locator = (By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
        try:
            # Ждем появления и статьи, и текстового блока внутри нее
            WebDriverWait(driver, wait_timeout).until(
                EC.all_of(
                    EC.presence_of_element_located(tweet_article_locator),
                    EC.presence_of_element_located(text_locator),
                    EC.url_contains(clean_url.split('/')[-1]) # Убедимся, что URL соответствует твиту
                )
            )
            logger.debug("Основной элемент твита и текст загружены.")
            time.sleep(1) # Небольшая пауза для прорисовки
            tweet_element = driver.find_element(*tweet_article_locator)

        except TimeoutException:
            logger.error(f"Таймаут при загрузке твита {clean_url} для получения полного текста.")
            # Попытка вернуться назад
            try:
                logger.info(f"Возвращаемся на предыдущую страницу: {current_url}")
                driver.get(current_url)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]')))
            except Exception as back_err: logger.error(f"Ошибка при возврате на предыдущую страницу: {back_err}")
            return "" # Возвращаем пустую строку
        except Exception as e:
             logger.error(f"Неожиданная ошибка при ожидании твита {clean_url}: {e}")
             # Попытка вернуться назад
             try:
                 logger.info(f"Возвращаемся на предыдущую страницу: {current_url}")
                 driver.get(current_url)
                 WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]')))
             except Exception as back_err: logger.error(f"Ошибка при возврате: {back_err}")
             return ""


        # --- Попытки раскрыть текст, если нужно ---
        initial_text = ""
        try:
            initial_text = tweet_element.find_element(*text_locator).text
            logger.debug(f"Начальный текст твита {clean_url}: {len(initial_text)} символов")
        except Exception as e: logger.warning(f"Не удалось получить начальный текст твита {clean_url}: {e}")

        full_text = initial_text # Начинаем с того, что есть

        # Проверяем, нужно ли раскрывать (используем ту же функцию is_tweet_truncated)
        if is_tweet_truncated(tweet_element):
             logger.info(f"Твит {clean_url} определен как обрезанный, пытаемся раскрыть...")
             for attempt in range(max_attempts_expand):
                 logger.debug(f"Попытка раскрытия текста #{attempt + 1}")
                 clicked_show_more = False
                 try:
                     # Ищем кнопку "Show more" / "Показать еще" ВНУТРИ загруженного твита
                     show_more_selectors_xpath = [
                         './/div[@role="button" and (contains(., "Show more") or contains(., "Показать ещё"))]',
                         './/span[contains(., "Show more") or contains(., "Показать ещё")]'
                     ]
                     show_more_button = None
                     for selector in show_more_selectors_xpath:
                         try:
                             button = tweet_element.find_element(By.XPATH, selector)
                             if button.is_displayed():
                                 show_more_button = button
                                 logger.debug(f"Найдена кнопка 'Show more' ({selector})")
                                 break
                         except (NoSuchElementException, StaleElementReferenceException): continue

                     if show_more_button:
                         try:
                             # Прокручиваем к кнопке и кликаем
                             driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", show_more_button)
                             time.sleep(0.5) # Пауза для завершения прокрутки
                             clickable_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(show_more_button))
                             clickable_button.click()
                             clicked_show_more = True
                             logger.info("Кликнули 'Show more'. Ждем обновления текста...")

                             # Ожидание: либо кнопка исчезнет, либо текст изменится
                             WebDriverWait(driver, 5).until(
                                 EC.any_of(
                                     EC.staleness_of(show_more_button),
                                     lambda d: d.find_element(*text_locator).text != full_text # Ждем изменения текста
                                 )
                             )
                             logger.info("Обновление после клика 'Show more' обнаружено.")
                             # Обновляем текст после ожидания
                             full_text = driver.find_element(*text_locator).text

                         except TimeoutException:
                             logger.warning("Таймаут ожидания обновления после клика 'Show more'. Текст мог не раскрыться.")
                             # Пробуем еще раз прочитать текст на всякий случай
                             try: full_text = driver.find_element(*text_locator).text
                             except: pass
                         except StaleElementReferenceException:
                             logger.info("Кнопка 'Show more' исчезла после клика (ожидаемо).")
                             # Текст должен был обновиться, читаем его
                             try: full_text = driver.find_element(*text_locator).text
                             except: logger.warning("Не удалось прочитать текст после исчезновения кнопки.")
                         except Exception as click_err:
                             logger.warning(f"Ошибка при клике/ожидании 'Show more': {click_err}")
                     else:
                          logger.debug("Кнопка 'Show more' не найдена на странице твита.")
                          break # Если кнопки нет, нет смысла пытаться дальше

                 except Exception as e:
                     logger.warning(f"Ошибка во время попытки раскрытия #{attempt + 1}: {e}")

                 # Проверяем, раскрылся ли текст после попытки
                 if not full_text.endswith(('…', '...')):
                     logger.info(f"Полный текст твита {clean_url} получен после {attempt + 1} попытки.")
                     break # Выходим из цикла попыток
                 else:
                     logger.info(f"Текст все еще обрезан после {attempt + 1} попытки.")
                     if attempt < max_attempts_expand - 1: time.sleep(1) # Пауза перед следующей попыткой

        else:
             logger.info(f"Твит {clean_url} не определен как обрезанный, используем начальный текст.")


    except WebDriverException as e:
        logger.error(f"Ошибка WebDriver при получении полного текста ({clean_url}): {e}")
        # Попытка восстановления
        try:
            logger.warning("Попытка восстановить сессию WebDriver переходом на twitter.com")
            driver.get("https://twitter.com")
            WebDriverWait(driver, 10).until(EC.url_contains("twitter.com"))
        except Exception as recovery_err:
            logger.error(f"Не удалось восстановить сессию WebDriver: {recovery_err}")
        full_text = "" # Текст не получен
    except Exception as e:
        logger.error(f"Общая ошибка при получении полного текста твита {clean_url}: {e}")
        import traceback; logger.error(traceback.format_exc())
        full_text = "" # Возвращаем пустую строку в случае ошибки
    finally:
        # --- Возвращаемся на исходную страницу ---
        try:
            if driver.current_url != current_url:
                 logger.info(f"Возвращаемся на предыдущую страницу: {current_url}")
                 driver.get(current_url)
                 # Ждем загрузки основного контента (например, первого твита)
                 WebDriverWait(driver, 15).until(
                     EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]'))
                 )
                 logger.debug("Успешно вернулись на предыдущую страницу.")
            else:
                 logger.debug("Уже находимся на исходной странице, возврат не требуется.")
        except Exception as back_err:
            logger.error(f"Критическая ошибка при возврате на страницу {current_url}: {back_err}")
            # Попытка перезагрузить исходную страницу
            try:
                logger.warning(f"Повторная попытка загрузить страницу: {current_url}")
                driver.get(current_url)
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]')))
            except Exception as retry_err:
                 logger.critical(f"Не удалось вернуться на страницу {current_url} даже после повторной попытки: {retry_err}.")


    if not full_text: logger.warning(f"Итоговый полный текст для {clean_url} не получен.")
    else: logger.info(f"Итоговый извлеченный текст для {clean_url}: {len(full_text)} символов")

    return full_text or "" # Возвращаем текст или пустую строку
