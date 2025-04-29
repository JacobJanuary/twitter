#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы с ретвитами и анализа информации об авторах.
Исправлена логика поиска URL оригинального твита.
"""

import re
import logging
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException

# Настройка логирования
logger = logging.getLogger('twitter_scraper.retweets')
if not logger.handlers:
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def extract_retweet_info_enhanced(tweet_element):
    """
    Улучшенная функция для извлечения информации о ретвите.
    Возвращает также URL оригинального твита. Исправлен поиск URL.

    Args:
        tweet_element: Элемент твита Selenium WebDriver

    Returns:
        dict: Словарь с информацией о ретвите:
              {"is_retweet": bool, "original_author": str|None, "original_tweet_url": str|None}
    """
    result = {
        "is_retweet": False,
        "original_author": None,
        "original_tweet_url": None
    }
    is_quote_tweet = False

    try:
        logger.debug("Начало расширенной проверки на ретвит/цитирование...")

        # --- Проверка на цитирование (Quote Tweet) ---
        try:
            # Ищем вложенный article, который НЕ является первым (основным)
            # Используем XPath для поиска article, который является потомком другого article
            # или находится внутри специфичного div-контейнера для цитат
            quote_tweet_elements = tweet_element.find_elements(By.XPATH, './/article[.//article] | .//div[@role="link" and contains(@aria-label, "Quote")]//article')
            if quote_tweet_elements:
                 logger.debug("Обнаружен Quote Tweet (вложенный твит или ссылка-цитата)")
                 is_quote_tweet = True
                 return result # Не считаем цитату простым ретвитом

        except (NoSuchElementException, StaleElementReferenceException): pass
        except Exception as e: logger.warning(f"Ошибка при проверке на Quote Tweet: {e}")

        # --- Если не цитирование, проверяем на ретвит ---
        # МЕТОД 1: SocialContext (наиболее надежный)
        try:
            social_context = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="socialContext"]')
            context_text = social_context.text.lower()
            retweet_keywords = ["retweeted", "reposted", "ретвитнул", "ретвитнула", "повторно опубликовал"]

            if any(keyword in context_text for keyword in retweet_keywords):
                logger.debug(f"Обнаружен ретвит через socialContext текст: '{context_text}'")
                result["is_retweet"] = True

                # Ищем автора и URL оригинала в ссылках внутри socialContext
                links_in_context = social_context.find_elements(By.TAG_NAME, 'a')
                for link in links_in_context:
                    try:
                        href = link.get_attribute('href')
                        if not href: continue

                        # Автор оригинала (ссылка на профиль)
                        if '/status/' not in href and ('twitter.com/' in href or 'x.com/' in href):
                            username = href.split('/')[-1].split('?')[0].strip('/')
                            if username and not result["original_author"]:
                                result["original_author"] = username
                                logger.debug(f"Найден оригинальный автор (socialContext link): @{username}")

                        # URL оригинала (ссылка на статус)
                        elif '/status/' in href and not result["original_tweet_url"]:
                             # Убедимся, что это не ссылка на аналитику и т.п.
                             if not any(part in href for part in ['/analytics', '/likes', '/retweets']):
                                  result["original_tweet_url"] = href.split("?")[0] # Убираем параметры
                                  logger.debug(f"Найден URL оригинала (socialContext link): {result['original_tweet_url']}")
                    except StaleElementReferenceException:
                         logger.warning("Ссылка в socialContext устарела во время обработки.")
                         continue
                    except Exception as link_err:
                         logger.warning(f"Ошибка обработки ссылки в socialContext: {link_err}")

                # Если нашли socialContext с текстом ретвита, но не нашли URL, это странно, но возможно
                if result["is_retweet"] and not result["original_tweet_url"]:
                     logger.warning("SocialContext указывает на ретвит, но URL оригинала не найден внутри него.")

        except NoSuchElementException:
             logger.debug("SocialContext не найден, проверяем другие методы.")
        except StaleElementReferenceException:
             logger.warning("Элемент socialContext устарел во время проверки.")
        except Exception as e:
            logger.error(f"Ошибка при проверке socialContext: {e}")

        # МЕТОД 2: Поиск URL оригинала в других местах, если socialContext не дал результата или не найден
        # (Этот метод сработает и если socialContext был, но URL там не было)
        if result["is_retweet"] and not result["original_tweet_url"]:
            logger.debug("Поиск URL оригинала в других местах...")
            try:
                # Ищем ссылку на статус, которая ассоциирована с временем публикации ретвита
                # Это часто основная ссылка на оригинальный твит в структуре ретвита
                # Ищем ссылку 'a', внутри которой есть 'time'
                time_links = tweet_element.find_elements(By.XPATH, './/a[.//time and contains(@href, "/status/")]')

                if time_links:
                    for link in time_links:
                        try:
                            href = link.get_attribute('href')
                            if href and '/status/' in href:
                                # Проверяем, не является ли эта ссылка ссылкой на сам ретвит
                                # (Сложно надежно определить URL ретвита заранее, поэтому ищем любую подходящую)
                                # Дополнительно проверяем, что это не ссылка внутри цитаты
                                is_inside_quote = False
                                try:
                                     # Проверяем, есть ли родительский элемент с ролью link (признак цитаты)
                                     quote_container = link.find_element(By.XPATH, './ancestor::div[@role="link"]')
                                     if quote_container: is_inside_quote = True
                                except NoSuchElementException:
                                     pass

                                if not is_inside_quote:
                                     potential_url = href.split("?")[0]
                                     result["original_tweet_url"] = potential_url
                                     logger.debug(f"Найден URL оригинала (по ссылке с time): {result['original_tweet_url']}")
                                     break # Нашли - выходим
                        except StaleElementReferenceException: continue
                        except Exception as link_err: logger.warning(f"Ошибка обработки ссылки с time: {link_err}")

                # Если все еще не нашли, пробуем найти ЛЮБУЮ ссылку на статус внутри article,
                # которая не является ссылкой на профиль или аналитику
                if not result["original_tweet_url"]:
                     all_status_links = tweet_element.find_elements(By.CSS_SELECTOR, 'article a[href*="/status/"]')
                     for link in all_status_links:
                          try:
                               href = link.get_attribute('href')
                               if href and '/status/' in href and not any(part in href for part in ['/analytics', '/likes', '/retweets', '/photo/', '/video/']):
                                    # Проверяем, не ссылка ли это внутри цитаты
                                    is_inside_quote = False
                                    try:
                                         quote_container = link.find_element(By.XPATH, './ancestor::div[@role="link"]')
                                         if quote_container: is_inside_quote = True
                                    except NoSuchElementException: pass

                                    if not is_inside_quote:
                                         result["original_tweet_url"] = href.split("?")[0]
                                         logger.debug(f"Найден URL оригинала (по общей ссылке на статус): {result['original_tweet_url']}")
                                         break
                          except StaleElementReferenceException: continue
                          except Exception as link_err: logger.warning(f"Ошибка обработки общей ссылки на статус: {link_err}")

            except Exception as e:
                logger.error(f"Ошибка при поиске URL оригинального твита: {e}")

        # Финальная проверка: если определили как ретвит, но нет автора или URL - сбрасываем флаг
        if result["is_retweet"] and (not result["original_author"] or not result["original_tweet_url"]):
             logger.warning(f"Определен как ретвит, но не найден автор ({result['original_author']}) или URL ({result['original_tweet_url']}). Сбрасываем флаг is_retweet.")
             result["is_retweet"] = False
             result["original_author"] = None
             result["original_tweet_url"] = None


        logger.debug(f"Результат определения ретвита: {result}")
        return result

    except StaleElementReferenceException:
         logger.warning("Элемент твита устарел во время проверки ретвита.")
         return result # Возвращаем то, что успели собрать
    except Exception as e:
        logger.error(f"Общая ошибка при определении ретвита: {e}")
        return result


def extract_retweet_info_basic(tweet_element):
    """
    Базовая функция для извлечения информации о ретвите.
    (Остается без изменений как резерв)
    """
    result = {"is_retweet": False, "original_author": None, "original_tweet_url": None}
    try:
        social_context = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"]')
        if social_context:
            context_text = social_context[0].text.lower()
            if any(term in context_text for term in ["retweeted", "reposted", "ретвитнул"]):
                result["is_retweet"] = True
                # Пытаемся извлечь имя оригинального автора
                mentions = re.findall(r'@(\w+)', social_context[0].text)
                if mentions: result["original_author"] = mentions[0]
                # Пытаемся найти URL оригинала
                try:
                     links = social_context[0].find_elements(By.TAG_NAME, 'a')
                     for link in links:
                          href = link.get_attribute('href')
                          if href and '/status/' in href:
                               result["original_tweet_url"] = href.split("?")[0]; break
                except: pass
        # Проверка на наличие иконки ретвита (менее надежно)
        if not result["is_retweet"]:
            try:
                 retweet_icons = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="retweet"] svg')
                 if retweet_icons: result["is_retweet"] = True
            except (NoSuchElementException, StaleElementReferenceException): pass

        # Сброс, если не хватает данных
        if result["is_retweet"] and (not result["original_author"] or not result["original_tweet_url"]):
             result["is_retweet"] = False; result["original_author"] = None; result["original_tweet_url"] = None

    except Exception as e: logger.error(f"Ошибка при базовой проверке ретвита: {e}")
    return result


def get_author_info(tweet_element):
    """
    Извлекает информацию об авторе твита (или ретвита)
    (Без изменений)
    """
    author_info = {"username": None, "display_name": None, "verified": False}
    try:
        author_block = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"]')
        if author_block:
             try: # Отображаемое имя
                  name_span = author_block.find_element(By.CSS_SELECTOR, 'span:not([dir="ltr"]) > span')
                  if name_span and name_span.text.strip(): author_info["display_name"] = name_span.text.strip()
             except NoSuchElementException:
                  try: author_info["display_name"] = author_block.text.split('\n')[0].strip()
                  except: pass
             try: # Имя пользователя (@username)
                  username_span = author_block.find_element(By.CSS_SELECTOR, 'span[dir="ltr"]')
                  if username_span and "@" in username_span.text:
                       match = re.search(r'@(\w+)', username_span.text)
                       if match: author_info["username"] = match.group(1)
             except NoSuchElementException: # Ищем в ссылке
                  try:
                       link = author_block.find_element(By.TAG_NAME, 'a')
                       href = link.get_attribute('href')
                       if href and ('twitter.com/' in href or 'x.com/' in href) and '/status/' not in href:
                            if 'twitter.com/' in href: author_info["username"] = href.split('twitter.com/')[-1].split('?')[0].strip('/')
                            else: author_info["username"] = href.split('x.com/')[-1].split('?')[0].strip('/')
                  except NoSuchElementException: pass
             try: # Верификация
                  author_block.find_element(By.CSS_SELECTOR, 'svg[aria-label*="Verified"]')
                  author_info["verified"] = True
             except NoSuchElementException: pass
    except (NoSuchElementException, StaleElementReferenceException): logger.debug("Не удалось найти блок автора User-Name")
    except Exception as e: logger.error(f"Ошибка при извлечении информации об авторе: {e}")
    return author_info

