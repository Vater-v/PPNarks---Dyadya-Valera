import time
import random
from typing import Optional, Dict
from ppadb.client import Client as AdbClient
import cv_helper
import os
import math

HUMANIZER_CONFIG = {
    "enabled": True,
    "multipliers": [
        {"min": 0.7475, "max": 0.9775, "weight": 40, "name": "Быстрый"},
        {"min": 0.9775, "max": 1.3225, "weight": 40, "name": "Спокойный"},
        {"min": 1.3225, "max": 1.7825, "weight": 10, "name": "Задумчивый"},
        {"min": 1.7825, "max": 2.7025, "weight": 10, "name": "Медленный"},
    ]
}
TIMING_CONFIG = {

    # --- Основные действия в игре ---
    "before_first_move": [0.85, 1.35],
    "before_double_decision": [0.8, 3.5],     # Пауза перед принятием решения о дабле (раздумье)
    "before_double_answer_click": [1, 6], # Пауза перед ответом на предложение дабла (раздумье)
    "between_double_clicks": [0.35, 1],    # Пауза между двумя кликами при отправке дабла
    "after_double_animations": [3.3, 4.7],

    # --- Перемещение шашек ---
    "before_checker_click": [0.4, 0.6],      # Короткая пауза ПЕРЕД кликом по шашке или полю.
    "between_separate_moves": [0.95, 1.25],    # Пауза между отдельными ходами (например, 6/12 и 13/18).
    "checker_swipe_duration": [400, 500],

    # --- Навигация и прочее ---
    "lobby_enter_game_step": [0.8, 1.2],     # Пауза между кликами при входе в игру из лобби.
    "smile_panel_open_wait": [0.4, 0.6],     # Пауза после открытия панели смайлов.
    "toggle_auto_roll": [0.3, 0.5],          # Пауза после переключения авто-броска.

    # --- Системные задержки ---
    "adb_connection_retry": [4.0, 6.0],      # Пауза перед повторной попыткой подключения к ADB.
    "config_load_retry": [1.5, 2.5],         # Пауза перед повторной попыткой загрузки конфига доски.
}


# --- ОБЩАЯ КОНФИГУРАЦИЯ ---
CONFIG = {
    "adb_host": "127.0.0.1",
    "adb_port": 5037,
    "board_config_path": "board_config.json",
    "coords": {
        # Координаты кнопок и других элементов интерфейса
        "off": {"x": 410, "y": 930},
        "roll_swipe": {"start_x": 425, "start_y": 845, "end_x": 380, "end_y": 850, "duration": 200},
        "turn_commit_btn": {"x": 410, "y": 650},
        "double_send_btn": {"x": 290, "y": 305},
        "double_confirm_yes_btn": {"x": 400, "y": 570},
        "double_confirm_no_btn": {"x": 140, "y": 570},
        "double_offer_take_btn": {"x": 415, "y": 275},
        "double_offer_pass_btn": {"x": 125, "y": 275},
        "exit_giveup_btn": {"x": 35, "y": 35},
        "smile_button": {"x": 465, "y": 305},
        "from_lobby_step_1": {"x": 270, "y": 895},
        "from_lobby_step_2": {"x": 270, "y": 815},
        "smile_panel": {"x_min": 80, "y_min": 445, "x_max": 465, "y_max": 830},
        "deselect_click_point": {"x": 270, "y": 80}, # Точка для клика, чтобы снять выделение с шашки
    }
}



def get_delay(key: str) -> float:
    """
    Получает задержку из TIMING_CONFIG.
    Возвращает случайное значение в диапазоне [min, max].
    """
    min_delay, max_delay = TIMING_CONFIG.get(key, [0.1, 0.2]) # Безопасное значение по умолчанию
    if min_delay >= max_delay:
        return min_delay
    return random.uniform(min_delay, max_delay)

class Action:
    def execute(self, device) -> None:
        print(f"[CLICKER] {self}")
        self._execute_action(device)
    
    def _execute_action(self, device) -> None:
        raise NotImplementedError
    
    def __repr__(self):
        return self.__class__.__name__

class ClickAction(Action):
    """Класс для клика. Больше не содержит встроенных задержек."""
    def __init__(self, x: int, y: int):
        self.x, self.y = x, y
    
    def _execute_action(self, device) -> None:
        if device:
            device.shell(f"input tap {self.x} {self.y}")
    
    def __repr__(self):
        return f"Клик: ({self.x}, {self.y})"

