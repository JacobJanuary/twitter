#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для управления браузером Chrome с защитой от обнаружения
Содержит функции для инициализации браузера, авторизации и настройки
"""

import os
import random
import logging
import uuid
from typing import Optional, Dict, Any, List
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

logger = logging.getLogger(__name__)

# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для управления браузером Chrome с защитой от обнаружения
Содержит функции для инициализации браузера, авторизации и настройки
"""

import os
import random
import logging
import uuid
from typing import Optional, Dict, Any, List
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

logger = logging.getLogger(__name__)


class TwitterBrowser:
    """Класс для управления браузером с защитой от обнаружения"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Инициализация браузера

        Args:
            config: Конфигурация браузера и User-Agent'ов
        """
        self.driver = None
        self.session_id = str(uuid.uuid4())[:8]

        # Конфигурация по умолчанию
        self.config = config or {
            'user_agents': [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            ],
            'window_sizes': ['1920,1080', '1366,768', '1440,900'],
            'chrome_profile_path': None
        }

    def get_random_user_agent(self) -> str:
        """Получить случайный User-Agent"""
        return random.choice(self.config['user_agents'])

    def get_random_window_size(self) -> str:
        """Получить случайный размер окна"""
        return random.choice(self.config['window_sizes'])

    def initialize_browser(self, chrome_profile_path: Optional[str] = None) -> bool:
        """
        Инициализация браузера Chrome с защитой от обнаружения

        Args:
            chrome_profile_path: Путь к профилю Chrome

        Returns:
            True если инициализация успешна, False в противном случае
        """
        try:
            options = Options()

            # Базовые настройки
            window_size = self.get_random_window_size()
            options.add_argument(f"--window-size={window_size}")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")

            # Продвинутая защита от обнаружения
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-extensions-except")
            options.add_argument("--disable-plugins-discovery")
            options.add_argument("--disable-web-security")
            options.add_argument("--disable-features=VizDisplayCompositor")
            options.add_argument("--disable-ipc-flooding-protection")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)

            # Случайный User-Agent
            user_agent = self.get_random_user_agent()
            options.add_argument(f"--user-agent={user_agent}")

            # Языковые настройки
            options.add_argument("--lang=en-US,en")
            options.add_experimental_option("prefs", {
                "intl.accept_languages": "en-US,en",
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_settings.popups": 0,
                "profile.managed_default_content_settings.images": 2  # Отключаем изображения для скорости
            })

            # Профиль Chrome
            profile_path = chrome_profile_path or self.config.get('chrome_profile_path')
            if profile_path and os.path.exists(profile_path):
                options.add_argument(f"user-data-dir={profile_path}")
                logger.info(f"Используется профиль Chrome: {profile_path}")

            # Создаем драйвер
            self.driver = webdriver.Chrome(options=options)

            # Настройка продвинутой защиты от обнаружения
            self._setup_anti_detection()

            # Настройки таймаутов
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(10)

            logger.info(f"Браузер Chrome инициализирован (сессия: {self.session_id})")
            return True

        except Exception as e:
            logger.error(f"Ошибка инициализации браузера: {e}")
            return False

    def _setup_anti_detection(self):
        """Настройка продвинутой защиты от обнаружения"""
        # Скрипты для маскировки автоматизации
        anti_detection_scripts = [
            # Скрываем webdriver property
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",

            # Подменяем plugins
            """
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            """,

            # Подменяем languages
            """
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            """,

            # Маскируем Chrome runtime
            """
            if (window.chrome) {
                Object.defineProperty(window.chrome, 'runtime', {
                    get: () => ({
                        onConnect: undefined,
                        onMessage: undefined
                    })
                });
            }
            """,

            # Подменяем permissions
            """
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
            """
        ]

        for script in anti_detection_scripts:
            try:
                self.driver.execute_script(script)
            except Exception as e:
                logger.debug(f"Не удалось выполнить anti-detection скрипт: {e}")

        # CDP команды для дополнительной маскировки
        try:
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": self.get_random_user_agent(),
                "acceptLanguage": "en-US,en;q=0.9",
                "platform": random.choice(["Win32", "MacIntel", "Linux x86_64"])
            })

            # Отключаем автоматизированные функции
            self.driver.execute_cdp_cmd('Runtime.evaluate', {
                "expression": """
                    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                """
            })

        except Exception as e:
            logger.debug(f"CDP команды не выполнены: {e}")

    def manual_auth(self, human_behavior=None) -> bool:
        """
        Ручная авторизация в Twitter с имитацией поведения пользователя

        Args:
            human_behavior: Экземпляр HumanBehaviorSimulator для имитации поведения

        Returns:
            True если авторизация успешна, False в противном случае
        """
        try:
            logger.info("Открытие страницы авторизации Twitter")

            # Сначала заходим на главную страницу
            self.driver.get("https://twitter.com")
            if human_behavior:
                human_behavior.random_delay('reading_pause')
                human_behavior.simulate_reading_pause(50)

            # Потом переходим на страницу логина
            self.driver.get("https://twitter.com/login")
            if human_behavior:
                human_behavior.random_delay('page_load_wait')
                human_behavior.simulate_reading_pause(100)
                human_behavior.random_mouse_movement()

            print("\n=== АВТОРИЗАЦИЯ В TWITTER ===")
            print("Пожалуйста, войдите в свой аккаунт Twitter в открывшемся окне браузера")
            print("ВАЖНО: Действуйте естественно, не торопитесь")

            # Даем время пользователю на авторизацию
            input("После завершения авторизации нажмите Enter для продолжения...")

            # Проверяем результат авторизации с задержкой
            if human_behavior:
                human_behavior.random_delay('between_actions')

            # Проверяем URL и содержимое страницы
            current_url = self.driver.current_url
            page_source = self.driver.page_source

            # Улучшенная проверка авторизации
            auth_indicators = [
                "home" in current_url.lower(),
                "timeline" in page_source.lower(),
                "compose" in page_source.lower(),
                not ("Log in" in page_source and "Sign up" in page_source)
            ]

            is_authenticated = any(auth_indicators)

            if is_authenticated:
                logger.info("Авторизация успешна")
                # Имитируем просмотр ленты после авторизации
                if human_behavior:
                    human_behavior.simulate_reading_pause(150)
                    human_behavior.random_mouse_movement()
                return True
            else:
                logger.warning("Авторизация не подтверждена")
                return False

        except Exception as e:
            logger.error(f"Ошибка при авторизации: {e}")
            return False

    def navigate_to_profile(self, username: str, human_behavior=None) -> bool:
        """
        Переход на страницу профиля пользователя

        Args:
            username: Имя пользователя Twitter
            human_behavior: Экземпляр HumanBehaviorSimulator

        Returns:
            True если переход успешен, False в противном случае
        """
        try:
            profile_url = f"https://twitter.com/{username}"

            # Иногда сначала заходим на главную (имитация естественного поведения)
            if human_behavior and random.random() < 0.2:
                self.driver.get("https://twitter.com")
                human_behavior.random_delay('reading_pause')

            self.driver.get(profile_url)

            # Имитируем загрузку страницы
            if human_behavior:
                human_behavior.random_delay('page_load_wait')

            # Ждем загрузки страницы
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]'))
                )

                # Имитируем изучение профиля
                if human_behavior:
                    human_behavior.simulate_reading_pause(120)
                    human_behavior.random_mouse_movement()

                return True

            except TimeoutException:
                logger.warning(f"Таймаут загрузки страницы пользователя @{username}")
                return False

        except Exception as e:
            logger.error(f"Ошибка при переходе к профилю @{username}: {e}")
            return False

    def check_account_availability(self, username: str) -> bool:
        """
        Проверка доступности аккаунта

        Args:
            username: Имя пользователя для проверки

        Returns:
            True если аккаунт доступен, False если заблокирован/не существует
        """
        try:
            page_source = self.driver.page_source

            unavailable_indicators = [
                "This account doesn't exist",
                "Account suspended",
                "User not found",
                "Hmm...this page doesn't exist",
                "Something went wrong",
                "Rate limit exceeded",
                "Temporarily restricted"
            ]

            for indicator in unavailable_indicators:
                if indicator in page_source:
                    logger.warning(f"Аккаунт @{username} недоступен: {indicator}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Ошибка проверки доступности аккаунта @{username}: {e}")
            return False

    def find_tweets_on_page(self) -> List:
        """
        Поиск всех твитов на текущей странице

        Returns:
            Список элементов твитов
        """
        try:
            tweet_elements = self.driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')

            # Фильтруем только видимые элементы
            visible_tweets = []
            for element in tweet_elements:
                try:
                    if element.is_displayed():
                        visible_tweets.append(element)
                except Exception:
                    continue

            logger.debug(f"Найдено {len(visible_tweets)} видимых твитов на странице")
            return visible_tweets

        except Exception as e:
            logger.error(f"Ошибка поиска твитов на странице: {e}")
            return []

    def scroll_page(self, distance: int = 800):
        """
        Прокрутка страницы

        Args:
            distance: Расстояние прокрутки в пикселях
        """
        try:
            self.driver.execute_script(f"window.scrollBy(0, {distance});")
        except Exception as e:
            logger.error(f"Ошибка прокрутки страницы: {e}")

    def get_page_height(self) -> int:
        """
        Получение высоты страницы

        Returns:
            Высота страницы в пикселях
        """
        try:
            return self.driver.execute_script("return document.body.scrollHeight")
        except Exception as e:
            logger.error(f"Ошибка получения высоты страницы: {e}")
            return 0

    def warmup_browsing(self, sites: Optional[List[str]] = None):
        """
        Разогрев браузера посещением обычных сайтов

        Args:
            sites: Список сайтов для посещения
        """
        warmup_sites = sites or [
            "https://google.com",
            "https://github.com",
            "https://stackoverflow.com"
        ]

        try:
            site = random.choice(warmup_sites)
            logger.info(f"Разогрев браузера: {site}")
            self.driver.get(site)

            # Небольшая пауза для имитации просмотра
            import time
            time.sleep(random.uniform(2, 5))

        except Exception as e:
            logger.debug(f"Ошибка разогрева браузера: {e}")

    def save_page_source(self, filename: str):
        """
        Сохранение исходного кода страницы для отладки

        Args:
            filename: Имя файла для сохранения
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.debug(f"HTML страницы сохранен в {filename}")
        except Exception as e:
            logger.error(f"Ошибка сохранения HTML: {e}")

    def get_browser_info(self) -> Dict[str, Any]:
        """
        Получение информации о браузере

        Returns:
            Словарь с информацией о браузере
        """
        try:
            return {
                'session_id': self.session_id,
                'current_url': self.driver.current_url if self.driver else None,
                'window_size': self.driver.get_window_size() if self.driver else None,
                'user_agent': self.driver.execute_script("return navigator.userAgent") if self.driver else None
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о браузере: {e}")
            return {'session_id': self.session_id, 'error': str(e)}

    def is_connected(self) -> bool:
        """
        Проверка состояния браузера

        Returns:
            True если браузер активен, False в противном случае
        """
        try:
            if self.driver is None:
                return False

            # Пытаемся выполнить простую команду
            self.driver.current_url
            return True

        except Exception:
            return False

    def close(self):
        """Закрытие браузера"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Браузер закрыт")
            except Exception as e:
                logger.error(f"Ошибка закрытия браузера: {e}")
            finally:
                self.driver = None

    def __enter__(self):
        """Поддержка context manager"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое закрытие при выходе из контекста"""
        self.close()


def create_browser(config: Optional[Dict[str, Any]] = None,
                   chrome_profile_path: Optional[str] = None) -> Optional[TwitterBrowser]:
    """
    Фабричная функция для создания и инициализации браузера

    Args:
        config: Конфигурация браузера
        chrome_profile_path: Путь к профилю Chrome

    Returns:
        Экземпляр TwitterBrowser или None в случае ошибки
    """
    try:
        browser = TwitterBrowser(config)
        if browser.initialize_browser(chrome_profile_path):
            return browser
        else:
            return None
    except Exception as e:
        logger.error(f"Ошибка создания браузера: {e}")
        return None