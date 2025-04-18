#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы со статьями из Twitter.
Отвечает за извлечение статей, их анализ и сохранение в базу данных.
"""

import os
import re
import json
import time
import logging
import hashlib
import requests
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from mysql.connector import Error
from urllib.parse import urlparse

# Настройка логирования
logger = logging.getLogger('twitter_scraper.articles')

# Константы
ARTICLE_CACHE_DIR = "twitter_article_cache"
os.makedirs(ARTICLE_CACHE_DIR, exist_ok=True)

# Список известных доменов для статей
ARTICLE_DOMAINS = [
    'medium.com', 'substack.com', 'mirror.xyz', 'blog.', '.blog.',
    'article.', '.article.', 'news.', '.news.', 'post.', '.post.',
    'nytimes.com', 'washingtonpost.com', 'theverge.com', 'techcrunch.com',
    'wired.com', 'bloomberg.com', 'forbes.com', 'cnn.com', 'bbc.com',
    'reuters.com', 'hackernoon.com', 'coindesk.com', 'cointelegraph.com',
    'decrypt.co', 'theblock.co', 'thedefiant.io', 'cryptoslate.com'
]


def is_article_url(url, extended_check=True):
    """
    Определяет, является ли URL ссылкой на статью с использованием расширенных критериев

    Args:
        url: URL для проверки
        extended_check: Выполнять ли расширенную проверку с HTTP-запросом

    Returns:
        bool: True, если URL является ссылкой на статью
    """
    # Исключаем ссылки на медиафайлы
    media_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mp3', '.wav', '.pdf']

    # Проверяем, не является ли это ссылкой на медиафайл
    if any(url.lower().endswith(ext) for ext in media_extensions):
        return False

    # Проверяем по известным доменам статей
    for domain in ARTICLE_DOMAINS:
        if domain in url.lower():
            logger.info(f"URL определен как статья по домену {domain}: {url}")
            return True

    # Проверяем по ключевым словам в URL
    article_keywords = ['article', 'blog', 'post', 'news', 'story', 'opinion', 'analysis']
    if any(keyword in url.lower() for keyword in article_keywords):
        logger.info(f"URL определен как статья по ключевому слову: {url}")
        return True

    # Расширенная проверка - переходим по ссылке и анализируем содержимое
    if extended_check:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Проверка метаданных Open Graph
                og_type = soup.find('meta', property='og:type')
                if og_type and og_type.get('content', '') in ['article', 'blog', 'news']:
                    logger.info(f"URL определен как статья по og:type: {url}")
                    return True

                # Проверка наличия Schema.org разметки типа Article
                article_schema = soup.find('script', {'type': 'application/ld+json'})
                if article_schema:
                    try:
                        schema_data = json.loads(article_schema.string)
                        if isinstance(schema_data, dict) and schema_data.get('@type') in ['Article', 'NewsArticle',
                                                                                          'BlogPosting']:
                            logger.info(f"URL определен как статья по schema.org: {url}")
                            return True
                    except:
                        pass

                # Проверка типичных элементов статьи
                article_elements = soup.select('article, .article, .post, .blog-post, .story')
                if article_elements:
                    logger.info(f"URL определен как статья по HTML элементам: {url}")
                    return True

                # Проверка на плотность текста - если страница содержит много абзацев, это может быть статья
                paragraphs = soup.find_all('p')
                if len(paragraphs) > 5 and sum(len(p.text.strip()) for p in paragraphs) > 1000:
                    logger.info(f"URL определен как статья по количеству текста: {url}")
                    return True

        except Exception as e:
            logger.warning(f"Ошибка при расширенной проверке URL {url}: {e}")

    return False


def extract_article_urls_from_tweet(tweet_element):
    """
    Улучшенное извлечение URL статей из твита

    Args:
        tweet_element: Элемент твита Selenium WebDriver

    Returns:
        list: Список URL статей
    """
    article_urls = []

    try:
        # Получаем все ссылки из твита
        try:
            # Импортируем функцию из модуля links_utils
            from twitter_scraper_links_utils import extract_all_links_from_tweet
            all_links = extract_all_links_from_tweet(tweet_element, "")  # Передаем пустую строку вместо username
        except ImportError:
            # Если не удалось импортировать, используем упрощенный вариант
            logger.warning("Не удалось импортировать extract_all_links_from_tweet, используем резервный метод")
            all_links = {"external_urls": []}
            for link in tweet_element.find_elements(By.CSS_SELECTOR, 'a[href]'):
                href = link.get_attribute('href')
                if href and href.startswith(('http://', 'https://')) and not any(
                        domain in href for domain in ['twitter.com', 'x.com', 't.co']):
                    all_links["external_urls"].append(href)

        external_urls = all_links.get("external_urls", [])

        # Проверяем каждую внешнюю ссылку
        for url in external_urls:
            # Предварительная проверка без перехода по ссылке
            if is_article_url(url, extended_check=False):
                article_urls.append(url)
                logger.info(f"Найдена ссылка на статью (по быстрой проверке): {url}")

        # Если не нашли статей по быстрой проверке, используем расширенную
        if not article_urls and external_urls:
            for url in external_urls:
                if is_article_url(url, extended_check=True):
                    article_urls.append(url)
                    logger.info(f"Найдена ссылка на статью (по расширенной проверке): {url}")

    except Exception as e:
        logger.error(f"Ошибка при извлечении URL статей: {e}")

    return article_urls


def parse_full_article(driver, article_url, username, cache_file=None):
    """
    Улучшенный парсинг полной статьи по URL с более надежным определением элементов

    Args:
        driver: Экземпляр Selenium WebDriver
        article_url: URL статьи
        username: Имя пользователя Twitter, связанное со статьей
        cache_file: Путь к файлу кэша

    Returns:
        dict: Словарь с данными статьи
    """
    article_data = {
        "url": article_url,
        "title": "",
        "content": "",
        "author": "",
        "published_date": "",
        "source_domain": "",
        "is_cached": False,
        "links": []  # Ссылки внутри статьи
    }

    # Извлекаем домен источника
    try:
        parsed_url = urlparse(article_url)
        article_data["source_domain"] = parsed_url.netloc
    except:
        pass

    # Проверяем кэш, если указан путь к файлу кэша
    if cache_file and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_article = json.load(f)
                logger.info(f"Используем кэшированные данные статьи: {article_url}")
                article_data.update(cached_article)
                article_data["is_cached"] = True
                return article_data
        except Exception as e:
            logger.error(f"Ошибка при чтении кэша статьи: {e}")

    # Если нет кэша или не удалось его прочитать, парсим статью
    try:
        # Открываем новую вкладку для загрузки статьи
        current_window = driver.current_window_handle

        # Открываем новую вкладку
        driver.execute_script("window.open('');")
        time.sleep(1)
        driver.switch_to.window(driver.window_handles[-1])

        logger.info(f"Загружаем статью по URL: {article_url}")
        driver.get(article_url)

        # Ждем загрузки страницы (ищем h1 или title)
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'h1, title, article, .article, .post, .entry-content'))
            )
            logger.info("Страница статьи загружена")
        except TimeoutException:
            logger.warning("Таймаут при ожидании загрузки статьи, пытаемся продолжить")
            # Дополнительная задержка
            time.sleep(15)

        # Прокручиваем страницу для загрузки всего контента
        for i in range(5):
            driver.execute_script(f"window.scrollTo(0, {i * 1000});")
            time.sleep(1)

        # Сохраняем HTML для анализа через BeautifulSoup
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')

        # Проверяем наличие Schema.org разметки
        schema_data = None
        schema_script = soup.find('script', {'type': 'application/ld+json'})
        if schema_script:
            try:
                schema_text = schema_script.string
                schema_data = json.loads(schema_text)
                logger.info("Найдена Schema.org разметка")
            except:
                schema_data = None

        # Извлекаем заголовок (приоритет Schema.org, затем тегам h1)
        if schema_data:
            if isinstance(schema_data, dict):
                article_data["title"] = schema_data.get('headline', '')
            elif isinstance(schema_data, list) and len(schema_data) > 0:
                for item in schema_data:
                    if isinstance(item, dict) and item.get('@type') in ['Article', 'NewsArticle', 'BlogPosting']:
                        article_data["title"] = item.get('headline', '')
                        break

        # Если заголовок не найден в Schema.org, ищем в h1
        if not article_data["title"]:
            title_element = soup.find('h1')
            if title_element:
                article_data["title"] = title_element.text.strip()
            else:
                # Ищем title в мета-данных
                title_meta = soup.find('meta', property='og:title') or soup.find('meta', attrs={'name': 'title'})
                if title_meta:
                    article_data["title"] = title_meta.get('content', '').strip()
                else:
                    # Используем title из заголовка страницы
                    article_data["title"] = soup.title.text.strip() if soup.title else ""

        logger.info(f"Извлечен заголовок статьи: {article_data['title']}")

        # Извлекаем дату публикации (сначала из Schema.org)
        if schema_data:
            if isinstance(schema_data, dict):
                article_data["published_date"] = schema_data.get('datePublished', '')
            elif isinstance(schema_data, list) and len(schema_data) > 0:
                for item in schema_data:
                    if isinstance(item, dict) and 'datePublished' in item:
                        article_data["published_date"] = item.get('datePublished', '')
                        break

        # Если дата не найдена в Schema.org, ищем в метаданных
        if not article_data["published_date"]:
            date_meta = (
                    soup.find('meta', property='article:published_time') or
                    soup.find('meta', attrs={'name': 'pubdate'}) or
                    soup.find('meta', attrs={'name': 'publishdate'}) or
                    soup.find('meta', property='og:published_time') or
                    soup.find('meta', attrs={'name': 'date'})
            )

            if date_meta:
                article_data["published_date"] = date_meta.get('content', '')
            else:
                # Ищем время/дату в тексте по шаблонам
                date_patterns = [
                    r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}',  # 25 December 2023
                    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},\s+\d{4}',  # December 25, 2023
                    r'\d{4}-\d{2}-\d{2}',  # 2023-12-25
                    r'\d{2}/\d{2}/\d{4}'  # 25/12/2023
                ]

                for pattern in date_patterns:
                    date_match = re.search(pattern, html_content)
                    if date_match:
                        article_data["published_date"] = date_match.group(0)
                        break

        # Извлекаем автора (сначала из Schema.org)
        if schema_data:
            if isinstance(schema_data, dict):
                author_data = schema_data.get('author', {})
                if isinstance(author_data, dict):
                    article_data["author"] = author_data.get('name', '')
                elif isinstance(author_data, str):
                    article_data["author"] = author_data
            elif isinstance(schema_data, list) and len(schema_data) > 0:
                for item in schema_data:
                    if isinstance(item, dict) and 'author' in item:
                        author_data = item.get('author', {})
                        if isinstance(author_data, dict):
                            article_data["author"] = author_data.get('name', '')
                        elif isinstance(author_data, str):
                            article_data["author"] = author_data
                        break

        # Если автор не найден в Schema.org, ищем в метаданных
        if not article_data["author"]:
            author_meta = (
                    soup.find('meta', property='article:author') or
                    soup.find('meta', attrs={'name': 'author'}) or
                    soup.find('meta', property='og:author')
            )

            if author_meta:
                article_data["author"] = author_meta.get('content', '')
            else:
                # Ищем автора в тексте (распространенные шаблоны)
                author_elements = soup.select('.author, .byline, [rel="author"], [itemprop="author"]')
                if author_elements:
                    article_data["author"] = author_elements[0].text.strip()

        # Основная логика извлечения контента статьи
        article_content = ""

        # Если есть Schema.org, проверяем наличие полного текста там
        if schema_data:
            if isinstance(schema_data, dict):
                if 'articleBody' in schema_data:
                    article_content = schema_data.get('articleBody', '')
            elif isinstance(schema_data, list) and len(schema_data) > 0:
                for item in schema_data:
                    if isinstance(item, dict) and 'articleBody' in item:
                        article_content = item.get('articleBody', '')
                        break

        # Если контент не найден в Schema.org или слишком короткий, ищем в HTML
        if len(article_content) < 200:
            # Список приоритетных селекторов для контента
            content_selectors = [
                'article', '[itemprop="articleBody"]', '.post-content', '.article-content',
                '.entry-content', '.post-body', '.article-body', '.story-body',
                '.main-content', '[property="schema:text"]', '.post', '#content',
                '.blog-post-content', '.story__content', '.page-content', '.content__body',
                '.js-post-body', '.rich-text', '.blog-content', '.article__content'
            ]

            # Пробуем найти контент по селекторам
            for selector in content_selectors:
                content_element = soup.select_one(selector)
                if content_element:
                    # Извлекаем все параграфы
                    paragraphs = content_element.find_all('p')
                    content_text = '\n\n'.join([p.text.strip() for p in paragraphs if p.text.strip()])

                    # Если нашли достаточно текста, используем этот контент
                    if len(content_text) > 200:
                        article_content = content_text
                        break

            # Если не удалось найти контент через селекторы, собираем все параграфы
            if len(article_content) < 200:
                all_paragraphs = soup.find_all('p')
                paragraphs_text = [p.text.strip() for p in all_paragraphs if len(p.text.strip()) > 40]

                # Отфильтровываем параграфы, которые похожи на комментарии, навигацию и т.д.
                filtered_paragraphs = []
                for p in paragraphs_text:
                    # Игнорируем короткие параграфы и типичные элементы навигации/интерфейса
                    if len(p) < 40:
                        continue
                    if re.search(r'comment|share|cookie|privacy|newsletter|subscribe|sign up|log in', p.lower()):
                        continue
                    filtered_paragraphs.append(p)

                article_content = '\n\n'.join(filtered_paragraphs)

        article_data["content"] = article_content

        # Извлекаем ссылки из статьи
        article_links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if href and href.startswith(('http://', 'https://')):
                # Отфильтровываем навигационные и служебные ссылки
                if not re.search(r'(comment|share|cookie|privacy|login|signup|subscribe)', href, re.IGNORECASE):
                    if href not in article_links and article_url not in href:
                        article_links.append(href)

        article_data["links"] = article_links[:20]  # Ограничиваем количество ссылок

        # Закрываем вкладку и возвращаемся к основной
        driver.close()
        driver.switch_to.window(current_window)

        # Сохраняем в кэш, если указан файл кэша
        if cache_file:
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(article_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Статья сохранена в кэш: {cache_file}")
            except Exception as e:
                logger.error(f"Ошибка при сохранении статьи в кэш: {e}")

        logger.info(
            f"Статья успешно обработана: {article_url}, длина контента: {len(article_data['content'])} символов")
        return article_data

    except Exception as e:
        logger.error(f"Ошибка при парсинге статьи {article_url}: {e}")
        import traceback
        traceback.print_exc()

        # В случае ошибки пытаемся закрыть вкладку и вернуться к основной
        try:
            driver.close()
            driver.switch_to.window(current_window)
        except:
            pass

        # Возвращаем неполные данные
        return article_data


def save_article_to_db(connection, tweet_id, article_data):
    """
    Сохраняет статью в базу данных с поддержкой ссылок

    Args:
        connection: Соединение с базой данных MySQL
        tweet_id: ID твита в базе данных
        article_data: Словарь с данными статьи

    Returns:
        int: ID статьи в базе данных или None в случае ошибки
    """
    try:
        cursor = connection.cursor()

        # Проверяем, существуют ли необходимые таблицы
        try:
            # Создаем таблицу для статей
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tweet_id INT,
                article_url VARCHAR(1024),
                title TEXT,
                author VARCHAR(255),
                published_date VARCHAR(255),
                source_domain VARCHAR(255),
                content LONGTEXT,
                inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tweet_id) REFERENCES tweets(id) ON DELETE CASCADE,
                INDEX idx_tweet_id (tweet_id),
                INDEX idx_source_domain (source_domain)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            # Создаем таблицу для ссылок из статей
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS article_links (
                id INT AUTO_INCREMENT PRIMARY KEY,
                article_id INT,
                url VARCHAR(1024),
                inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
                INDEX idx_article_id (article_id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            connection.commit()
        except Error as e:
            logger.error(f"Ошибка при создании таблиц для статей: {e}")
            return None

        # Проверяем, существует ли статья (по URL и ID твита)
        cursor.execute("""
            SELECT id FROM articles 
            WHERE tweet_id = %s AND article_url = %s
            """, (tweet_id, article_data["url"]))

        result = cursor.fetchone()
        article_id = None

        if result:
            # Обновляем существующую статью
            article_id = result[0]
            cursor.execute("""
                UPDATE articles 
                SET title = %s, author = %s, published_date = %s, 
                    source_domain = %s, content = %s
                WHERE id = %s
                """,
                           (
                               article_data["title"],
                               article_data["author"],
                               article_data["published_date"],
                               article_data["source_domain"],
                               article_data["content"],
                               article_id
                           )
                           )

            logger.info(f"Обновлена существующая статья с ID: {article_id}")
        else:
            # Создаем новую запись
            cursor.execute("""
                INSERT INTO articles 
                (tweet_id, article_url, title, author, published_date, source_domain, content)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                           (
                               tweet_id,
                               article_data["url"],
                               article_data["title"],
                               article_data["author"],
                               article_data["published_date"],
                               article_data["source_domain"],
                               article_data["content"]
                           )
                           )

            article_id = cursor.lastrowid
            logger.info(f"Создана новая запись статьи с ID: {article_id}")

        # Сохраняем ссылки из статьи
        if article_id and "links" in article_data and article_data["links"]:
            # Сначала удаляем существующие ссылки для этой статьи
            cursor.execute("DELETE FROM article_links WHERE article_id = %s", (article_id,))

            # Добавляем новые ссылки
            for link in article_data["links"]:
                cursor.execute("""
                    INSERT INTO article_links (article_id, url)
                    VALUES (%s, %s)
                    """, (article_id, link))

            logger.info(f"Сохранено {len(article_data['links'])} ссылок из статьи")

        connection.commit()
        return article_id

    except Error as e:
        logger.error(f"Ошибка при сохранении статьи в базу данных: {e}")
        return None


