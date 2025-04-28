#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы со ссылками и анализа содержимого твитов.
Отвечает за извлечение ссылок разных типов и их обработку.
(time.sleep заменен на WebDriverWait)
"""

import os
import re
import logging
import requests
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from mysql.connector import Error
import time # Оставляем для редких случаев

# Настройка логирования
logger = logging.getLogger('twitter_scraper.links')

# Константы
LINKS_CACHE_DIR = "twitter_links_cache"
os.makedirs(LINKS_CACHE_DIR, exist_ok=True)


def extract_all_links_from_tweet(tweet_element, username, expand_first=True):
    """
    Улучшенное извлечение всех ссылок из твита. Использует WebDriverWait.
    """
    links = {
        "external_urls": [],  # Внешние ссылки
        "mentions": [],  # @упоминания
        "hashtags": [],  # #хэштеги
        "media_urls": []  # Ссылки на медиа (если они есть как <a>)
    }
    driver = tweet_element.parent # Получаем драйвер из родительского элемента
    wait_short = WebDriverWait(driver, 3) # Короткое ожидание

    try:
        # Если нужно раскрыть длинный пост, делаем это сначала
        if expand_first:
            try:
                # Ищем кнопку "Show more" / "Показать ещё"
                show_more_xpath = './/div[@role="button" and (contains(text(), "Show more") or contains(text(), "Показать ещё"))] | .//span[contains(text(), "Show more") or contains(text(), "Показать ещё")]'
                show_more_buttons = tweet_element.find_elements(By.XPATH, show_more_xpath)

                if show_more_buttons:
                    logger.info("Найдена кнопка 'Show more', раскрываем пост перед извлечением ссылок...")
                    button_to_click = show_more_buttons[0]
                    try:
                        # Ждем кликабельности кнопки
                        clickable_button = wait_short.until(EC.element_to_be_clickable(button_to_click))
                        try:
                            clickable_button.click()
                        except:
                            driver.execute_script("arguments[0].click();", clickable_button)
                        # Ждем немного после клика (сложно определить точное условие завершения)
                        time.sleep(1) # Короткий sleep после клика может быть оправдан
                        logger.info("Клик по 'Show more' выполнен.")
                    except TimeoutException:
                        logger.warning("Кнопка 'Show more' не стала кликабельной.")
                    except Exception as e:
                        logger.warning(f"Не удалось кликнуть на 'Show more': {e}")
            except Exception as e:
                logger.warning(f"Ошибка при попытке раскрыть пост: {e}")

        # Получаем все ссылки в твите ПОСЛЕ возможного раскрытия
        link_elements = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href]')

        # Фильтры для исключения ложных ссылок
        excluded_texts = [
            "тыс.", "млн", "апр.", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек",
            "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
            "hours", "mins", "час", "мин", "дн", "days", "week"
        ]

        # Паттерн для проверки внутренних URL профиля
        internal_profile_pattern = re.compile(rf"(twitter|x)\.com/{username}(?![/\w])", re.IGNORECASE) # Только сам профиль

        for link in link_elements:
            try:
                href = link.get_attribute('href')
                if not href: continue

                link_text = link.text.strip()

                # Пропускаем элементы с метриками и датами
                if any(exc in link_text for exc in excluded_texts):
                    logger.debug(f"Пропускаем ссылку с исключенным текстом: {link_text}")
                    continue

                # Пропускаем ссылку на профиль самого пользователя
                if internal_profile_pattern.search(href):
                    logger.debug(f"Пропускаем ссылку на профиль пользователя: {href}")
                    continue

                # Обрабатываем ссылки по категориям
                # 1. Хэштеги
                if ('twitter.com/hashtag/' in href or 'x.com/hashtag/' in href):
                    hashtag = href.split('/hashtag/')[-1].split('?')[0]
                    if hashtag and hashtag not in links["hashtags"]:
                        links["hashtags"].append(hashtag)
                        logger.debug(f"Добавлен хэштег: {hashtag}")
                # 2. Упоминания (ссылки на другие профили)
                elif ('/status/' not in href) and \
                     (('twitter.com/' in href and not href.startswith(f'https://twitter.com/{username}/')) or \
                      ('x.com/' in href and not href.startswith(f'https://x.com/{username}/'))):
                    # Извлекаем имя пользователя из URL
                    match = re.search(r"(?:twitter|x)\.com/([^/?]+)", href)
                    if match:
                        mention = match.group(1)
                        # Дополнительная проверка, что это не служебные слова
                        if mention and mention not in ["search", "settings", "home", "explore", "notifications", "messages", "i"] and mention not in links["mentions"]:
                            links["mentions"].append(mention)
                            logger.debug(f"Добавлено упоминание: @{mention}")
                # 3. Медиа-ссылки (фото/видео на самом твиттере)
                elif ('pbs.twimg.com' in href or '/photo/' in href or '/video/' in href):
                    if href not in links["media_urls"]:
                        links["media_urls"].append(href)
                        logger.debug(f"Добавлена медиа-ссылка Twitter: {href}")
                # 4. Внешние ссылки (не twitter/x/t.co)
                elif not any(domain in href for domain in ['twitter.com', 'x.com', 't.co']):
                    if href not in links["external_urls"]:
                        links["external_urls"].append(href)
                        logger.debug(f"Добавлена внешняя ссылка: {href}")
                # 5. Сокращенные ссылки t.co
                elif href.startswith('https://t.co/'):
                    try:
                        # Используем HEAD запрос для получения реального URL без скачивания контента
                        response = requests.head(href, allow_redirects=True, timeout=5) # Allow redirects to get final URL
                        real_url = response.url # requests автоматически следует редиректам в HEAD
                        if real_url and real_url != href and not any(domain in real_url for domain in ['twitter.com', 'x.com']):
                             if real_url not in links["external_urls"]:
                                 links["external_urls"].append(real_url)
                                 logger.debug(f"Добавлена развернутая t.co ссылка: {real_url}")
                        elif real_url == href and href not in links["external_urls"]: # Если редиректа не было
                             links["external_urls"].append(href)
                             logger.debug(f"Добавлена t.co ссылка (без редиректа): {href}")

                    except requests.exceptions.RequestException as req_e:
                        logger.warning(f"Ошибка при разрешении t.co ссылки {href}: {req_e}")
                        # Добавляем исходную t.co ссылку в случае ошибки
                        if href not in links["external_urls"]:
                            links["external_urls"].append(href)
                            logger.debug(f"Добавлена t.co ссылка (ошибка разрешения): {href}")

            except StaleElementReferenceException:
                 logger.warning("Элемент ссылки устарел во время итерации, пропуск.")
                 continue
            except Exception as e:
                logger.warning(f"Ошибка при обработке отдельной ссылки: {e}")
                continue

        # Дополнительно ищем хэштеги и упоминания в тексте (если текст есть)
        try:
            tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
            tweet_text = tweet_text_element.text
            if tweet_text:
                # Хэштеги
                for hashtag in re.findall(r'#(\w+)', tweet_text):
                    if hashtag and hashtag not in links["hashtags"]:
                        links["hashtags"].append(hashtag)
                # Упоминания
                for mention in re.findall(r'@(\w+)', tweet_text):
                    # Исключаем упоминание самого себя, если username известен
                    if mention and mention not in links["mentions"] and (not username or mention.lower() != username.lower()):
                        links["mentions"].append(mention)
        except NoSuchElementException:
            logger.debug("Текстовый элемент твита не найден для доп. поиска ссылок.")
        except Exception as e:
            logger.warning(f"Ошибка при анализе текста твита на ссылки: {e}")

    except Exception as e:
        logger.error(f"Общая ошибка при извлечении ссылок: {e}")

    # Логируем итог
    total_links = sum(len(v) for v in links.values())
    logger.info(f"Извлечено ссылок для твита: {total_links} "
                f"(Ext: {len(links['external_urls'])}, Ment: {len(links['mentions'])}, "
                f"Hash: {len(links['hashtags'])}, Media: {len(links['media_urls'])})")

    return links


def save_links_to_db(connection, tweet_db_id, links):
    """
    Сохраняет ссылки из твита в базу данных. (Без изменений)
    """
    try:
        cursor = connection.cursor()
        # --- (Проверка и создание таблицы tweet_links, если нужно) ---
        try:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tweet_links (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tweet_id INT,
                url VARCHAR(1024),
                link_type ENUM('external', 'mention', 'hashtag', 'media'),
                inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tweet_id) REFERENCES tweets(id) ON DELETE CASCADE,
                INDEX idx_tweet_id (tweet_id),
                INDEX idx_link_type (link_type)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)
            connection.commit()
        except Error as e:
            # Игнорируем ошибку, если таблица уже существует
            if e.errno != 1050: # Error 1050: Table already exists
                 logger.error(f"Ошибка при проверке/создании таблицы tweet_links: {e}")
                 return False

        link_counts = {"external": 0, "mention": 0, "hashtag": 0, "media": 0}
        link_data_to_insert = []

        for url in links.get("external_urls", []):
            link_data_to_insert.append((tweet_db_id, url[:1024], 'external')) # Обрезаем URL, если он слишком длинный
            link_counts["external"] += 1
        for username in links.get("mentions", []):
            link_data_to_insert.append((tweet_db_id, username[:1024], 'mention'))
            link_counts["mention"] += 1
        for hashtag in links.get("hashtags", []):
            link_data_to_insert.append((tweet_db_id, hashtag[:1024], 'hashtag'))
            link_counts["hashtag"] += 1
        for media_url in links.get("media_urls", []):
            link_data_to_insert.append((tweet_db_id, media_url[:1024], 'media'))
            link_counts["media"] += 1

        if link_data_to_insert:
             sql = "INSERT INTO tweet_links (tweet_id, url, link_type) VALUES (%s, %s, %s)"
             cursor.executemany(sql, link_data_to_insert)
             connection.commit()
             logger.info(f"Сохранено в БД ссылок для твита {tweet_db_id}: {link_counts}")
             return True
        else:
             logger.debug(f"Нет ссылок для сохранения в БД для твита {tweet_db_id}.")
             return True # Считаем успешным, если ссылок просто не было

    except Error as e:
        logger.error(f"Ошибка при сохранении ссылок в БД для твита {tweet_db_id}: {e}")
        return False
    except Exception as e:
         logger.error(f"Неожиданная ошибка при сохранении ссылок в БД: {e}")
         return False


def is_tweet_truncated(tweet_element):
    """
    Улучшенное определение обрезанных твитов. (Без изменений)
    """
    try:
        # 1. Проверка по классам и стилям (менее надежно из-за частых изменений)
        # truncated_classes = ['r-1sf7l6p', 'r-1xyedr5'] # Пример, классы могут меняться
        # for class_name in truncated_classes:
        #     elements = tweet_element.find_elements(By.CSS_SELECTOR, f'[class*="{class_name}"]')
        #     if elements and any('…' in elem.text or '...' in elem.text for elem in elements):
        #          logger.debug(f"Обнаружен обрезанный твит (класс: {class_name})")
        #          return True

        # 2. Проверка по кнопкам "Show more" / "Показать ещё"
        xpath_indicators = [
            './/div[@role="button" and (contains(text(), "Show more") or contains(text(), "Показать ещё"))]',
            './/span[contains(text(), "Show more") or contains(text(), "Показать ещё")]'
        ]
        for xpath in xpath_indicators:
            if tweet_element.find_elements(By.XPATH, xpath):
                logger.debug(f"Обнаружен обрезанный твит (кнопка: {xpath})")
                return True

        # 3. Проверка по многоточию в конце текста
        try:
            tweet_text_elements = tweet_element.find_elements(By.CSS_SELECTOR, 'div[data-testid="tweetText"], div[lang]')
            for elem in tweet_text_elements:
                # Используем get_attribute('textContent') для получения полного текста, включая скрытый
                text_content = elem.get_attribute('textContent') or ""
                if text_content.strip().endswith('…') or text_content.strip().endswith('...'):
                    logger.debug("Обнаружен обрезанный твит (многоточие в конце textContent)")
                    return True
                # Дополнительная проверка видимого текста
                visible_text = elem.text.strip()
                if visible_text.endswith('…') or visible_text.endswith('...'):
                     logger.debug("Обнаружен обрезанный твит (многоточие в конце видимого текста)")
                     return True
        except StaleElementReferenceException:
             logger.warning("Элемент текста устарел при проверке на многоточие.")
             return False # Не можем быть уверены
        except NoSuchElementException:
            pass # Элемент текста не найден

        return False

    except Exception as e:
        logger.error(f"Ошибка при проверке обрезанности твита: {e}")
        return False # Возвращаем False при ошибке


def get_full_tweet_text(driver, tweet_url, max_attempts=2):
    """
    Улучшенное получение полного текста твита. Использует WebDriverWait.
    """
    full_text = ""
    current_window = driver.current_window_handle
    wait = WebDriverWait(driver, 15) # Ожидание для загрузки страницы твита

    try:
        clean_url = tweet_url.split('?')[0].split('#')[0]
        logger.info(f"Загружаем полную версию твита: {clean_url}")

        # Открываем новую вкладку
        driver.execute_script("window.open('');")
        # time.sleep(1) # Заменено
        wait.until(EC.number_of_windows_to_be(len(driver.window_handles)))
        driver.switch_to.window(driver.window_handles[-1])

        # Загружаем твит
        driver.get(clean_url)

        # Ждем загрузки основного элемента твита
        tweet_container_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        try:
            tweet_element = wait.until(EC.presence_of_element_located(tweet_container_locator))
            logger.info("Основной контейнер твита загружен (get_full_tweet_text).")
        except TimeoutException:
            logger.error(f"Таймаут при загрузке основного контейнера твита: {clean_url}")
            driver.close()
            driver.switch_to.window(current_window)
            return "" # Возвращаем пустую строку, если твит не загрузился

        # Пытаемся извлечь текст несколько раз, давая время на подгрузку
        for attempt in range(max_attempts):
             logger.debug(f"Попытка {attempt + 1}/{max_attempts} извлечения полного текста для {tweet_url}")
             current_text = ""
             try:
                 # Ждем видимости текстового блока
                 text_locator = (By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                 text_element = wait.until(EC.visibility_of_element_located(text_locator))
                 current_text = text_element.text # Берем видимый текст

                 # Проверяем, нет ли многоточия
                 if not (current_text.strip().endswith('…') or current_text.strip().endswith('...')):
                      full_text = current_text
                      logger.info(f"Полный текст извлечен (попытка {attempt + 1}): {len(full_text)} симв.")
                      break # Выходим, если текст полный
                 elif len(current_text) > len(full_text):
                      # Сохраняем самый длинный найденный текст, даже если он с многоточием
                      full_text = current_text

             except TimeoutException:
                  logger.warning(f"Текстовый блок не найден/не виден на попытке {attempt + 1}.")
             except Exception as e:
                  logger.error(f"Ошибка при извлечении текста на попытке {attempt + 1}: {e}")

             # Если текст все еще не полный, ждем немного перед следующей попыткой
             if attempt < max_attempts - 1 and (not full_text or full_text.strip().endswith('…') or full_text.strip().endswith('...')):
                  time.sleep(1.5) # Короткий sleep между попытками

        # Если после всех попыток текст все еще с многоточием, используем JS
        if full_text.strip().endswith('…') or full_text.strip().endswith('...'):
             logger.info("Текст все еще обрезан, пробуем извлечь через JavaScript...")
             try:
                 js_text = driver.execute_script("""
                     const tweetTextElement = document.querySelector('[data-testid="tweetText"]');
                     if (!tweetTextElement) return "";
                     // Собираем текст из всех span внутри, исключая иконки и т.п.
                     let fullText = '';
                     const spans = tweetTextElement.querySelectorAll('span');
                     for (const span of spans) {
                         // Проверяем, что span не содержит только иконку или картинку
                         if (!span.querySelector('img, svg, [role=\"link\"] > svg') && span.textContent) {
                              // Добавляем пробел, если текст не начинается/заканчивается пробелом и есть предыдущий текст
                             if (fullText && !span.textContent.startsWith(' ') && !fullText.endsWith(' ')) {
                                 fullText += ' ';
                             }
                             fullText += span.textContent;
                         }
                     }
                     // Добавляем текст из ссылок (упоминания, хэштеги)
                     const links = tweetTextElement.querySelectorAll('a');
                      for (const link of links) {
                          if (link.textContent && !fullText.includes(link.textContent)) {
                               if (fullText && !link.textContent.startsWith(' ') && !fullText.endsWith(' ')) {
                                   fullText += ' ';
                               }
                               fullText += link.textContent;
                          }
                      }

                     return fullText.trim();
                 """)
                 if js_text and len(js_text) > len(full_text):
                     full_text = js_text
                     logger.info(f"Извлечен текст через JavaScript: {len(full_text)} символов")
                 elif js_text:
                     logger.info(f"Текст из JS не длиннее текущего ({len(js_text)} vs {len(full_text)})")

             except Exception as e:
                 logger.error(f"Ошибка при извлечении текста через JavaScript: {e}")


        # Закрываем вкладку и возвращаемся
        driver.close()
        driver.switch_to.window(current_window)

        if not full_text:
            logger.warning(f"Не удалось извлечь полный текст твита: {tweet_url}")

        return full_text

    except Exception as e:
        logger.error(f"Общая ошибка при получении полного текста твита {tweet_url}: {e}", exc_info=True)
        # Пытаемся закрыть вкладку и вернуться в любом случае
        try:
            if driver.current_window_handle != current_window:
                driver.close()
            driver.switch_to.window(current_window)
        except Exception as close_e:
             logger.error(f"Ошибка при закрытии/переключении вкладки после ошибки: {close_e}")
        return "" # Возвращаем пустую строку при серьезной ошибке


def extract_full_tweet_text_from_html(driver, tweet_url):
    """
    Извлекает полный текст твита из HTML страницы, загруженной через Selenium.
    Использует WebDriverWait.
    """
    current_window = driver.current_window_handle
    full_text = ""
    wait = WebDriverWait(driver, 15) # Ожидание загрузки

    try:
        # Открываем новую вкладку
        driver.execute_script("window.open('');")
        wait.until(EC.number_of_windows_to_be(len(driver.window_handles)))
        driver.switch_to.window(driver.window_handles[-1])

        # Загружаем твит напрямую
        driver.get(tweet_url)

        # Ждем загрузки основного элемента твита
        tweet_container_locator = (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        try:
            wait.until(EC.presence_of_element_located(tweet_container_locator))
            logger.info("Основной контейнер твита загружен (extract_full_tweet_text_from_html).")
        except TimeoutException:
            logger.error(f"Таймаут при загрузке основного контейнера твита (HTML метод): {tweet_url}")
            driver.close()
            driver.switch_to.window(current_window)
            return ""

        # Даем немного времени на отрисовку JS
        time.sleep(1)

        # --- Методы извлечения текста ---
        # Метод 1: Продвинутый XPath
        try:
            text_parts = []
            # Ждем появления текстовых элементов
            text_elements_xpath = "//article[@data-testid='tweet']//div[@lang]//span[not(ancestor::a) and not(child::img) and not(child::svg)]"
            text_elements = wait.until(EC.presence_of_all_elements_located((By.XPATH, text_elements_xpath)))

            for elem in text_elements:
                try:
                    text = elem.text.strip()
                    if text: # Добавляем только непустые
                        text_parts.append(text)
                except StaleElementReferenceException:
                    continue # Пропускаем устаревшие элементы
            if text_parts:
                full_text = ' '.join(text_parts)
                logger.info(f"Извлечен текст через XPath: {len(full_text)} симв.")
        except TimeoutException:
            logger.warning("Не удалось найти текстовые элементы через XPath.")
        except Exception as e:
            logger.error(f"Ошибка при извлечении текста методом XPath: {e}")

        # Метод 2: CSS селектор для основного блока текста (если XPath не сработал)
        if not full_text:
            try:
                text_locator_css = 'div[data-testid="tweetText"]'
                text_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, text_locator_css)))
                full_text = text_element.text
                logger.info(f"Извлечен текст через CSS [data-testid='tweetText']: {len(full_text)} симв.")
            except TimeoutException:
                logger.warning("Не удалось найти текстовый блок через CSS [data-testid='tweetText'].")
            except Exception as e:
                 logger.error(f"Ошибка при извлечении текста методом CSS: {e}")


        # Метод 3: JavaScript (как резервный или для проверки)
        try:
            js_text = driver.execute_script("""
                const article = document.querySelector('article[data-testid="tweet"]');
                if (!article) return "";
                const textElement = article.querySelector('div[data-testid="tweetText"]');
                return textElement ? textElement.textContent.trim() : "";
            """)
            if js_text and len(js_text) > len(full_text):
                full_text = js_text
                logger.info(f"Извлечен текст через JavaScript: {len(full_text)} симв.")
            elif js_text:
                 logger.debug(f"Текст из JS не длиннее текущего ({len(js_text)} vs {len(full_text)})")

        except Exception as e:
            logger.error(f"Ошибка при извлечении текста через JavaScript: {e}")

        # Закрываем вкладку и возвращаемся
        driver.close()
        driver.switch_to.window(current_window)

        return full_text

    except Exception as e:
        logger.error(f"Общая ошибка при извлечении текста твита из HTML: {e}", exc_info=True)
        try:
            if driver.current_window_handle != current_window:
                driver.close()
            driver.switch_to.window(current_window)
        except Exception as close_e:
             logger.error(f"Ошибка при закрытии/переключении вкладки после ошибки (HTML метод): {close_e}")
        return ""

