#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы с базой данных MySQL
Содержит функции для подключения, сохранения твитов и получения статистики
"""

import logging
import datetime
from typing import Optional, Dict, Any, List
import mysql.connector
from mysql.connector import Error

logger = logging.getLogger(__name__)


class TwitterDatabase:
    """Класс для работы с базой данных Twitter"""

    def __init__(self, config: Dict[str, Any]):
        """
        Инициализация подключения к базе данных

        Args:
            config: Словарь с параметрами подключения к MySQL
        """
        self.config = config
        self.connection = None
        self._connect()

    def _connect(self) -> bool:
        """Установка соединения с базой данных"""
        try:
            self.connection = mysql.connector.connect(**self.config)
            if self.connection.is_connected():
                logger.info("Успешное подключение к MySQL")
                self._ensure_table_exists()
                return True
        except Error as e:
            logger.error(f"Ошибка подключения к MySQL: {e}")
            self.connection = None
            return False
        return False

    def _ensure_table_exists(self):
        """Создание таблицы tweets если она не существует"""
        try:
            cursor = self.connection.cursor()
            create_table_query = """
                                 CREATE TABLE IF NOT EXISTS tweets \
                                 ( \
                                     id \
                                     INT \
                                     AUTO_INCREMENT \
                                     PRIMARY \
                                     KEY, \
                                     url \
                                     VARCHAR \
                                 ( \
                                     500 \
                                 ) COLLATE utf8mb4_unicode_ci NOT NULL UNIQUE,
                                     tweet_text TEXT COLLATE utf8mb4_unicode_ci NOT NULL,
                                     created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                                     isGrok TINYINT \
                                 ( \
                                     1 \
                                 ) DEFAULT 0,
                                     inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                     INDEX idx_created_at \
                                 ( \
                                     created_at \
                                 ),
                                     INDEX idx_url \
                                 ( \
                                     url \
                                 )
                                     ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci; \
                                 """

            cursor.execute(create_table_query)
            self.connection.commit()
            cursor.close()
            logger.info("Таблица tweets проверена/создана")

        except Error as e:
            logger.error(f"Ошибка при создании таблицы: {e}")

    def is_connected(self) -> bool:
        """Проверка состояния соединения"""
        return self.connection and self.connection.is_connected()

    def reconnect(self) -> bool:
        """Переподключение к базе данных"""
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass

        return self._connect()

    def parse_twitter_date(self, date_str: str) -> Optional[datetime.datetime]:
        """
        Парсинг даты Twitter в различных форматах

        Args:
            date_str: Строка с датой в формате Twitter

        Returns:
            datetime объект или None в случае ошибки
        """
        if not date_str:
            return None

        try:
            # Формат ISO с Z (UTC)
            if "Z" in date_str:
                return datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))

            # Формат ISO с timezone
            if "T" in date_str and ('+' in date_str or '-' in date_str.split('T')[1]):
                return datetime.datetime.fromisoformat(date_str)

            # Формат с миллисекундами
            if "T" in date_str and "." in date_str and date_str.endswith("Z"):
                date_without_ms = date_str.split(".")[0]
                dt = datetime.datetime.fromisoformat(date_without_ms)
                return dt.replace(tzinfo=datetime.timezone.utc)

        except Exception as e:
            logger.warning(f"Ошибка парсинга даты '{date_str}': {e}")

        # Возвращаем текущее время в случае ошибки
        return datetime.datetime.now(datetime.timezone.utc)

    def save_tweet(self, tweet_data: Dict[str, Any]) -> bool:
        """
        Сохранение твита в базу данных

        Args:
            tweet_data: Словарь с данными твита (url, text, created_at)

        Returns:
            True если сохранение успешно, False в противном случае
        """
        if not self.is_connected():
            logger.warning("Нет подключения к базе данных")
            return False

        try:
            cursor = self.connection.cursor()

            # Проверяем, существует ли твит
            cursor.execute("SELECT id FROM tweets WHERE url = %s", (tweet_data['url'],))
            existing_tweet = cursor.fetchone()

            if existing_tweet:
                logger.debug(f"Твит уже существует в БД: {tweet_data['url']}")
                cursor.close()
                return True

            # Преобразуем дату
            created_at = self.parse_twitter_date(tweet_data['created_at'])
            created_at_str = created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else None

            # Вставляем новый твит
            insert_query = """
                           INSERT INTO tweets (url, tweet_text, created_at, isGrok)
                           VALUES (%s, %s, %s, %s) \
                           """

            tweet_values = (
                tweet_data['url'],
                tweet_data['text'],
                created_at_str,
                tweet_data.get('isGrok', 0)
            )

            cursor.execute(insert_query, tweet_values)
            self.connection.commit()

            tweet_id = cursor.lastrowid
            cursor.close()

            logger.info(f"Твит сохранен в БД с ID {tweet_id}: {tweet_data['url']}")
            return True

        except Error as e:
            logger.error(f"Ошибка сохранения твита в БД: {e}")
            # Пытаемся восстановить соединение
            if "MySQL server has gone away" in str(e):
                logger.info("Попытка переподключения к БД...")
                if self.reconnect():
                    return self.save_tweet(tweet_data)  # Рекурсивный вызов после переподключения
            return False

        except Exception as e:
            logger.error(f"Неожиданная ошибка при сохранении твита: {e}")
            return False

    def get_tweets_count(self, hours: int = 24) -> int:
        """
        Получение количества твитов за указанный период

        Args:
            hours: Количество часов назад от текущего времени

        Returns:
            Количество твитов
        """
        if not self.is_connected():
            return 0

        try:
            cursor = self.connection.cursor()

            query = """
                    SELECT COUNT(*) \
                    FROM tweets
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR) \
                    """

            cursor.execute(query, (hours,))
            count = cursor.fetchone()[0]
            cursor.close()

            return count

        except Error as e:
            logger.error(f"Ошибка получения количества твитов: {e}")
            return 0

    def get_database_stats(self) -> Dict[str, Any]:
        """
        Получение статистики базы данных

        Returns:
            Словарь со статистическими данными
        """
        if not self.is_connected():
            return {"error": "Нет подключения к БД"}

        try:
            cursor = self.connection.cursor()
            stats = {}

            # Общее количество твитов
            cursor.execute("SELECT COUNT(*) FROM tweets")
            stats['total_tweets'] = cursor.fetchone()[0]

            # Твиты за последние 24 часа
            cursor.execute("""
                           SELECT COUNT(*)
                           FROM tweets
                           WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                           """)
            stats['tweets_24h'] = cursor.fetchone()[0]

            # Твиты за последнюю неделю
            cursor.execute("""
                           SELECT COUNT(*)
                           FROM tweets
                           WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                           """)
            stats['tweets_7d'] = cursor.fetchone()[0]

            # Самый старый твит
            cursor.execute("""
                           SELECT created_at
                           FROM tweets
                           WHERE created_at IS NOT NULL
                           ORDER BY created_at ASC LIMIT 1
                           """)
            oldest_result = cursor.fetchone()
            stats['oldest_tweet'] = oldest_result[0] if oldest_result else None

            # Самый новый твит
            cursor.execute("""
                           SELECT created_at
                           FROM tweets
                           WHERE created_at IS NOT NULL
                           ORDER BY created_at DESC LIMIT 1
                           """)
            newest_result = cursor.fetchone()
            stats['newest_tweet'] = newest_result[0] if newest_result else None

            # Топ доменов в URL'ах
            cursor.execute("""
                           SELECT SUBSTRING_INDEX(SUBSTRING_INDEX(url, '/', 3), '/', -1) as domain,
                    COUNT(*) as count
                           FROM tweets
                           GROUP BY domain
                           ORDER BY count DESC
                               LIMIT 5
                           """)
            stats['top_domains'] = cursor.fetchall()

            cursor.close()

            return stats

        except Error as e:
            logger.error(f"Ошибка получения статистики БД: {e}")
            return {"error": str(e)}

    def get_recent_tweets(self, limit: int = 10, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Получение последних твитов

        Args:
            limit: Максимальное количество твитов
            hours: Период в часах

        Returns:
            Список словарей с данными твитов
        """
        if not self.is_connected():
            return []

        try:
            cursor = self.connection.cursor(dictionary=True)

            query = """
                    SELECT id, url, tweet_text, created_at, isGrok, inserted_at
                    FROM tweets
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                    ORDER BY created_at DESC
                        LIMIT %s \
                    """

            cursor.execute(query, (hours, limit))
            tweets = cursor.fetchall()
            cursor.close()

            return tweets

        except Error as e:
            logger.error(f"Ошибка получения последних твитов: {e}")
            return []

    def clean_old_tweets(self, days: int = 30) -> int:
        """
        Удаление старых твитов

        Args:
            days: Количество дней для хранения твитов

        Returns:
            Количество удаленных записей
        """
        if not self.is_connected():
            return 0

        try:
            cursor = self.connection.cursor()

            # Сначала подсчитываем количество записей для удаления
            count_query = """
                          SELECT COUNT(*) \
                          FROM tweets
                          WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY) \
                          """
            cursor.execute(count_query, (days,))
            count_to_delete = cursor.fetchone()[0]

            if count_to_delete == 0:
                cursor.close()
                return 0

            # Удаляем старые записи
            delete_query = """
                           DELETE \
                           FROM tweets
                           WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY) \
                           """
            cursor.execute(delete_query, (days,))
            self.connection.commit()

            deleted_count = cursor.rowcount
            cursor.close()

            logger.info(f"Удалено {deleted_count} старых твитов (старше {days} дней)")
            return deleted_count

        except Error as e:
            logger.error(f"Ошибка при удалении старых твитов: {e}")
            return 0

    def check_duplicate_url(self, url: str) -> bool:
        """
        Проверка существования твита с указанным URL

        Args:
            url: URL твита для проверки

        Returns:
            True если твит уже существует, False в противном случае
        """
        if not self.is_connected():
            return False

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id FROM tweets WHERE url = %s", (url,))
            result = cursor.fetchone()
            cursor.close()

            return result is not None

        except Error as e:
            logger.error(f"Ошибка проверки дубликата URL: {e}")
            return False

    def close(self):
        """Закрытие соединения с базой данных"""
        if self.connection and self.connection.is_connected():
            try:
                self.connection.close()
                logger.info("Соединение с базой данных закрыто")
            except Exception as e:
                logger.error(f"Ошибка при закрытии соединения с БД: {e}")

    def __enter__(self):
        """Поддержка context manager"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое закрытие при выходе из контекста"""
        self.close()


def create_database_connection(config: Dict[str, Any]) -> Optional[TwitterDatabase]:
    """
    Фабричная функция для создания подключения к базе данных

    Args:
        config: Конфигурация подключения к MySQL

    Returns:
        Экземпляр TwitterDatabase или None в случае ошибки
    """
    try:
        db = TwitterDatabase(config)
        if db.is_connected():
            return db
        else:
            return None
    except Exception as e:
        logger.error(f"Ошибка создания подключения к БД: {e}")
        return None