class SwipeAction(Action):
    def __init__(self, start_x, start_y, end_x, end_y, duration):
        self.start_x, self.start_y, self.end_x, self.end_y, self.duration = start_x, start_y, end_x, end_y, duration
    
    def _execute_action(self, device) -> None:
        if device:
            device.shell(f"input swipe {self.start_x} {self.start_y} {self.end_x} {self.end_y} {self.duration}")
    
    def __repr__(self):
        return f"Свайп: ({self.start_x},{self.start_y}) -> ({self.end_x},{self.end_y})"

class LogAction(Action):
    def __init__(self, message: str):
        self.message = message
    
    def execute(self, device) -> None:
        #print(f"[CLICKER] {self.message}")
        pass
    
    def __repr__(self):
        return f"Команда: {self.message}"

# --- ПОДКЛЮЧЕНИЕ К ЭМУЛЯТОРУ ---
def connect_to_emulator(host: str, port: int, target_device_id: str):
    """Подключается к конкретному эмулятору по его ID."""
    try:
        client = AdbClient(host=host, port=port)
        # Пытаемся получить устройство по его "адресу"
        device = client.device(target_device_id)
        if device:
            return device
        
        print(f"Эмулятор '{target_device_id}' не найден. Проверьте adb devices.")
        return None
    except Exception as e:
        print(f"Ошибка подключения к ADB ({target_device_id}): {e}")
        return None



