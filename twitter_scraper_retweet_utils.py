# twitter_scraper_retweet_utils.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы с ретвитами и анализа информации об авторах.
Исправлена логика поиска URL оригинального твита.
ИЗМЕНЕНО: Удален поиск оригинального автора.
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
    Возвращает флаг ретвита и URL оригинального твита (если найден).
    НЕ ищет оригинального автора.

    Args:
        tweet_element: Элемент твита Selenium WebDriver

    Returns:
        dict: Словарь с информацией о ретвите:
              {"is_retweet": bool, "original_tweet_url": str|None}
    """
    result = {
        "is_retweet": False,
        # "original_author": None, # <-- УДАЛЕНО
        "original_tweet_url": None
    }
    is_quote_tweet = False

    try:
        logger.debug("Начало расширенной проверки на ретвит/цитирование...")

        # --- Проверка на цитирование (Quote Tweet) ---
        try:
            # Ищем вложенный article или div[@role="link"] для цитат
            quote_tweet_elements = tweet_element.find_elements(By.XPATH, './/article[.//article] | .//div[@role="link" and contains(@aria-label, "Quote")]//article | .//div[@role="link" and count(.//article)>0]')
            if quote_tweet_elements:
                 logger.debug("Обнаружен Quote Tweet (вложенный твит или ссылка-цитата)")
                 is_quote_tweet = True
                 return result # Не считаем цитату простым ретвитом

        except (NoSuchElementException, StaleElementReferenceException): pass
        except Exception as e: logger.warning(f"Ошибка при проверке на Quote Tweet: {e}")

        # --- Если не цитирование, проверяем на ретвит ---
        # МЕТОД 1: SocialContext
        try:
            social_context = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="socialContext"]')
            context_text = social_context.text.lower()
            retweet_keywords = ["retweeted", "reposted", "ретвитнул", "ретвитнула", "повторно опубликовал"]

            if any(keyword in context_text for keyword in retweet_keywords):
                logger.debug(f"Обнаружен ретвит через socialContext текст: '{context_text}'")
                result["is_retweet"] = True

                # Ищем ТОЛЬКО URL оригинала в ссылках внутри socialContext
                links_in_context = social_context.find_elements(By.TAG_NAME, 'a')
                for link in links_in_context:
                    try:
                        href = link.get_attribute('href')
                        if not href: continue

                        # URL оригинала (ссылка на статус)
                        if '/status/' in href and not result["original_tweet_url"]:
                             # Убедимся, что это не ссылка на аналитику и т.п.
                             if not any(part in href for part in ['/analytics', '/likes', '/retweets']):
                                  result["original_tweet_url"] = href.split("?")[0] # Убираем параметры
                                  logger.debug(f"Найден URL оригинала (socialContext link): {result['original_tweet_url']}")
                                  # Не прерываем цикл, вдруг дальше будет ссылка на профиль,
                                  # хотя мы её и не используем сейчас.
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
        if result["is_retweet"] and not result["original_tweet_url"]:
            logger.debug("Поиск URL оригинала в других местах (т.к. не найден в socialContext)...")
            try:
                # Ищем ссылку на статус, которая ассоциирована с временем публикации ретвита
                time_links = tweet_element.find_elements(By.XPATH, './/a[.//time and contains(@href, "/status/")]')

                if time_links:
                    for link in time_links:
                        try:
                            href = link.get_attribute('href')
                            if href and '/status/' in href:
                                # Проверяем, не является ли эта ссылка ссылкой на сам ретвит (сложно)
                                # Дополнительно проверяем, что это не ссылка внутри цитаты
                                is_inside_quote = False
                                try:
                                     # Проверяем, есть ли родительский элемент с ролью link (признак цитаты)
                                     # ИЛИ является ли ссылка потомком блока с data-testid="tweet" который сам является потомком другого data-testid="tweet"
                                     quote_container = link.find_element(By.XPATH, './ancestor::div[@role="link"] | ./ancestor::article[@data-testid="tweet"]/ancestor::article[@data-testid="tweet"]')
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
                # которая не является ссылкой на профиль или аналитику и не внутри цитаты
                if not result["original_tweet_url"]:
                     all_status_links = tweet_element.find_elements(By.CSS_SELECTOR, 'article a[href*="/status/"]')
                     for link in all_status_links:
                          try:
                               href = link.get_attribute('href')
                               if href and '/status/' in href and not any(part in href for part in ['/analytics', '/likes', '/retweets', '/photo/', '/video/']):
                                    # Проверяем, не ссылка ли это внутри цитаты
                                    is_inside_quote = False
                                    try:
                                         quote_container = link.find_element(By.XPATH, './ancestor::div[@role="link"] | ./ancestor::article[@data-testid="tweet"]/ancestor::article[@data-testid="tweet"]')
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

        # Финальная проверка: если определили как ретвит, но нет URL - сбрасываем флаг
        if result["is_retweet"] and not result["original_tweet_url"]:
             logger.warning(f"Определен как ретвит, но не найден URL оригинала. Сбрасываем флаг is_retweet.")
             result["is_retweet"] = False
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
    (Остается без изменений как резерв, но не ищет автора)
    """
    result = {"is_retweet": False, "original_tweet_url": None} # "original_author": None, <-- УДАЛЕНО
    try:
        social_context = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"]')
        if social_context:
            context_text = social_context[0].text.lower()
            if any(term in context_text for term in ["retweeted", "reposted", "ретвитнул"]):
                result["is_retweet"] = True
                # Пытаемся извлечь имя оригинального автора - НЕ НУЖНО
                # mentions = re.findall(r'@(\w+)', social_context[0].text)
                # if mentions: result["original_author"] = mentions[0]
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

        # Сброс, если не хватает URL
        if result["is_retweet"] and not result["original_tweet_url"]:
             result["is_retweet"] = False; result["original_tweet_url"] = None

    except Exception as e: logger.error(f"Ошибка при базовой проверке ретвита: {e}")
    return result


