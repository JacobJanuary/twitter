#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы со ссылками и анализа содержимого твитов.
Отвечает за извлечение ссылок разных типов и их обработку.
"""

import os
import re
import logging
import requests
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from mysql.connector import Error
import time

# Настройка логирования
logger = logging.getLogger('twitter_scraper.links')

# Константы
LINKS_CACHE_DIR = "twitter_links_cache"
os.makedirs(LINKS_CACHE_DIR, exist_ok=True)


def extract_all_links_from_tweet(tweet_element, username, expand_first=True):
    """
    Улучшенное извлечение всех ссылок из твита

    Args:
        tweet_element: Элемент твита Selenium WebDriver
        username: Имя пользователя, твит которого обрабатывается (для фильтрации)
        expand_first: Сначала раскрыть пост, если он длинный

    Returns:
        dict: Словарь с категориями ссылок
    """
    links = {
        "external_urls": [],  # Внешние ссылки
        "mentions": [],  # @упоминания
        "hashtags": [],  # #хэштеги
        "media_urls": []  # Ссылки на медиа
    }

    try:
        # Если нужно раскрыть длинный пост, делаем это сначала
        if expand_first:
            try:
                # Ищем кнопку "Show more"
                show_more_buttons = tweet_element.find_elements(
                    By.XPATH,
                    './/div[@role="button" and contains(text(), "Show more")]'
                )

                if not show_more_buttons:
                    show_more_buttons = tweet_element.find_elements(
                        By.XPATH,
                        './/span[contains(text(), "Show more")]'
                    )

                # Если нашли кнопку, нажимаем на неё
                if show_more_buttons:
                    logger.info("Найдена кнопка 'Show more', раскрываем пост перед извлечением ссылок")
                    for button in show_more_buttons:
                        try:
                            button.click()
                            time.sleep(1)  # Ждем раскрытия текста
                        except:
                            try:
                                # Используем JavaScript для клика
                                tweet_element.parent.execute_script("arguments[0].click();", button)
                                time.sleep(1)
                            except Exception as e:
                                logger.warning(f"Не удалось кликнуть на 'Show more': {e}")
            except Exception as e:
                logger.warning(f"Ошибка при попытке раскрыть пост: {e}")

        # Получаем все ссылки в твите
        link_elements = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href]')

        # Фильтры для исключения ложных ссылок
        excluded_texts = [
            "тыс.", "млн", "апр.", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек",
            "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
            "hours", "mins", "час", "мин", "дн", "days", "week"
        ]

        # Паттерн для проверки внутренних URL
        internal_url_pattern = f"twitter.com/{username}|x.com/{username}"

        for link in link_elements:
            try:
                href = link.get_attribute('href')
                if not href:
                    continue

                # Получаем текст ссылки
                link_text = link.text.strip()

                # Пропускаем элементы с метриками и датами
                if any(exc in link_text for exc in excluded_texts):
                    logger.debug(f"Пропускаем ссылку с исключенным текстом: {link_text}")
                    continue

                # Пропускаем внутренние ссылки профиля пользователя
                if re.search(internal_url_pattern, href, re.IGNORECASE):
                    # Исключение для статусов (твитов) - их нужно считать
                    if "/status/" in href:
                        # Если это не analytics, likes, retweets и подобное
                        if not any(x in href for x in ["/analytics", "/likes", "/retweets", "/quotes", "/bookmarks"]):
                            # Здесь можно обработать ссылки на другие твиты как отдельную категорию
                            logger.debug(f"Обнаружена ссылка на твит: {href}")
                    else:
                        logger.debug(f"Пропускаем внутреннюю ссылку профиля: {href}")
                        continue

                # Обрабатываем ссылки по категориям
                if href.startswith('http') and ('twitter.com/hashtag/' in href or 'x.com/hashtag/' in href):
                    # Хэштег
                    hashtag = href.split('/hashtag/')[-1].split('?')[0]
                    if hashtag and hashtag not in links["hashtags"]:
                        links["hashtags"].append(hashtag)
                        logger.debug(f"Добавлен хэштег: {hashtag}")

                elif href.startswith('http') and (('/status/' not in href) and
                                                  (('twitter.com/' in href and not href.startswith(
                                                      f'https://twitter.com/{username}')) or
                                                   ('x.com/' in href and not href.startswith(
                                                       f'https://x.com/{username}')))):
                    # Упоминание пользователя
                    if 'twitter.com/' in href:
                        username_match = re.search(r'twitter\.com/([^/]+)', href)
                    else:
                        username_match = re.search(r'x\.com/([^/]+)', href)

                    if username_match:
                        mention = username_match.group(1)
                        if mention and mention not in links["mentions"] and mention != username:
                            links["mentions"].append(mention)
                            logger.debug(f"Добавлено упоминание: @{mention}")

                elif 'pbs.twimg.com' in href or '/photo/' in href or '/video/' in href:
                    # Медиа-контент
                    if href not in links["media_urls"]:
                        links["media_urls"].append(href)
                        logger.debug(f"Добавлена медиа-ссылка: {href}")

                elif href.startswith('http') and not any(x in href for x in ['twitter.com', 'x.com', 't.co']):
                    # Надежно определяем внешние ссылки - исключаем все twitter/x домены
                    if href not in links["external_urls"]:
                        links["external_urls"].append(href)
                        logger.debug(f"Добавлена внешняя ссылка: {href}")

                elif href.startswith('https://t.co/'):
                    # Для сокращенных t.co ссылок пытаемся получить настоящий URL
                    try:
                        # Используем requests с отключенным перенаправлением, чтобы получить заголовок Location
                        response = requests.head(href, allow_redirects=False, timeout=5)
                        if response.status_code in (301, 302) and 'Location' in response.headers:
                            real_url = response.headers['Location']
                            if real_url and real_url not in links["external_urls"]:
                                links["external_urls"].append(real_url)
                                logger.debug(f"Добавлена развернутая t.co ссылка: {real_url}")
                        else:
                            # Если не получилось получить настоящий URL, добавляем t.co ссылку
                            if href not in links["external_urls"]:
                                links["external_urls"].append(href)
                                logger.debug(f"Добавлена t.co ссылка: {href}")
                    except:
                        # В случае ошибки добавляем исходную ссылку
                        if href not in links["external_urls"]:
                            links["external_urls"].append(href)
                            logger.debug(f"Добавлена t.co ссылка (без разрешения): {href}")

            except Exception as e:
                logger.warning(f"Ошибка при обработке отдельной ссылки: {e}")
                continue

        # Дополнительно ищем хэштеги и упоминания в тексте
        try:
            tweet_text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
            if tweet_text_element:
                tweet_text = tweet_text_element.text

                # Хэштеги в тексте
                hashtag_pattern = r'#(\w+)'
                for hashtag in re.findall(hashtag_pattern, tweet_text):
                    if hashtag and hashtag not in links["hashtags"]:
                        links["hashtags"].append(hashtag)

                # Упоминания в тексте
                mention_pattern = r'@(\w+)'
                for mention in re.findall(mention_pattern, tweet_text):
                    if mention and mention not in links["mentions"] and mention != username:
                        links["mentions"].append(mention)
        except Exception as e:
            logger.warning(f"Ошибка при анализе текста твита: {e}")

    except Exception as e:
        logger.error(f"Общая ошибка при извлечении ссылок: {e}")

    # Выводим статистику по найденным ссылкам
    total_links = sum(len(links[key]) for key in links)
    logger.info(f"Всего извлечено ссылок: {total_links}")
    for key, values in links.items():
        logger.info(f"  - {key}: {len(values)}")

    return links


def save_links_to_db(connection, tweet_db_id, links):
    """
    Сохраняет ссылки из твита в базу данных

    Args:
        connection: Соединение с базой данных MySQL
        tweet_db_id: ID твита в базе данных
        links: Словарь с ссылками из твита

    Returns:
        bool: True, если ссылки успешно сохранены
    """
    try:
        cursor = connection.cursor()

        # Проверяем, существует ли таблица tweet_links
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
            logger.error(f"Ошибка при создании таблицы tweet_links: {e}")
            return False

        # Добавляем каждую ссылку в базу данных
        link_counts = {
            "external": 0,
            "mention": 0,
            "hashtag": 0,
            "media": 0
        }

        # Внешние ссылки
        for url in links.get("external_urls", []):
            cursor.execute("""
                INSERT INTO tweet_links (tweet_id, url, link_type)
                VALUES (%s, %s, %s)
                """, (tweet_db_id, url, 'external'))
            link_counts["external"] += 1

        # Упоминания
        for username in links.get("mentions", []):
            cursor.execute("""
                INSERT INTO tweet_links (tweet_id, url, link_type)
                VALUES (%s, %s, %s)
                """, (tweet_db_id, username, 'mention'))
            link_counts["mention"] += 1

        # Хэштеги
        for hashtag in links.get("hashtags", []):
            cursor.execute("""
                INSERT INTO tweet_links (tweet_id, url, link_type)
                VALUES (%s, %s, %s)
                """, (tweet_db_id, hashtag, 'hashtag'))
            link_counts["hashtag"] += 1

        # Медиа ссылки
        for media_url in links.get("media_urls", []):
            cursor.execute("""
                INSERT INTO tweet_links (tweet_id, url, link_type)
                VALUES (%s, %s, %s)
                """, (tweet_db_id, media_url, 'media'))
            link_counts["media"] += 1

        connection.commit()

        # Логируем результаты
        logger.info(f"Сохранено в БД: {link_counts['external']} внешних ссылок, " +
                    f"{link_counts['mention']} упоминаний, {link_counts['hashtag']} хэштегов, " +
                    f"{link_counts['media']} медиа-ссылок")

        return True

    except Error as e:
        logger.error(f"Ошибка при сохранении ссылок в БД: {e}")
        return False


def is_tweet_truncated(tweet_element):
    """
    Улучшенное определение обрезанных твитов
    """
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
                    if '…' in elem.text or '...' in elem.text:
                        logger.info(f"Обнаружен обрезанный твит (класс: {class_name})")
                        return True

        # 2. Проверка по кнопкам "Show more"
        xpath_indicators = [
            './/div[@role="button" and contains(text(), "Show more")]',
            './/div[@role="button" and contains(text(), "Read more")]',
            './/span[contains(text(), "Show more")]',
            './/span[contains(text(), "Read more")]'
        ]

        for xpath in xpath_indicators:
            elements = tweet_element.find_elements(By.XPATH, xpath)
            if elements:
                logger.info(f"Обнаружен обрезанный твит (кнопка: {xpath})")
                return True

        # 3. Проверка по многоточию в конце текста
        try:
            tweet_text_elements = tweet_element.find_elements(By.CSS_SELECTOR, 'div[data-testid="tweetText"], [lang]')
            for elem in tweet_text_elements:
                text = elem.text.strip()
                if text.endswith('…') or text.endswith('...'):
                    logger.info("Обнаружен обрезанный твит (многоточие в конце)")
                    return True
        except:
            pass

        # 4. Проверка URL на параметры
        try:
            for link in tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]'):
                href = link.get_attribute('href')
                if href and ('/status/' in href) and ('s=20' in href or 's=19' in href):
                    logger.info(f"Обнаружен обрезанный твит (параметр s=20 в URL)")
                    return True
        except:
            pass

        return False

    except Exception as e:
        logger.error(f"Ошибка при проверке обрезанности твита: {e}")
        return False


def get_full_tweet_text(driver, tweet_url, max_attempts=3):
    """
    Улучшенное получение полного текста твита с надежным методом раскрытия контента
    """
    full_text = ""
    current_window = driver.current_window_handle

    try:
        # Очищаем URL от параметров запроса
        clean_url = tweet_url.split('?')[0].split('#')[0]
        logger.info(f"Загружаем полную версию твита: {clean_url}")

        # Открываем новую вкладку
        driver.execute_script("window.open('');")
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

        # НОВЫЙ МЕТОД: Принудительное раскрытие текста
        # Twitter часто загружает сжатый текст, даже если страница открыта напрямую
        for attempt in range(3):
            # 1. Попробуем найти и кликнуть по элементам "Show more"
            try:
                # Все возможные селекторы кнопок "Show more"
                show_more_selectors = [
                    '//div[@role="button" and contains(., "Show more")]',
                    '//span[contains(., "Show more")]',
                    '//div[@data-testid="tweet"]//div[@role="button" and contains(., "more")]',
                    '//div[contains(@class, "css-1dbjc4n") and contains(., "…")]',
                    '//div[contains(@class, "r-1sg46qm")]',  # Класс для сокращенного текста
                ]

                for selector in show_more_selectors:
                    buttons = driver.find_elements(By.XPATH, selector)
                    if buttons:
                        for button in buttons:
                            try:
                                # Прокрутим к кнопке
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(1)

                                # Пробуем разные способы клика
                                try:
                                    button.click()
                                except:
                                    driver.execute_script("arguments[0].click();", button)

                                # ВАЖНО: дополнительное ожидание после клика
                                time.sleep(3)
                                logger.info("Успешно раскрыт твит через кнопку Show more")
                                break
                            except Exception as e:
                                logger.debug(f"Не удалось кликнуть на кнопку: {e}")
            except Exception as e:
                logger.debug(f"Ошибка при поиске кнопок Show more: {e}")

            # 2. Дополнительный метод: иногда клик по самому твиту помогает раскрыть его
            try:
                tweet_containers = driver.find_elements(By.CSS_SELECTOR,
                                                        'article[data-testid="tweet"], div[data-testid="tweetText"]')
                if tweet_containers:
                    # Кликаем по твиту
                    driver.execute_script("arguments[0].click();", tweet_containers[0])
                    time.sleep(2)
            except:
                pass

            # 3. Извлекаем текст после попыток раскрытия
            all_text_elements = []

            # Пробуем все возможные селекторы для текста
            selectors = [
                'div[data-testid="tweetText"]',
                'article[data-testid="tweet"] div[lang]',
                'div[lang][dir="auto"]',
                'div[role="group"] div[dir="auto"]'
            ]

            for selector in selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                all_text_elements.extend(elements)

            # Собираем весь текст из найденных элементов
            current_text = ""
            for elem in all_text_elements:
                elem_text = elem.text.strip()
                # Если текст не пустой и не дублирует существующий
                if elem_text and elem_text not in current_text:
                    if current_text:
                        current_text += " "
                    current_text += elem_text

            # ВАЖНО: проверка наличия многоточия в конце
            if current_text and not current_text.endswith('…') and not current_text.endswith('...'):
                # Вероятно полный текст найден
                if len(current_text) > len(full_text):
                    full_text = current_text
                    logger.info(f"Найден полный текст длиной {len(full_text)} символов")
                break
            elif len(current_text) > len(full_text):
                # Если текст длиннее, но все еще с многоточием, сохраняем его и пробуем снова
                full_text = current_text
                logger.info(f"Найден частично раскрытый текст ({len(full_text)} символов), пробуем еще раз")

            # Дополнительно прокручиваем страницу и ждем раскрытия
            driver.execute_script("window.scrollTo(0, 100);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

        # 4. НОВЫЙ МЕТОД: Извлечение текста через JavaScript (может обойти обрезание)
        try:
            js_text = driver.execute_script("""
                // Попытка получить полный текст через DOM структуру
                const tweetTextElements = document.querySelectorAll('[data-testid="tweetText"] span');
                let fullText = '';
                for (const element of tweetTextElements) {
                    if (element.textContent && !element.querySelector('img, svg') && !element.parentElement.querySelector('img, svg')) {
                        fullText += element.textContent + ' ';
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

        # Возвращаемся к основной вкладке
        try:
            driver.close()
            driver.switch_to.window(current_window)
        except:
            pass

        return full_text or ""


def extract_full_tweet_text_from_html(driver, tweet_url):
    """
    Извлекает полный текст твита из HTML страницы
    """
    current_window = driver.current_window_handle
    full_text = ""

    try:
        # Открываем новую вкладку
        driver.execute_script("window.open('');")
        time.sleep(1)
        driver.switch_to.window(driver.window_handles[-1])

        # Загружаем твит напрямую
        driver.get(tweet_url)
        time.sleep(5)  # Увеличенное время ожидания загрузки

        # Вариант 1: Используем продвинутый XPath для поиска всех текстовых элементов внутри твита
        try:
            text_parts = []
            # Находим основные элементы твита с текстом
            text_elements = driver.find_elements(By.XPATH,
                                                 "//article//div[@lang]//span[not(child::img)]")

            for elem in text_elements:
                text = elem.text.strip()
                if text and len(text) > 1:
                    # Исключаем имена пользователей и хэштеги
                    if not (text.startswith('@') or text.startswith('#')):
                        text_parts.append(text)

            if text_parts:
                # Соединяем текст и удаляем возможные дублирования
                full_text = ' '.join(text_parts)
        except Exception as e:
            print(f"Ошибка при извлечении текста методом 1: {e}")

        # Если первый метод не сработал, пробуем другой
        if not full_text:
            try:
                # Ищем элементы с языковым атрибутом - обычно это текст твита
                lang_elements = driver.find_elements(By.CSS_SELECTOR, "[lang][dir='auto']")
                for elem in lang_elements:
                    if elem.text and len(elem.text) > len(full_text):
                        full_text = elem.text
            except Exception as e:
                print(f"Ошибка при извлечении текста методом 2: {e}")

        # Добавляем метод для сохранения структуры упоминаний и хэштегов
        if not full_text or "@" not in full_text:
            try:
                # Получаем HTML и ищем структурированный текст с упоминаниями
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')
                tweet_elem = soup.select_one('article[data-testid="tweet"]')

                if tweet_elem:
                    # Ищем все ссылки с потенциальными упоминаниями
                    mentions = []
                    for a in tweet_elem.select('a[role="link"]'):
                        href = a.get('href', '')
                        if href and '/status/' not in href:
                            if '/twitter.com/' in href or '/x.com/' in href:
                                username = href.split('/')[-1].split('?')[0]
                                if username and len(username) > 1:
                                    mentions.append(f"@{username}")

                    # Если нашли упоминания, добавляем их к тексту
                    if mentions:
                        mention_text = " ".join(mentions)
                        if full_text:
                            full_text = f"{full_text} {mention_text}"
                        else:
                            full_text = mention_text
            except Exception as e:
                print(f"Ошибка при извлечении упоминаний: {e}")

        # Третий метод - используем JavaScript для извлечения текста
        if not full_text or len(full_text) < 50:
            try:
                js_text = driver.execute_script("""
                    // Ищем основной текст твита
                    const article = document.querySelector('article[data-testid="tweet"]');
                    if (!article) return "";

                    // Собираем все текстовые элементы
                    const textElements = article.querySelectorAll('div[lang] > span');
                    let text = '';
                    for (const el of textElements) {
                        if (el.textContent && !el.querySelector('img, svg')) {
                            text += el.textContent + ' ';
                        }
                    }

                    // Дополнительно собираем все упоминания
                    const mentions = [];
                    article.querySelectorAll('a[role="link"]').forEach(a => {
                        const href = a.getAttribute('href');
                        if (href && !href.includes('/status/')) {
                            if (href.includes('twitter.com/') || href.includes('x.com/')) {
                                const parts = href.split('/');
                                const username = parts[parts.length - 1].split('?')[0];
                                if (username) mentions.push('@' + username);
                            }
                        }
                    });

                    // Объединяем основной текст с упоминаниями
                    return text.trim() + ' ' + mentions.join(' ');
                """)

                if js_text and len(js_text) > len(full_text):
                    full_text = js_text
            except Exception as e:
                print(f"Ошибка при извлечении текста через JavaScript: {e}")

        # Закрываем вкладку и возвращаемся
        driver.close()
        driver.switch_to.window(current_window)

        return full_text

    except Exception as e:
        print(f"Общая ошибка при извлечении текста твита: {e}")
        try:
            driver.close()
            driver.switch_to.window(current_window)
        except:
            pass
        return full_text