# --- ОСНОВНОЙ КЛАСС КЛИКЕРА ---
class Clicker:
    def __init__(self, max_retries=None):
        self.device = None
        self.current_turn_multiplier = 1.0
        self.cached_match_autoroll_coords = None
        self.latest_turn_token = None
        self.double_just_resolved = False

        target_emulator_id = os.getenv("TARGET_EMULATOR")
        if not target_emulator_id:
            raise Exception("КРИТИЧЕСКАЯ ОШИБКА: ID эмулятора (TARGET_EMULATOR) не установлен.")
        
        retry_count = 0
        while True:
            try:
                self.device = connect_to_emulator(CONFIG["adb_host"], CONFIG["adb_port"], target_emulator_id)
                if self.device:
                    print(f"✓ Подключено к целевому эмулятору: {target_emulator_id}")
                    break
                else:
                    raise Exception(f"Не удалось найти эмулятор {target_emulator_id}")
            except Exception as e:
                retry_count += 1
                print(f"⚠ Попытка {retry_count}: Не удалось подключиться к ADB: {e}")
                time.sleep(get_delay("adb_connection_retry")) # Используем глобальную функцию
                if max_retries and retry_count >= max_retries:
                    raise Exception("Превышено максимальное количество попыток подключения")
        
        if not self.device:
            raise Exception("КРИТИЧЕСКАЯ ОШИБКА: Невозможно инициализировать автокликер")
        print("✓ Автокликер успешно инициализирован и готов к работе")

    def update_turn_token(self, new_token):
        self.latest_turn_token = new_token

    def generate_new_turn_multiplier(self):
        if not HUMANIZER_CONFIG.get("enabled"):
            self.current_turn_multiplier = 1.0
            return
        config = HUMANIZER_CONFIG["multipliers"]
        population = config
        weights = [item.get("weight", 1) for item in config]
        chosen_range = random.choices(population, weights, k=1)[0]
        min_mult, max_mult = chosen_range.get("min", 1.0), chosen_range.get("max", 1.1)
        self.current_turn_multiplier = random.uniform(min_mult, max_mult)
        mode_name = chosen_range.get('name', 'Default')
        print(f"[HUMANIZER] 💓 Новый ритм хода: {mode_name} (множитель x{self.current_turn_multiplier:.2f})")

    def get_delay(self, key: str) -> float:
        min_delay, max_delay = TIMING_CONFIG.get(key, [0.1, 0.2])
        base_delay = random.uniform(min_delay, max_delay) if min_delay < max_delay else min_delay
        return base_delay * self.current_turn_multiplier

    def _execute(self, actions):
        if not isinstance(actions, list): actions = [actions]
        for action in actions:
            try: action.execute(self.device)
            except Exception as e: print(f"[CLICKER][ERROR] Ошибка выполнения действия {action}: {e}")

    def _execute_click(self, x, y):
        time.sleep(self.get_delay("before_checker_click"))
        self._execute(ClickAction(x, y))

    def move_checkers(self, moves_with_coords: list[dict], turn_token: any):
        """
        Просто выполняет свайпы по готовым координатам.
        moves_with_coords = [{'from': (x,y), 'to': (x,y), 'move_str': '6/off'}, ...]
        """
        if self.double_just_resolved:
            time.sleep(self.get_delay("after_double_animations"))
            self.double_just_resolved = False

        time.sleep(self.get_delay("before_first_move"))

        for move_data in moves_with_coords:
            if self.latest_turn_token != turn_token:
                print("[CLICKER] Токен хода устарел. Отмена выполнения.")
                return

            from_coords = move_data['from']
            to_coords = move_data['to']
            move_str = move_data['move_str']

            x1, y1 = from_coords
            x2, y2 = to_coords
            
            inertia_pixels = 8
            distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            
            if distance > 0:
                inertial_x = round(x2 + inertia_pixels * ((x2 - x1) / distance))
                inertial_y = round(y2 + inertia_pixels * ((y2 - y1) / distance))
            else:
                inertial_x, inertial_y = x2, y2

            min_dur, max_dur = TIMING_CONFIG["checker_swipe_duration"]
            duration_ms = int(random.uniform(min_dur, max_dur))

            swipe_action = SwipeAction(x1, y1, inertial_x, inertial_y, duration_ms)
            
            self._execute(LogAction(f"Перемещаю {move_str} свайпом ({duration_ms}ms)"))
            self._execute(swipe_action)
            time.sleep(self.get_delay("between_separate_moves"))

    def roll_dice(self):
        time.sleep(0.3)
        c = CONFIG["coords"]["roll_swipe"]
        swipe_action = SwipeAction(c['start_x'], c['start_y'], c['end_x'], c['end_y'], c['duration'])
        self._execute(swipe_action)

    def turn_commit(self):
        c = CONFIG["coords"]["turn_commit_btn"]
        #time.sleep(self.get_delay("before_checker_click"))
        self._execute_click(c['x'], c['y'])

    def send_double(self):
        c_send = CONFIG["coords"]["double_send_btn"]
        c_yes = CONFIG["coords"]["double_confirm_yes_btn"]
        time.sleep(self.get_delay("before_double_decision"))
        self._execute_click(c_send['x'], c_send['y'])
        time.sleep(self.get_delay("between_double_clicks"))
        self._execute_click(c_yes['x'], c_yes['y'])
        self.double_just_resolved = True

    def take_double(self):
        c = CONFIG["coords"]["double_offer_take_btn"]
        time.sleep(self.get_delay("before_double_answer_click"))
        self._execute_click(c['x'], c['y'])
        self.double_just_resolved = True

    def pass_double(self):
        c = CONFIG["coords"]["double_offer_pass_btn"]
        time.sleep(self.get_delay("before_double_answer_click"))
        self._execute_click(c['x'], c['y'])
        self.double_just_resolved = True

    # Функции для CV (поиск кнопки) не меняются
    def find_and_cache_autoroll_button(self):
        print("[CLICKER] Выполняю первоначальный поиск кнопки авто-броска для кэширования...")
        state, coords, confidence = cv_helper.find_button_state(self.device)
        if state != 'unknown' and coords:
            self.cached_match_autoroll_coords = coords
            print(f"[CLICKER] ✓ Координаты кнопки ({coords}) сохранены на весь матч.")
            return True
        else:
            print("[CLICKER] ⚠ Не удалось найти кнопку для кэширования.")
            self.cached_match_autoroll_coords = None
            return False

    def clear_autoroll_cache(self):
        if self.cached_match_autoroll_coords:
            print("[CLICKER] Кэш координат кнопки авто-броска сброшен.")
        self.cached_match_autoroll_coords = None

    def is_auto_roll_enabled(self) -> Optional[bool]:
        if not self.device: return None
        state, coords, confidence = cv_helper.find_button_state(self.device)
        if state == 'on': return True
        elif state == 'off': return False
        else: return None

    def toggle_auto_roll(self):
        if not self.cached_match_autoroll_coords:
            if not self.find_and_cache_autoroll_button():
                print("[CLICKER] Клик отменен: координаты кнопки авто-броска неизвестны.")
                return
        coords = self.cached_match_autoroll_coords
        self._execute_click(coords[0], coords[1])
        time.sleep(self.get_delay("toggle_auto_roll"))
