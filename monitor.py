#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для мониторинга работы парсера и сбора статистики
"""

import time
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import mysql.connector
from mysql.connector import Error

logger = logging.getLogger(__name__)


class TwitterScraperMonitor:
    """Класс для мониторинга работы парсера Twitter"""

    def __init__(self, db_config=None):
        self.db_config = db_config
        self.session_stats = {
            'start_time': time.time(),
            'accounts_processed': 0,
            'tweets_collected': 0,
            'errors_count': 0,
            'successful_accounts': 0,
            'failed_accounts': 0,
            'average_tweets_per_account': 0,
            'processing_times': [],
            'error_types': Counter(),
            'tweets_by_hour': defaultdict(int)
        }

    def log_account_start(self, username):
        """Логирование начала обработки аккаунта"""
        self.current_account = {
            'username': username,
            'start_time': time.time(),
            'tweets_found': 0,
            'errors': []
        }
        logger.info(f"📊 Начата обработка @{username}")

    def log_account_finish(self, username, tweets_count, success=True):
        """Логирование завершения обработки аккаунта"""
        if hasattr(self, 'current_account'):
            processing_time = time.time() - self.current_account['start_time']
            self.session_stats['processing_times'].append(processing_time)

            if success:
                self.session_stats['successful_accounts'] += 1
                self.session_stats['tweets_collected'] += tweets_count
                logger.info(f"✅ @{username}: {tweets_count} твитов за {processing_time:.1f}с")
            else:
                self.session_stats['failed_accounts'] += 1
                logger.warning(f"❌ @{username}: обработка неудачна")

            self.session_stats['accounts_processed'] += 1
            self._update_averages()

    def log_tweet_collected(self, tweet_data):
        """Логирование сбора твита"""
        try:
            # Анализируем время публикации твита
            if 'created_at' in tweet_data:
                tweet_time = datetime.fromisoformat(tweet_data['created_at'].replace('Z', '+00:00'))
                hour_key = tweet_time.strftime('%Y-%m-%d %H:00')
                self.session_stats['tweets_by_hour'][hour_key] += 1

            logger.debug(f"📝 Собран твит: {tweet_data.get('url', 'unknown')}")
        except Exception as e:
            logger.error(f"Ошибка логирования твита: {e}")

    def log_error(self, error_type, error_message, username=None):
        """Логирование ошибки"""
        self.session_stats['errors_count'] += 1
        self.session_stats['error_types'][error_type] += 1

        if hasattr(self, 'current_account') and username:
            self.current_account['errors'].append({
                'type': error_type,
                'message': str(error_message),
                'timestamp': time.time()
            })

        logger.error(f"🚨 {error_type}: {error_message}")

    def _update_averages(self):
        """Обновление средних значений"""
        if self.session_stats['successful_accounts'] > 0:
            self.session_stats['average_tweets_per_account'] = (
                    self.session_stats['tweets_collected'] /
                    self.session_stats['successful_accounts']
            )

    def get_current_stats(self):
        """Получение текущей статистики"""
        session_duration = time.time() - self.session_stats['start_time']

        stats = self.session_stats.copy()
        stats.update({
            'session_duration_minutes': session_duration / 60,
            'tweets_per_minute': self.session_stats['tweets_collected'] / max(session_duration / 60, 1),
            'success_rate': (
                    self.session_stats['successful_accounts'] /
                    max(self.session_stats['accounts_processed'], 1) * 100
            ),
            'average_processing_time': (
                    sum(self.session_stats['processing_times']) /
                    max(len(self.session_stats['processing_times']), 1)
            )
        })

        return stats

    def print_progress_report(self):
        """Вывод отчета о прогрессе"""
        stats = self.get_current_stats()

        print("\n" + "=" * 50)
        print("📊 ОТЧЕТ О ПРОГРЕССЕ")
        print("=" * 50)
        print(f"⏱️  Время работы: {stats['session_duration_minutes']:.1f} мин")
        print(f"👥 Обработано аккаунтов: {stats['accounts_processed']}")
        print(f"✅ Успешно: {stats['successful_accounts']}")
        print(f"❌ Неудачно: {stats['failed_accounts']}")
        print(f"📝 Собрано твитов: {stats['tweets_collected']}")
        print(f"📈 Средне на аккаунт: {stats['average_tweets_per_account']:.1f}")
        print(f"⚡ Твитов в минуту: {stats['tweets_per_minute']:.1f}")
        print(f"🎯 Успешность: {stats['success_rate']:.1f}%")

        if stats['errors_count'] > 0:
            print(f"\n🚨 Ошибки ({stats['errors_count']} всего):")
            for error_type, count in stats['error_types'].most_common(5):
                print(f"   • {error_type}: {count}")

        print("=" * 50)

    def save_session_report(self, filename=None):
        """Сохранение отчета о сессии"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"scraper_report_{timestamp}.json"

        try:
            stats = self.get_current_stats()

            # Конвертируем Counter в обычный dict для JSON
            stats['error_types'] = dict(stats['error_types'])
            stats['tweets_by_hour'] = dict(stats['tweets_by_hour'])

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"💾 Отчет сохранен: {filename}")
            return filename

        except Exception as e:
            logger.error(f"Ошибка сохранения отчета: {e}")
            return None

    def get_database_stats(self):
        """Получение статистики из базы данных"""
        if not self.db_config:
            return None

        try:
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor()

            # Общее количество твитов
            cursor.execute("SELECT COUNT(*) FROM tweets")
            total_tweets = cursor.fetchone()[0]

            # Твиты за последние 24 часа
            cursor.execute("""
                           SELECT COUNT(*)
                           FROM tweets
                           WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                           """)
            recent_tweets = cursor.fetchone()[0]

            # Твиты за последнюю неделю
            cursor.execute("""
                           SELECT COUNT(*)
                           FROM tweets
                           WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                           """)
            week_tweets = cursor.fetchone()[0]

            # Топ доменов в URL'ах
            cursor.execute("""
                           SELECT SUBSTRING_INDEX(SUBSTRING_INDEX(url, '/', 3), '/', -1) as domain,
                    COUNT(*) as count
                           FROM tweets
                           GROUP BY domain
                           ORDER BY count DESC
                               LIMIT 10
                           """)
            top_domains = cursor.fetchall()

            cursor.close()
            connection.close()

            return {
                'total_tweets': total_tweets,
                'recent_tweets_24h': recent_tweets,
                'recent_tweets_7d': week_tweets,
                'top_domains': top_domains
            }

        except Error as e:
            logger.error(f"Ошибка получения статистики БД: {e}")
            return None

    def print_database_stats(self):
        """Вывод статистики базы данных"""
        db_stats = self.get_database_stats()

        if db_stats:
            print("\n" + "=" * 50)
            print("🗄️ СТАТИСТИКА БАЗЫ ДАННЫХ")
            print("=" * 50)
            print(f"📊 Всего твитов: {db_stats['total_tweets']:,}")
            print(f"🕐 За 24 часа: {db_stats['recent_tweets_24h']:,}")
            print(f"📅 За 7 дней: {db_stats['recent_tweets_7d']:,}")

            if db_stats['top_domains']:
                print(f"\n🌐 Топ доменов:")
                for domain, count in db_stats['top_domains'][:5]:
                    print(f"   • {domain}: {count:,}")

            print("=" * 50)
        else:
            print("❌ Не удалось получить статистику БД")


def create_monitor(db_config=None):
    """Фабричная функция для создания монитора"""
    return TwitterScraperMonitor(db_config)