def process_article_from_tweet(driver, tweet_element, tweet_db_id, username, db_connection=None, use_cache=True):
    """
    Обрабатывает статью из твита

    Args:
        driver: Экземпляр Selenium WebDriver
        tweet_element: Элемент твита Selenium WebDriver
        tweet_db_id: ID твита в базе данных
        username: Имя пользователя Twitter
        db_connection: Соединение с базой данных MySQL
        use_cache: Использовать ли кэш

    Returns:
        dict: Словарь с данными статьи или None, если статья не найдена
    """
    # Извлекаем URL статей из твита
    article_urls = extract_article_urls_from_tweet(tweet_element)

    if not article_urls:
        logger.info("Статей в твите не найдено")
        return None

    # Обрабатываем первую найденную статью
    for url in article_urls:
        logger.info(f"Обнаружена ссылка на статью: {url}")

        # Создаем имя кэш-файла на основе URL
        cache_file = None
        if use_cache:
            url_hash = hashlib.md5(url.encode()).hexdigest()
            cache_file = os.path.join(ARTICLE_CACHE_DIR, f"{url_hash}_article.json")

        # Парсим статью
        article_data = parse_full_article(driver, url, username, cache_file)

        # Сохраняем в базу данных, если установлено соединение
        if db_connection and tweet_db_id and article_data and article_data.get("title"):
            logger.info(f"Сохранение статьи в базу данных...")
            article_id = save_article_to_db(db_connection, tweet_db_id, article_data)
            if article_id:
                logger.info(f"Статья сохранена в БД с ID: {article_id}")

        return article_data

    logger.info("Подходящих статей в твите не найдено")
    return None