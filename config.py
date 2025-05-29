#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конфигурация для облегченного парсера Twitter
Содержит все настройки для модулей: база данных, браузер, поведение
"""

import random
from typing import Dict, Any, Tuple

# ===============================
# НАСТРОЙКИ БАЗЫ ДАННЫХ
# ===============================

MYSQL_CONFIG = {
    'host': '217.154.19.224',
    'database': 'crypto_analyzer',
    'user': 'elcrypto',
    'password': 'LohNeMamont@!21',
    'port': 3306,
    'charset': 'utf8mb4',
    'use_unicode': True
}

# ===============================
# НАСТРОЙКИ ПАРСЕРА
# ===============================

SCRAPER_CONFIG = {
    # Основные параметры сбора
    'max_tweets_per_account': 15,  # Максимум твитов с одного аккаунта
    'time_filter_hours': 24,  # Период сбора в часах
    'max_scroll_attempts': 25,  # Максимум попыток скроллинга
    'max_consecutive_no_new': 5,  # Максимум итераций без новых твитов

    # Настройки для защиты от блокировок
    'retry_attempts': 3,  # Количество повторных попыток
    'retry_delay': 5,  # Задержка между повторами (сек)
    'session_tweet_limit': 200,  # Лимит твитов за сессию
    'daily_account_limit': 50,  # Лимит аккаунтов в день
}

# ===============================
# НАСТРОЙКИ БРАУЗЕРА
# ===============================

BROWSER_CONFIG = {
    # Путь к профилю Chrome (настройте под свою систему)
    'chrome_profile_path': None,  # Будет установлен в main()

    # User-Agent строки для ротации
    'user_agents': [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
    ],

    # Размеры окна браузера
    'window_sizes': [
        '1920,1080',
        '1366,768',
        '1440,900',
        '1536,864',
        '1280,720'
    ],

    # Дополнительные настройки Chrome
    'chrome_options': {
        'disable_images': True,  # Отключить загрузку изображений
        'disable_javascript': False,  # JavaScript нужен для работы
        'headless': False,  # Показывать браузер (для авторизации)
        'incognito': False,  # Не использовать режим инкогнито
    }
}

# ===============================
# НАСТРОЙКИ ПОВЕДЕНИЯ ПОЛЬЗОВАТЕЛЯ
# ===============================

BEHAVIOR_CONFIG = {
    # Временные задержки (мин, макс в секундах)
    'delays': {
        'between_actions': (1.0, 3.0),  # Между обычными действиями
        'reading_pause': (2.0, 8.0),  # Пауза на чтение контента
        'typing_speed': (0.05, 0.2),  # Скорость печати (сек на символ)
        'inter_account_pause': (15.0, 35.0),  # Между аккаунтами (увеличено)
        'long_break': (120.0, 300.0),  # Длинные перерывы (2-5 мин)
        'page_load_wait': (3.0, 6.0),  # Ожидание загрузки страницы
        'scroll_pause': (2.0, 5.0),  # После скроллинга
        'warmup_browse': (2.0, 5.0),  # Разогрев браузера
    },

    # Вероятности различных действий (от 0.0 до 1.0)
    'probabilities': {
        'extra_long_pause': 0.4,  # Дополнительная длинная пауза
        'visit_homepage': 0.3,  # Посещение главной страницы
        'simulate_interest': 0.15,  # Имитация заинтересованности
        'random_mouse_movement': 0.25,  # Случайные движения мыши
        'tab_switching': 0.1,  # Переключение вкладок
        'scroll_back': 0.15,  # Скроллинг назад
        'warmup_browsing': 0.8,  # Разогрев перед работой
        'check_page_title': 0.2,  # Проверка заголовка
    },

    # Параметры скроллинга
    'scroll': {
        'distances': [300, 400, 500, 600, 700, 800],  # Варианты дистанции
        'types': ['smooth', 'wheel'],  # Типы скроллинга
        'smooth_steps_range': (5, 12),  # Шаги для плавного скроллинга
        'wheel_steps_range': (3, 8),  # Шаги для колесика
        'back_distance_range': (50, 200),  # Дистанция обратного скроллинга
    }
}

# ===============================
# САЙТЫ ДЛЯ РАЗОГРЕВА
# ===============================

WARMUP_SITES = [
    "https://google.com",
    "https://github.com",
    "https://stackoverflow.com",
    "https://news.ycombinator.com",
    "https://reddit.com",
    "https://wikipedia.org"
]

# ===============================
# СЕЛЕКТОРЫ ЭЛЕМЕНТОВ
# ===============================

SELECTORS = {
    # Основные селекторы твитов
    'tweet_article': 'article[data-testid="tweet"]',
    'tweet_text': 'div[data-testid="tweetText"]',
    'tweet_time': 'time',
    'tweet_link': 'a[href*="/status/"]',
    'alternative_text': '[lang][dir="auto"]',

    # Кнопки раскрытия твита
    'show_more_buttons': [
        './/div[@role="button" and (contains(., "Show more") or contains(., "Показать ещё"))]',
        './/span[contains(., "Show more") or contains(., "Показать ещё")]'
    ],

    # Элементы авторизации
    'login_indicators': ['Log in', 'Sign up'],
    'auth_success_indicators': ['home', 'timeline', 'compose'],
}

# ===============================
# ИНДИКАТОРЫ ПРОБЛЕМ
# ===============================

# Признаки заблокированных/недоступных аккаунтов
ACCOUNT_UNAVAILABLE_INDICATORS = [
    "This account doesn't exist",
    "Account suspended",
    "User not found",
    "Hmm...this page doesn't exist",
    "Something went wrong",
    "Rate limit exceeded",
    "Temporarily restricted",
    "Account locked",
    "Protected tweets"
]

# Признаки блокировки IP/сессии
BLOCKING_INDICATORS = [
    "Too many requests",
    "Rate limit exceeded",
    "Please try again later",
    "Unusual activity",
    "Automated requests",
    "Challenge required"
]

# ===============================
# НАСТРОЙКИ ЛОГИРОВАНИЯ
# ===============================

LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'twitter_scraper.log',
    'max_bytes': 10 * 1024 * 1024,  # 10 MB
    'backup_count': 5,
    'encoding': 'utf-8'
}


# ===============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ===============================

def get_random_delay(delay_type: str) -> float:
    """
    Получить случайную задержку определенного типа

    Args:
        delay_type: Тип задержки из BEHAVIOR_CONFIG['delays']

    Returns:
        Случайное время задержки в секундах
    """
    if delay_type in BEHAVIOR_CONFIG['delays']:
        min_val, max_val = BEHAVIOR_CONFIG['delays'][delay_type]
        return random.uniform(min_val, max_val)
    return random.uniform(1.0, 3.0)  # Значение по умолчанию


def should_perform_action(action_type: str) -> bool:
    """
    Определить, следует ли выполнить действие на основе вероятности

    Args:
        action_type: Тип действия из BEHAVIOR_CONFIG['probabilities']

    Returns:
        True если действие следует выполнить
    """
    if action_type in BEHAVIOR_CONFIG['probabilities']:
        return random.random() < BEHAVIOR_CONFIG['probabilities'][action_type]
    return random.random() < 0.2  # Значение по умолчанию


def get_random_user_agent() -> str:
    """Получить случайный User-Agent"""
    return random.choice(BROWSER_CONFIG['user_agents'])


def get_random_window_size() -> str:
    """Получить случайный размер окна"""
    return random.choice(BROWSER_CONFIG['window_sizes'])


def get_random_warmup_site() -> str:
    """Получить случайный сайт для разогрева"""
    return random.choice(WARMUP_SITES)


def get_scroll_distance() -> int:
    """Получить случайную дистанцию скроллинга"""
    return random.choice(BEHAVIOR_CONFIG['scroll']['distances'])


def get_scroll_type() -> str:
    """Получить случайный тип скроллинга"""
    return random.choice(BEHAVIOR_CONFIG['scroll']['types'])


# ===============================
# ПРОФИЛИ ПОВЕДЕНИЯ
# ===============================

# Консервативный профиль (для длительной работы без блокировок)
CONSERVATIVE_PROFILE = {
    'scraper': {
        'max_tweets_per_account': 10,
        'max_scroll_attempts': 15,
    },
    'delays': {
        'inter_account_pause': (30.0, 60.0),  # Очень длинные паузы
        'long_break': (300.0, 600.0),  # 5-10 минут
    },
    'probabilities': {
        'extra_long_pause': 0.6,  # Часто отдыхаем
        'visit_homepage': 0.4,  # Часто заходим на главную
    }
}

# Быстрый профиль (для быстрого сбора, повышенный риск)
FAST_PROFILE = {
    'scraper': {
        'max_tweets_per_account': 25,
        'max_scroll_attempts': 35,
    },
    'delays': {
        'inter_account_pause': (5.0, 15.0),  # Короткие паузы
        'long_break': (60.0, 120.0),  # 1-2 минуты
    },
    'probabilities': {
        'extra_long_pause': 0.2,  # Редко отдыхаем
        'visit_homepage': 0.1,  # Редко заходим на главную
    }
}

# Сбалансированный профиль (по умолчанию)
BALANCED_PROFILE = {
    'scraper': SCRAPER_CONFIG,
    'delays': BEHAVIOR_CONFIG['delays'],
    'probabilities': BEHAVIOR_CONFIG['probabilities']
}


# ===============================
# ФУНКЦИИ ПРИМЕНЕНИЯ ПРОФИЛЕЙ
# ===============================

def apply_behavior_profile(profile_name: str = 'balanced') -> Dict[str, Any]:
    """
    Применить профиль поведения

    Args:
        profile_name: Название профиля ('conservative', 'fast', 'balanced')

    Returns:
        Словарь с обновленной конфигурацией
    """
    base_config = {
        'mysql': MYSQL_CONFIG,
        'scraper': SCRAPER_CONFIG.copy(),
        'browser': BROWSER_CONFIG,
        'behavior': BEHAVIOR_CONFIG.copy()
    }

    if profile_name == 'conservative':
        profile = CONSERVATIVE_PROFILE
    elif profile_name == 'fast':
        profile = FAST_PROFILE
    else:
        profile = BALANCED_PROFILE

    # Применяем изменения профиля
    for section, settings in profile.items():
        if section in base_config:
            if isinstance(base_config[section], dict):
                base_config[section].update(settings)
            else:
                base_config[section] = settings
        elif section in base_config['behavior']:
            base_config['behavior'][section].update(settings)

    return base_config


# ===============================
# НАСТРОЙКИ ПО СИСТЕМАМ
# ===============================

# Пути к профилям Chrome для разных ОС
CHROME_PROFILES = {
    'macos': "/Users/{username}/Library/Application Support/Google/Chrome/Profile 1/",
    'windows': "C:\\Users\\{username}\\AppData\\Local\\Google\\Chrome\\User Data\\Profile 1",
    'linux': "/home/{username}/.config/google-chrome/Profile 1"
}


def get_chrome_profile_path(username: str, os_type: str = 'macos') -> str:
    """
    Получить путь к профилю Chrome для конкретной ОС

    Args:
        username: Имя пользователя системы
        os_type: Тип ОС ('macos', 'windows', 'linux')

    Returns:
        Путь к профилю Chrome
    """
    if os_type in CHROME_PROFILES:
        return CHROME_PROFILES[os_type].format(username=username)
    return CHROME_PROFILES['macos'].format(username=username)


# ===============================
# ВАЛИДАЦИЯ КОНФИГУРАЦИИ
# ===============================

def validate_config() -> bool:
    """
    Проверка корректности конфигурации

    Returns:
        True если конфигурация корректна
    """
    errors = []

    # Проверка MySQL конфигурации
    required_mysql_keys = ['host', 'database', 'user', 'password', 'port']
    for key in required_mysql_keys:
        if key not in MYSQL_CONFIG:
            errors.append(f"Отсутствует ключ '{key}' в MYSQL_CONFIG")

    # Проверка диапазонов задержек
    for delay_name, (min_val, max_val) in BEHAVIOR_CONFIG['delays'].items():
        if min_val >= max_val:
            errors.append(f"Некорректный диапазон для '{delay_name}': {min_val} >= {max_val}")
        if min_val < 0:
            errors.append(f"Отрицательное значение для '{delay_name}': {min_val}")

    # Проверка вероятностей
    for prob_name, prob_val in BEHAVIOR_CONFIG['probabilities'].items():
        if not 0 <= prob_val <= 1:
            errors.append(f"Вероятность '{prob_name}' вне диапазона [0, 1]: {prob_val}")

    # Проверка списков
    if not BROWSER_CONFIG['user_agents']:
        errors.append("Пустой список user_agents")

    if not WARMUP_SITES:
        errors.append("Пустой список сайтов для разогрева")

    if errors:
        print("❌ Ошибки в конфигурации:")
        for error in errors:
            print(f"   • {error}")
        return False

    print("✅ Конфигурация корректна")
    return True


# ===============================
# ЭКСПОРТ ОСНОВНЫХ ОБЪЕКТОВ
# ===============================

__all__ = [
    'MYSQL_CONFIG',
    'SCRAPER_CONFIG',
    'BROWSER_CONFIG',
    'BEHAVIOR_CONFIG',
    'WARMUP_SITES',
    'SELECTORS',
    'ACCOUNT_UNAVAILABLE_INDICATORS',
    'BLOCKING_INDICATORS',
    'LOGGING_CONFIG',
    'get_random_delay',
    'should_perform_action',
    'get_random_user_agent',
    'get_random_window_size',
    'get_random_warmup_site',
    'get_scroll_distance',
    'get_scroll_type',
    'apply_behavior_profile',
    'get_chrome_profile_path',
    'validate_config'
]

# Автоматическая валидация при импорте
if __name__ == "__main__":
    validate_config()