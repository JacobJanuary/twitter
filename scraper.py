#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Основной модуль парсера Twitter
Объединяет все компоненты: браузер, базу данных, имитацию поведения
"""

import os
import logging
import time
import random
import datetime
from typing import Optional, Dict, Any, List
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException
)

# Импорт наших модулей
from human_behavior import HumanBehaviorSimulator
from database import TwitterDatabase, create_database_connection
from browser import TwitterBrowser, create_browser

logger = logging.getLogger(__name__)


class LightweightTwitterScraper:
    """Основной класс парсера Twitter"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Инициализация парсера

        Args:
            config: Конфигурация парсера
        """
        # Конфигурация по умолчанию
        self.config = config or {
            'mysql': {
                'host': '217.154.19.224',
                'database': 'twitter_data',
                'user': 'elcrypto',
                'password': 'LohNeMamont@!21',
                'port': 3306,
                'charset': 'utf8mb4',
                'use_unicode': True
            },
            'scraper': {
                'max_tweets_per_account': 15,
                'time_filter_hours': 24,
                'max_scroll_attempts': 25,
                'max_consecutive_no_new': 5
            },
            'browser': {
                'chrome_profile_path': None,
                'user_agents': [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
                ]
            },
            'behavior': {
                'delays': {
                    'between_actions': (1, 3),
                    'reading_pause': (2, 8),
                    'inter_account_pause': (10, 30),
                    'long_break': (60, 180),
                    'page_load_wait': (3, 6),
                    'scroll_pause': (2, 5),
                },
                'probabilities': {
                    'extra_long_pause': 0.3,
                    'visit_homepage': 0.2,
                    'simulate_interest': 0.15,
                }
            }
        }

        # Компоненты парсера
        self.browser = None
        self.database = None
        self.human_behavior = None

        # Статистика
        self.stats = {
            'accounts_processed': 0,
            'tweets_collected': 0,
            'successful_accounts': 0,
            'failed_accounts': 0,
            'start_time': None
        }

    def initialize(self, chrome_profile_path: Optional[str] = None) -> bool:
        """
        Инициализация всех компонентов парсера

        Args:
            chrome_profile_path: Путь к профилю Chrome

        Returns:
            True если инициализация успешна
        """
        logger.info("=== ИНИЦИАЛИЗАЦИЯ ПАРСЕРА ===")

        # Инициализация базы данных
        logger.info("Подключение к базе данных...")
        self.database = create_database_connection(self.config['mysql'])
        if not self.database:
            logger.error("Не удалось подключиться к базе данных")
            answer = input("Продолжить без сохранения в БД? (да/нет): ")
            if answer.lower() not in ['да', 'yes', 'y', 'д']:
                return False
        else:
            logger.info("✅ База данных подключена")

        # Инициализация браузера
        logger.info("Инициализация браузера...")

        # Безопасное получение конфигурации браузера
        browser_config = self.config.get('browser', {}).copy()
        if chrome_profile_path:
            browser_config['chrome_profile_path'] = chrome_profile_path

        # Добавляем базовые настройки если они отсутствуют
        if 'user_agents' not in browser_config:
            browser_config['user_agents'] = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            ]

        self.browser = create_browser(browser_config, chrome_profile_path)
        if not self.browser:
            logger.error("Не удалось инициализировать браузер")
            return False

        logger.info("✅ Браузер инициализирован")

        # Инициализация симулятора поведения
        behavior_config = self.config.get('behavior', {
            'delays': {
                'between_actions': (1, 3),
                'reading_pause': (2, 8),
                'page_load_wait': (3, 6),
            }
        })

        self.human_behavior = HumanBehaviorSimulator(
            self.browser.driver,
            behavior_config
        )
        logger.info("✅ Симулятор поведения инициализирован")

        # Разогрев браузера
        logger.info("Разогрев браузера...")
        try:
            self.browser.warmup_browsing()
        except Exception as e:
            logger.warning(f"Ошибка разогрева браузера: {e}")

        return True

    def authenticate(self) -> bool:
        """
        Авторизация в Twitter

        Returns:
            True если авторизация успешна
        """
        logger.info("=== АВТОРИЗАЦИЯ В TWITTER ===")

        auth_success = self.browser.manual_auth(self.human_behavior)
        if auth_success:
            logger.info("✅ Авторизация успешна")
        else:
            logger.warning("⚠️ Авторизация не подтверждена, но продолжаем")

        # Дополнительная проверка после авторизации
        self.human_behavior.random_delay('page_load_wait')

        return auth_success

    def load_accounts_from_file(self, filename: str = "influencer_twitter.txt") -> List[str]:
        """
        Загрузка списка аккаунтов из файла

        Args:
            filename: Имя файла со списком аккаунтов

        Returns:
            Список имен пользователей
        """
        accounts = []
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Извлекаем username из URL или берем как есть
                username = None
                if line.startswith('http'):
                    try:
                        username = line.split('/')[-1].split('?')[0]
                    except Exception:
                        logger.warning(f"Не удалось извлечь username из URL в строке {line_num}: {line}")
                        continue
                else:
                    username = line.lstrip('@')

                if username and username not in accounts:
                    accounts.append(username)

            logger.info(f"Загружено {len(accounts)} аккаунтов из {filename}")
            return accounts

        except FileNotFoundError:
            logger.error(f"Файл {filename} не найден")
            return []
        except Exception as e:
            logger.error(f"Ошибка загрузки аккаунтов из {filename}: {e}")
            return []

    def extract_tweet_data(self, tweet_element) -> Optional[Dict[str, Any]]:
        """
        Извлечение данных из элемента твита

        Args:
            tweet_element: Selenium элемент твита

        Returns:
            Словарь с данными твита или None
        """
        try:
            # Имитируем наведение мыши на твит
            try:
                ActionChains(self.browser.driver).move_to_element(tweet_element).perform()
                self.human_behavior.random_delay('between_actions')
            except Exception:
                pass

            # Получаем URL твита
            tweet_url = ""
            tweet_links = tweet_element.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
            for link in tweet_links:
                href = link.get_attribute('href')
                if href and "/status/" in href:
                    tweet_url = href.split("?")[0]  # Убираем параметры
                    break

            if not tweet_url:
                return None

            # Пытаемся раскрыть твит если он обрезан
            self._expand_tweet_content(tweet_element)

            # Извлекаем текст твита
            tweet_text = ""
            try:
                text_element = tweet_element.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                tweet_text = text_element.text

                # Имитируем чтение текста
                if tweet_text:
                    self.human_behavior.simulate_reading_pause(len(tweet_text))

            except NoSuchElementException:
                # Альтернативный способ извлечения текста
                try:
                    lang_elements = tweet_element.find_elements(By.CSS_SELECTOR, '[lang][dir="auto"]')
                    if lang_elements:
                        tweet_text = lang_elements[0].text
                except Exception:
                    pass

            # Извлекаем дату создания
            created_at = ""
            try:
                time_element = tweet_element.find_element(By.TAG_NAME, 'time')
                created_at = time_element.get_attribute('datetime')
            except NoSuchElementException:
                logger.warning(f"Не удалось найти дату для твита: {tweet_url}")

            if not tweet_text or not created_at:
                return None

            # Иногда имитируем дополнительный интерес к твиту
            behavior_config = self.config.get('behavior', {})
            probabilities = behavior_config.get('probabilities', {})
            interest_prob = probabilities.get('simulate_interest', 0.15)

            if random.random() < interest_prob:
                self.human_behavior.simulate_user_interest()

            return {
                'url': tweet_url,
                'text': tweet_text,
                'created_at': created_at
            }

        except Exception as e:
            logger.error(f"Ошибка извлечения данных твита: {e}")
            return None

    def _expand_tweet_content(self, tweet_element):
        """
        Раскрытие полного содержимого твита если он обрезан

        Args:
            tweet_element: Selenium элемент твита
        """
        try:
            # Ищем кнопки "Show more" или "Показать ещё"
            show_more_selectors = [
                ".//div[@role='button' and (contains(., 'Show more') or contains(., 'Показать ещё'))]",
                ".//span[contains(., 'Show more') or contains(., 'Показать ещё')]"
            ]

            for selector in show_more_selectors:
                try:
                    buttons = tweet_element.find_elements(By.XPATH, selector)
                    if buttons:
                        for button in buttons:
                            try:
                                # Естественный клик через симулятор поведения
                                if hasattr(self.human_behavior, 'natural_click'):
                                    self.human_behavior.natural_click(button)
                                else:
                                    # Fallback на обычный клик
                                    ActionChains(self.browser.driver).move_to_element(button).click().perform()
                                    self.human_behavior.random_delay('between_actions')

                                logger.debug("Твит раскрыт")
                                return True
                            except Exception:
                                continue
                except Exception:
                    continue

            return False
        except Exception as e:
            logger.debug(f"Ошибка при раскрытии твита: {e}")
            return False

    def get_tweets_from_user(self, username: str) -> List[Dict[str, Any]]:
        """
        Получение твитов от конкретного пользователя

        Args:
            username: Имя пользователя Twitter

        Returns:
            Список словарей с данными твитов
        """
        logger.info(f"📥 Начинаем сбор твитов от @{username}")

        # Параметры из конфигурации с безопасным получением
        scraper_config = self.config.get('scraper', {})
        max_tweets = scraper_config.get('max_tweets_per_account', 15)
        time_filter_hours = scraper_config.get('time_filter_hours', 24)
        max_scroll_attempts = scraper_config.get('max_scroll_attempts', 25)
        max_consecutive_no_new = scraper_config.get('max_consecutive_no_new', 5)

        collected_tweets = []

        try:
            # Переходим на страницу пользователя
            if not self.browser.navigate_to_profile(username, self.human_behavior):
                logger.error(f"Не удалось открыть профиль @{username}")
                return []

            # Проверяем доступность аккаунта
            if not self.browser.check_account_availability(username):
                logger.error(f"Аккаунт @{username} недоступен")
                return []

            # Настройки для сбора
            processed_urls = set()
            scroll_attempts = 0
            consecutive_no_new_tweets = 0

            # Время фильтрации
            cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=time_filter_hours)

            logger.info(f"🎯 Цель: макс. {max_tweets} твитов за последние {time_filter_hours}ч")

            while (scroll_attempts < max_scroll_attempts and
                   len(collected_tweets) < max_tweets and
                   consecutive_no_new_tweets < max_consecutive_no_new):

                scroll_attempts += 1
                initial_count = len(collected_tweets)

                # Проверяем состояние сессии
                self.human_behavior.session_health_check()

                # Находим твиты на текущей странице
                tweet_elements = self.browser.find_tweets_on_page()

                # Имитируем естественный просмотр страницы
                self.human_behavior.simulate_reading_pause(100)
                self.human_behavior.random_mouse_movement()

                for tweet_element in tweet_elements:
                    try:
                        tweet_data = self.extract_tweet_data(tweet_element)

                        if not tweet_data or tweet_data['url'] in processed_urls:
                            continue

                        processed_urls.add(tweet_data['url'])

                        # Проверяем временной фильтр
                        tweet_time = self._parse_twitter_date(tweet_data['created_at'])
                        if tweet_time and tweet_time >= cutoff_time:
                            collected_tweets.append(tweet_data)

                            # Сохраняем в БД
                            if self.database:
                                self.database.save_tweet(tweet_data)

                            logger.info(f"📝 Твит [{len(collected_tweets)}/{max_tweets}]: {tweet_data['text'][:50]}...")

                            if len(collected_tweets) >= max_tweets:
                                logger.info(f"🎯 Достигнут лимит твитов: {max_tweets}")
                                break
                        else:
                            logger.debug(f"⏰ Старый твит пропущен: {tweet_time}")

                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        logger.error(f"Ошибка обработки твита: {e}")
                        continue

                # Проверяем прогресс
                new_tweets_count = len(collected_tweets) - initial_count
                if new_tweets_count == 0:
                    consecutive_no_new_tweets += 1
                    logger.info(
                        f"⏸️ Нет новых твитов в итерации {scroll_attempts} (подряд: {consecutive_no_new_tweets})")
                else:
                    consecutive_no_new_tweets = 0
                    logger.info(f"✅ Добавлено {new_tweets_count} твитов в итерации {scroll_attempts}")

                # Если достигли лимита, прерываем
                if len(collected_tweets) >= max_tweets:
                    break

                # Естественный скроллинг
                if scroll_attempts < max_scroll_attempts:
                    logger.debug(f"📜 Скроллинг #{scroll_attempts}")
                    self.human_behavior.anti_detection_scroll()

                    # Дополнительная пауза для загрузки контента
                    self.human_behavior.random_delay('scroll_pause')

                    # Иногда делаем более длинную паузу
                    behavior_config = self.config.get('behavior', {})
                    probabilities = behavior_config.get('probabilities', {})
                    if random.random() < probabilities.get('extra_long_pause', 0.3):
                        self.human_behavior.take_break('long_break')

            logger.info(f"🏁 Завершен сбор от @{username}: {len(collected_tweets)} твитов за {scroll_attempts} итераций")
            return collected_tweets

        except Exception as e:
            logger.error(f"Критическая ошибка при сборе твитов от @{username}: {e}")
            return collected_tweets  # Возвращаем то, что успели собрать

    def _parse_twitter_date(self, date_str: str) -> Optional[datetime.datetime]:
        """
        Парсинг даты Twitter

        Args:
            date_str: Строка с датой

        Returns:
            datetime объект или None
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

    def run(self, chrome_profile_path: Optional[str] = None, accounts_file: str = "influencer_twitter.txt") -> bool:
        """
        Основная функция запуска парсера

        Args:
            chrome_profile_path: Путь к профилю Chrome
            accounts_file: Файл со списком аккаунтов

        Returns:
            True если выполнение успешно
        """
        try:
            self.stats['start_time'] = time.time()

            logger.info("🚀 === ЗАПУСК ОБЛЕГЧЕННОГО ПАРСЕРА TWITTER ===")

            # Инициализация
            if not self.initialize(chrome_profile_path):
                logger.error("❌ Ошибка инициализации парсера")
                return False

            # Авторизация
            self.authenticate()

            # Загрузка списка аккаунтов
            accounts = self.load_accounts_from_file(accounts_file)
            if not accounts:
                logger.error("❌ Нет аккаунтов для обработки")
                return False

            # Параметры сбора
            scraper_config = self.config.get('scraper', {})
            behavior_config = self.config.get('behavior', {})

            max_tweets_per_account = scraper_config.get('max_tweets_per_account', 15)
            time_filter_hours = scraper_config.get('time_filter_hours', 24)

            delays = behavior_config.get('delays', {})
            probabilities = behavior_config.get('probabilities', {})

            logger.info(f"📊 Параметры сбора:")
            logger.info(f"   • Аккаунтов: {len(accounts)}")
            logger.info(f"   • Макс. твитов на аккаунт: {max_tweets_per_account}")
            logger.info(f"   • Период: {time_filter_hours} часов")

            # Случайно перемешиваем аккаунты
            shuffled_accounts = accounts.copy()
            random.shuffle(shuffled_accounts)

            # Обрабатываем каждый аккаунт
            for i, username in enumerate(shuffled_accounts, 1):
                logger.info(f"👤 === Аккаунт {i}/{len(accounts)}: @{username} ===")

                try:
                    tweets = self.get_tweets_from_user(username)

                    if tweets:
                        self.stats['tweets_collected'] += len(tweets)
                        self.stats['successful_accounts'] += 1
                        logger.info(f"✅ От @{username} получено {len(tweets)} твитов")
                    else:
                        self.stats['failed_accounts'] += 1
                        logger.warning(f"❌ От @{username} твиты не получены")

                    self.stats['accounts_processed'] += 1

                    # Перерыв между аккаунтами
                    if i < len(accounts):
                        inter_pause_range = delays.get('inter_account_pause', (15, 35))
                        pause_time = random.uniform(*inter_pause_range)
                        logger.info(f"⏳ Пауза между аккаунтами: {pause_time:.1f} сек")
                        time.sleep(pause_time)

                        # Иногда делаем дополнительную паузу
                        extra_pause_prob = probabilities.get('extra_long_pause', 0.4)
                        if random.random() < extra_pause_prob:
                            long_break_range = delays.get('long_break', (120, 300))
                            extra_pause = random.uniform(*long_break_range)
                            logger.info(f"☕ Дополнительная пауза: {extra_pause:.1f} сек")
                            time.sleep(extra_pause)

                        # Иногда посещаем главную страницу
                        homepage_prob = probabilities.get('visit_homepage', 0.3)
                        if random.random() < homepage_prob:
                            logger.info("🏠 Посещение главной страницы Twitter")
                            try:
                                self.browser.driver.get("https://twitter.com")
                                self.human_behavior.random_delay('page_load_wait')
                                self.human_behavior.simulate_reading_pause(100)
                                self.human_behavior.human_scroll()
                            except Exception as e:
                                logger.debug(f"Ошибка посещения главной: {e}")

                except Exception as e:
                    self.stats['failed_accounts'] += 1
                    self.stats['accounts_processed'] += 1
                    logger.error(f"Ошибка при обработке @{username}: {e}")
                    continue

            # Финальная статистика
            self._print_final_stats()

            return True

        except KeyboardInterrupt:
            logger.info("⏹️ Прервано пользователем (Ctrl+C)")
            return False
        except Exception as e:
            logger.error(f"💥 Критическая ошибка: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
        finally:
            self.cleanup()

    def _print_final_stats(self):
        """Вывод финальной статистики"""
        if self.stats['start_time']:
            duration = time.time() - self.stats['start_time']
            duration_minutes = duration / 60
        else:
            duration_minutes = 0

        logger.info("📊 === ФИНАЛЬНАЯ СТАТИСТИКА ===")
        logger.info(f"⏱️  Время работы: {duration_minutes:.1f} мин")
        logger.info(f"👥 Всего аккаунтов: {self.stats['accounts_processed']}")
        logger.info(f"✅ Успешно обработано: {self.stats['successful_accounts']}")
        logger.info(f"❌ Неудачно: {self.stats['failed_accounts']}")
        logger.info(f"📝 Всего твитов собрано: {self.stats['tweets_collected']}")

        if self.stats['successful_accounts'] > 0:
            avg_tweets = self.stats['tweets_collected'] / self.stats['successful_accounts']
            logger.info(f"📈 Среднее твитов на аккаунт: {avg_tweets:.1f}")

        if duration_minutes > 0:
            tweets_per_minute = self.stats['tweets_collected'] / duration_minutes
            logger.info(f"⚡ Скорость: {tweets_per_minute:.1f} твитов/мин")

        # Статистика базы данных
        if self.database:
            try:
                db_stats = self.database.get_database_stats()
                if 'error' not in db_stats:
                    logger.info("🗄️ === СТАТИСТИКА БАЗЫ ДАННЫХ ===")
                    logger.info(f"📊 Всего твитов в БД: {db_stats.get('total_tweets', 0):,}")
                    logger.info(f"🕐 За 24 часа: {db_stats.get('tweets_24h', 0):,}")
                    logger.info(f"📅 За 7 дней: {db_stats.get('tweets_7d', 0):,}")
            except Exception as e:
                logger.error(f"Ошибка получения статистики БД: {e}")

    def cleanup(self):
        """Очистка ресурсов"""
        logger.info("🧹 Очистка ресурсов...")

        if self.browser:
            self.browser.close()
            self.browser = None

        if self.database:
            self.database.close()
            self.database = None

        logger.info("✨ Очистка завершена")


def main():
    """Точка входа в программу"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('twitter_scraper.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    # Конфигурация (можно вынести в отдельный файл)
    config = {
        'mysql': {
            'host': '217.154.19.224',
            'database': 'twitter_data',
            'user': 'elcrypto',
            'password': 'LohNeMamont@!21',
            'port': 3306,
            'charset': 'utf8mb4',
            'use_unicode': True
        },
        'scraper': {
            'max_tweets_per_account': 15,
            'time_filter_hours': 24,
            'max_scroll_attempts': 25,
            'max_consecutive_no_new': 5
        },
        'behavior': {
            'delays': {
                'between_actions': (1, 3),
                'reading_pause': (2, 8),
                'inter_account_pause': (15, 35),  # Увеличенные паузы для безопасности
                'long_break': (120, 300),
                'page_load_wait': (3, 6),
                'scroll_pause': (2, 5),
            },
            'probabilities': {
                'extra_long_pause': 0.4,  # Чаще делаем длинные паузы
                'visit_homepage': 0.3,
                'simulate_interest': 0.15,
            }
        }
    }

    # Путь к профилю Chrome (настройте под свою систему)
    chrome_profile_path = "/Users/evgeniyyanvarskiy/Library/Application Support/Google/Chrome/Profile 1/"

    # Создаем и запускаем парсер
    scraper = LightweightTwitterScraper(config)
    success = scraper.run(chrome_profile_path, "influencer_twitter.txt")

    if success:
        print("🎉 Парсер завершил работу успешно!")
    else:
        print("💥 Парсер завершился с ошибками")


if __name__ == "__main__":
    main()