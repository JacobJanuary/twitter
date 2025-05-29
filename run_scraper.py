#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Универсальный запуск парсера Twitter
Автоматически выбирает лучшую доступную версию
"""

import sys
import logging
import os
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('twitter_scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def check_dependencies():
    """Проверка наличия зависимостей"""
    required_packages = ['selenium', 'mysql-connector-python']
    missing_packages = []

    for package in required_packages:
        try:
            if package == 'mysql-connector-python':
                import mysql.connector
            else:
                __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        logger.error(f"❌ Отсутствуют пакеты: {', '.join(missing_packages)}")
        logger.info("Установите их командой: pip install " + " ".join(missing_packages))
        return False

    logger.info("✅ Все зависимости установлены")
    return True


def test_main_scraper():
    """Тест основного парсера"""
    try:
        from scraper import LightweightTwitterScraper

        # Простой тест создания объекта
        config = {
            'mysql': {'host': 'test'},
            'scraper': {'max_tweets_per_account': 1},
            'browser': {'user_agents': ['test']},
            'behavior': {'delays': {'between_actions': (1, 2)}}
        }

        scraper = LightweightTwitterScraper(config)
        logger.info("✅ Основной парсер доступен")
        return True, scraper

    except SyntaxError as e:
        logger.warning(f"⚠️ Синтаксическая ошибка в основном парсере: {e}")
        return False, None
    except Exception as e:
        logger.warning(f"⚠️ Ошибка загрузки основного парсера: {e}")
        return False, None


def test_simple_scraper():
    """Тест упрощенного парсера"""
    try:
        from simple_scraper import SimpleTwitterScraper

        config = {'scraper': {'max_tweets_per_account': 1}}
        scraper = SimpleTwitterScraper(config)
        logger.info("✅ Упрощенный парсер доступен")
        return True, scraper

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки упрощенного парсера: {e}")
        return False, None


def get_chrome_profile_path():
    """Определение пути к профилю Chrome"""
    system_paths = {
        'darwin': "~/Library/Application Support/Google/Chrome/Profile 1/",  # macOS
        'win32': "~\\AppData\\Local\\Google\\Chrome\\User Data\\Profile 1",  # Windows
        'linux': "~/.config/google-chrome/Profile 1"  # Linux
    }

    platform = sys.platform
    if platform.startswith('darwin'):
        path = system_paths['darwin']
    elif platform.startswith('win'):
        path = system_paths['win32']
    else:
        path = system_paths['linux']

    expanded_path = Path(path).expanduser()

    if expanded_path.exists():
        logger.info(f"✅ Найден профиль Chrome: {expanded_path}")
        return str(expanded_path)
    else:
        logger.warning(f"⚠️ Профиль Chrome не найден: {expanded_path}")
        return None


def create_sample_accounts_file():
    """Создание примера файла с аккаунтами"""
    filename = "influencer_twitter.txt"

    if not os.path.exists(filename):
        sample_accounts = [
            "# Пример файла с аккаунтами Twitter",
            "# Можно указывать URL или просто username",
            "",
            "# Примеры:",
            "# https://x.com/elonmusk",
            "# https://x.com/BillGates",
            "# sundarpichai",
            "# @tim_cook",
            "",
            "# Добавьте свои аккаунты ниже:",
            "elonmusk",
            "BillGates"
        ]

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write('\n'.join(sample_accounts))
            logger.info(f"✅ Создан пример файла: {filename}")
        except Exception as e:
            logger.error(f"❌ Не удалось создать файл {filename}: {e}")


def main():
    """Основная функция"""
    logger.info("🚀 === ЗАПУСК ПАРСЕРА TWITTER ===")

    # Проверка зависимостей
    if not check_dependencies():
        logger.error("💥 Установите недостающие зависимости и повторите запуск")
        return False

    # Создание примера файла с аккаунтами
    create_sample_accounts_file()

    # Определение профиля Chrome
    chrome_profile = get_chrome_profile_path()

    # Попытка использовать основной парсер
    logger.info("🔍 Проверка доступности основного парсера...")
    main_available, main_scraper = test_main_scraper()

    if main_available:
        logger.info("🎯 Используется основной парсер с полным функционалом")
        try:
            success = main_scraper.run(chrome_profile, "influencer_twitter.txt")
            if success:
                logger.info("🎉 Парсер завершил работу успешно!")
            else:
                logger.error("💥 Парсер завершился с ошибками")
            return success
        except Exception as e:
            logger.error(f"💥 Ошибка выполнения основного парсера: {e}")
            logger.info("🔄 Переключение на упрощенную версию...")

    # Fallback на упрощенный парсер
    logger.info("🔍 Проверка доступности упрощенного парсера...")
    simple_available, simple_scraper = test_simple_scraper()

    if simple_available:
        logger.info("🎯 Используется упрощенный парсер (тестовый режим)")
        try:
            success = simple_scraper.run()
            if success:
                logger.info("🎉 Упрощенный парсер завершил работу успешно!")
            else:
                logger.error("💥 Упрощенный парсер завершился с ошибками")
            return success
        except Exception as e:
            logger.error(f"💥 Ошибка выполнения упрощенного парсера: {e}")

    # Если ничего не работает
    logger.error("💥 Ни одна версия парсера не доступна")
    logger.info("📋 Проверьте:")
    logger.info("   1. Установлены ли все зависимости: pip install -r requirements.txt")
    logger.info("   2. Нет ли синтаксических ошибок в файлах")
    logger.info("   3. Запустите тест: python test_modules.py")

    return False


def interactive_setup():
    """Интерактивная настройка"""
    print("\n" + "=" * 50)
    print("🔧 ИНТЕРАКТИВНАЯ НАСТРОЙКА ПАРСЕРА")
    print("=" * 50)

    # Проверка файла аккаунтов
    accounts_file = "influencer_twitter.txt"
    if not os.path.exists(accounts_file):
        print(f"\n❌ Файл {accounts_file} не найден")
        create_sample_accounts_file()
        print(f"✅ Создан пример файла {accounts_file}")
        print("📝 Отредактируйте файл, добавив нужные аккаунты Twitter")

        edit_now = input("\nОткрыть файл для редактирования? (да/нет): ").lower()
        if edit_now in ['да', 'yes', 'y', 'д']:
            try:
                if sys.platform.startswith('darwin'):  # macOS
                    os.system(f'open -t {accounts_file}')
                elif sys.platform.startswith('linux'):  # Linux
                    os.system(f'xdg-open {accounts_file}')
                elif sys.platform.startswith('win'):  # Windows
                    os.system(f'notepad {accounts_file}')
            except Exception as e:
                print(f"Не удалось открыть файл: {e}")
                print(f"Откройте файл {accounts_file} вручную")

    # Проверка профиля Chrome
    chrome_profile = get_chrome_profile_path()
    if not chrome_profile:
        print("\n⚠️ Профиль Chrome не найден автоматически")
        custom_path = input("Введите путь к профилю Chrome (или Enter для пропуска): ").strip()
        if custom_path and os.path.exists(custom_path):
            chrome_profile = custom_path
            print(f"✅ Будет использован: {chrome_profile}")

    print("\n🚀 Настройка завершена! Запускаю парсер...")
    return chrome_profile


if __name__ == "__main__":
    try:
        # Интерактивная настройка при первом запуске
        if len(sys.argv) > 1 and sys.argv[1] == '--setup':
            chrome_profile = interactive_setup()

        # Запуск парсера
        success = main()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("\n⏹️ Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        import traceback

        logger.error(traceback.format_exc())
        sys.exit(1)