def get_author_info(tweet_element):
    """
    Извлекает информацию об авторе твита (или ретвитующего пользователя)
    (Без изменений)
    """
    author_info = {"username": None, "display_name": None, "verified": False}
    try:
        # Ищем блок с именем пользователя. Селектор может меняться.
        # Попробуем найти ссылку внутри блока с User-Name, которая ведет на профиль
        user_link_elements = tweet_element.find_elements(By.XPATH, './/div[@data-testid="User-Name"]//a[@role="link" and starts-with(@href, "/")]')

        author_block = None
        user_link = None
        for link in user_link_elements:
            href = link.get_attribute('href')
            # Исключаем ссылки на статус, ищем ссылку на профиль
            if href and ('/status/' not in href) and ('/photo/' not in href) and ('/video/' not in href):
                 # Нашли ссылку на профиль, берем родительский блок User-Name
                 try:
                      author_block = link.find_element(By.XPATH, './ancestor::div[@data-testid="User-Name"]')
                      user_link = link # Сохраняем ссылку для извлечения username
                      break
                 except NoSuchElementException:
                      continue # Ищем дальше

        if author_block:
             try: # Отображаемое имя
                  # Ищем span, который не содержит @ и не является dir=ltr
                  name_span = author_block.find_element(By.XPATH, './/span[not(contains(text(), "@")) and not(@dir="ltr")]/span[not(contains(text(), "@"))]')
                  if name_span and name_span.text.strip():
                       author_info["display_name"] = name_span.text.strip()
                  else: # Запасной вариант - первый span в блоке
                       all_spans = author_block.find_elements(By.XPATH, './/span')
                       if all_spans and all_spans[0].text.strip():
                           author_info["display_name"] = all_spans[0].text.strip()

             except NoSuchElementException:
                  # Если не нашли span, берем текст всего блока и пытаемся извлечь
                  try: author_info["display_name"] = author_block.text.split('\n')[0].strip()
                  except: pass

             try: # Имя пользователя (@username) - из сохраненной ссылки
                  if user_link:
                       href = user_link.get_attribute('href')
                       username = href.strip('/').split('/')[-1].split('?')[0]
                       if username and re.match(r'^[A-Za-z0-9_]{1,15}$', username):
                            author_info["username"] = username
                  else: # Если ссылку не нашли, ищем span с dir="ltr"
                       username_span = author_block.find_element(By.CSS_SELECTOR, 'span[dir="ltr"]')
                       if username_span and "@" in username_span.text:
                            match = re.search(r'@(\w+)', username_span.text)
                            if match: author_info["username"] = match.group(1)
             except NoSuchElementException:
                  logger.debug("Не удалось извлечь username ни из ссылки, ни из span[dir=ltr]")

             try: # Верификация
                  author_block.find_element(By.CSS_SELECTOR, 'svg[aria-label*="Verified"]')
                  author_info["verified"] = True
             except NoSuchElementException: pass
        else:
            logger.debug("Не удалось найти блок автора User-Name с ссылкой на профиль")

    except (NoSuchElementException, StaleElementReferenceException): logger.debug("Ошибка поиска блока автора или ссылки на профиль")
    except Exception as e: logger.error(f"Ошибка при извлечении информации об авторе: {e}")

    # Если display_name не найден, но есть username, используем username
    if not author_info["display_name"] and author_info["username"]:
        author_info["display_name"] = author_info["username"]

    return author_info