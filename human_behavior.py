#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для имитации человеческого поведения при работе с браузером
Содержит функции для естественных движений мыши, скроллинга, задержек
"""

import time
import random
import logging
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)


class HumanBehaviorSimulator:
    """Класс для имитации поведения реального пользователя"""

    def __init__(self, driver, config=None):
        self.driver = driver
        self.last_action_time = time.time()
        self.session_start_time = time.time()
        self.total_actions = 0
        self.page_views = 0

        # Настройки по умолчанию
        self.config = config or {
            'delays': {
                'between_actions': (1, 3),
                'reading_pause': (2, 8),
                'typing_speed': (0.05, 0.2),
                'long_break': (60, 180),
                'scroll_pause': (0.1, 0.3),
            },
            'probabilities': {
                'scroll_back': 0.15,
                'mouse_movement': 0.25,
                'tab_switching': 0.1,
            }
        }

    def get_random_delay(self, delay_type='between_actions'):
        """Получить случайную задержку определенного типа"""
        if delay_type in self.config['delays']:
            min_val, max_val = self.config['delays'][delay_type]
            return random.uniform(min_val, max_val)
        return random.uniform(1, 3)

    def should_perform_action(self, action_type):
        """Определить, следует ли выполнить действие на основе вероятности"""
        return self.config['probabilities'].get(action_type, 0.2) > random.random()

    def random_delay(self, delay_type='between_actions'):
        """Случайная задержка между действиями"""
        delay = self.get_random_delay(delay_type)
        time.sleep(delay)
        self.last_action_time = time.time()
        return delay

    def human_type(self, element, text):
        """Имитация человеческой печати с случайными задержками"""
        try:
            typing_speed_range = self.config['delays']['typing_speed']
            for char in text:
                element.send_keys(char)
                delay = random.uniform(*typing_speed_range)
                time.sleep(delay)
            logger.debug(f"Напечатан текст: {text[:20]}...")
        except Exception as e:
            logger.warning(f"Ошибка при печати: {e}")

    def human_scroll(self, scroll_type='smooth', distance=None):
        """Имитация человеческого скроллинга"""
        try:
            if distance is None:
                distance = random.randint(300, 800)

            if scroll_type == 'smooth':
                # Плавный скроллинг небольшими порциями
                steps = random.randint(5, 12)
                step_size = distance // steps

                for i in range(steps):
                    self.driver.execute_script(f"window.scrollBy(0, {step_size});")
                    scroll_pause = self.get_random_delay('scroll_pause')
                    time.sleep(scroll_pause)

            elif scroll_type == 'wheel':
                # Имитация колесика мыши
                for _ in range(random.randint(3, 8)):
                    scroll_distance = random.randint(100, 200)
                    self.driver.execute_script(f"window.scrollBy(0, {scroll_distance});")
                    time.sleep(random.uniform(0.2, 0.5))

            # Иногда скроллим обратно (как делают люди)
            if self.should_perform_action('scroll_back'):
                back_distance = random.randint(50, 200)
                self.driver.execute_script(f"window.scrollBy(0, -{back_distance});")
                time.sleep(random.uniform(0.5, 1.0))
                logger.debug("Выполнен обратный скроллинг")

        except Exception as e:
            logger.warning(f"Ошибка при скроллинге: {e}")

    def simulate_reading_pause(self, content_length=100):
        """Имитация паузы на чтение контента"""
        try:
            # Базовое время чтения: ~200 слов в минуту
            words_count = max(content_length / 5, 10)  # примерно 5 символов на слово
            estimated_reading_time = words_count / 200 * 60  # в секундах
            estimated_reading_time = max(estimated_reading_time, 2)  # минимум 2 секунды

            # Добавляем случайность в время чтения
            actual_pause = random.uniform(
                estimated_reading_time * 0.3,
                estimated_reading_time * 0.8
            )
            time.sleep(actual_pause)
            logger.debug(f"Пауза на чтение: {actual_pause:.1f}с для {content_length} символов")

        except Exception as e:
            logger.warning(f"Ошибка при паузе на чтение: {e}")

    def random_mouse_movement(self):
        """Случайные движения мыши"""
        try:
            if not self.should_perform_action('mouse_movement'):
                return

            action = ActionChains(self.driver)

            # Находим случайный элемент для наведения
            elements = self.driver.find_elements(By.TAG_NAME, "div")[:10]
            if elements:
                target_element = random.choice(elements)
                action.move_to_element(target_element)
                action.perform()
                time.sleep(random.uniform(0.5, 1.5))
                logger.debug("Выполнено случайное движение мыши")

        except Exception as e:
            logger.debug(f"Ошибка движения мыши (игнорируется): {e}")

    def simulate_user_interest(self):
        """Имитация заинтересованности пользователя"""
        try:
            interest_actions = [
                self.random_hover_on_tweets,
                self.simulate_tab_switching,
                self.random_mouse_movement,
                self.check_page_title
            ]

            if random.random() < 0.3:  # 30% вероятность
                action = random.choice(interest_actions)
                action()
                logger.debug("Выполнено действие имитации интереса")

        except Exception as e:
            logger.debug(f"Ошибка при имитации интереса: {e}")

    def random_hover_on_tweets(self):
        """Случайное наведение на твиты"""
        try:
            tweets = self.driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')[:5]
            if tweets:
                tweet = random.choice(tweets)
                ActionChains(self.driver).move_to_element(tweet).perform()
                time.sleep(random.uniform(1, 3))
                logger.debug("Наведение на случайный твит")
        except Exception as e:
            logger.debug(f"Ошибка наведения на твит: {e}")

    def simulate_tab_switching(self):
        """Имитация переключения между вкладками"""
        try:
            if not self.should_perform_action('tab_switching'):
                return

            original_handles = self.driver.window_handles[:]

            # Открываем новую вкладку
            self.driver.execute_script("window.open('about:blank', '_blank');")
            time.sleep(random.uniform(1, 2))

            # Переключаемся обратно
            self.driver.switch_to.window(original_handles[0])
            time.sleep(random.uniform(0.5, 1))

            # Закрываем лишнюю вкладку
            new_handles = self.driver.window_handles
            if len(new_handles) > len(original_handles):
                self.driver.switch_to.window(new_handles[-1])
                self.driver.close()
                self.driver.switch_to.window(original_handles[0])
                logger.debug("Выполнено переключение вкладок")

        except Exception as e:
            logger.debug(f"Ошибка переключения вкладок: {e}")

    def check_page_title(self):
        """Проверка заголовка страницы (имитация внимания)"""
        try:
            title = self.driver.title
            time.sleep(random.uniform(0.2, 0.5))
            logger.debug(f"Проверен заголовок: {title[:30]}...")
        except Exception as e:
            logger.debug(f"Ошибка проверки заголовка: {e}")

    def take_break(self, break_type='long_break'):
        """Длинная пауза для имитации отдыха пользователя"""
        try:
            # Проверяем, нужен ли перерыв
            if self.total_actions % random.randint(50, 100) == 0:
                break_duration = self.get_random_delay(break_type)
                logger.info(f"Перерыв на {break_duration:.1f} секунд (действий выполнено: {self.total_actions})")
                time.sleep(break_duration)
        except Exception as e:
            logger.warning(f"Ошибка во время перерыва: {e}")

    def session_health_check(self):
        """Проверка состояния сессии и имитация естественных пауз"""
        try:
            current_time = time.time()
            session_duration = current_time - self.session_start_time

            # Каждые 10 минут делаем паузу
            if session_duration > 600 and session_duration % 600 < 60:
                self.take_break('long_break')

            # Увеличиваем счетчик действий
            self.total_actions += 1

            # Логируем состояние сессии
            if self.total_actions % 50 == 0:
                logger.info(f"Состояние сессии: {self.total_actions} действий за {session_duration / 60:.1f} мин")

        except Exception as e:
            logger.warning(f"Ошибка проверки состояния сессии: {e}")

    def anti_detection_scroll(self):
        """Продвинутый скроллинг с защитой от обнаружения"""
        try:
            # Случайный выбор типа скроллинга
            scroll_types = ['smooth', 'wheel']
            scroll_type = random.choice(scroll_types)

            # Варьируем дистанцию скроллинга
            distances = [300, 400, 500, 600, 700, 800]
            distance = random.choice(distances)

            # Иногда делаем несколько небольших скроллов вместо одного большого
            if random.random() < 0.4:
                small_scrolls = random.randint(2, 4)
                small_distance = distance // small_scrolls
                for _ in range(small_scrolls):
                    self.human_scroll(scroll_type, small_distance)
                    time.sleep(random.uniform(0.5, 1.5))
            else:
                self.human_scroll(scroll_type, distance)

            # Случайная пауза после скроллинга
            self.random_delay('between_actions')

        except Exception as e:
            logger.warning(f"Ошибка при продвинутом скроллинге: {e}")

    def natural_click(self, element):
        """Естественный клик с имитацией движения мыши"""
        try:
            # Наведение мыши с небольшой задержкой
            ActionChains(self.driver).move_to_element(element).perform()
            time.sleep(random.uniform(0.1, 0.3))

            # Клик с небольшой паузой
            ActionChains(self.driver).click(element).perform()
            self.random_delay('between_actions')

            logger.debug("Выполнен естественный клик")

        except Exception as e:
            logger.warning(f"Ошибка естественного клика: {e}")
            # Fallback на обычный клик
            try:
                element.click()
            except Exception as fallback_error:
                logger.error(f"Fallback клик тоже не удался: {fallback_error}")

    def get_session_stats(self):
        """Получить статистику текущей сессии"""
        current_time = time.time()
        session_duration = current_time - self.session_start_time

        return {
            'session_duration_minutes': session_duration / 60,
            'total_actions': self.total_actions,
            'actions_per_minute': self.total_actions / max(session_duration / 60, 1),
            'page_views': self.page_views
        }