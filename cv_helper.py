# cv_helper.py
import cv2
import numpy as np

try:
    TEMPLATE_AUTO_ON = cv2.imread('auto_on.png', 0)
    TEMPLATE_AUTO_OFF = cv2.imread('auto_off.png', 0)
    if TEMPLATE_AUTO_ON is None or TEMPLATE_AUTO_OFF is None:
        raise FileNotFoundError("Один или оба файла-шаблона (auto_on.png, auto_off.png) не найдены.")
except Exception as e:
    print(f"[CV_HELPER] КРИТИЧЕСКАЯ ОШИБКА при загрузке шаблонов: {e}")
    TEMPLATE_AUTO_ON, TEMPLATE_AUTO_OFF = None, None

def take_screenshot(device) -> np.ndarray | None:
    """Делает скриншот с устройства и возвращает его как объект OpenCV в градациях серого."""
    try:
        result = device.screencap()
        screenshot = cv2.imdecode(np.frombuffer(result, np.uint8), cv2.IMREAD_GRAYSCALE)
        return screenshot
    except Exception as e:
        print(f"[CV_HELPER] Не удалось сделать скриншот: {e}")
        return None

def find_button_state(
    device,
    confidence_threshold: float = 0.70
) -> tuple[str, tuple[int, int] | None, float]:
    """
    Ищет кнопку авто-броска по ВСЕМУ ЭКРАНУ, определяет её состояние и точные координаты.

    :param device: ADB устройство.
    :param confidence_threshold: Минимальный порог уверенности для принятия решения.
    :return: Кортеж (state, center_coords, confidence):
             - state: 'on', 'off' или 'unknown'.
             - center_coords: (x, y) центра найденной кнопки или None.
             - confidence: Максимальная обнаруженная уверенность (от 0.0 до 1.0).
    """
    if TEMPLATE_AUTO_ON is None or TEMPLATE_AUTO_OFF is None:
        print("[CV_HELPER] Шаблоны не загружены, проверка невозможна.")
        return 'unknown', None, 0.0

    screenshot = take_screenshot(device)
    if screenshot is None:
        return 'unknown', None, 0.0

    # 1. Ищем оба шаблона на полном скриншоте
    res_on = cv2.matchTemplate(screenshot, TEMPLATE_AUTO_ON, cv2.TM_CCOEFF_NORMED)
    min_val_on, max_val_on, min_loc_on, max_loc_on = cv2.minMaxLoc(res_on)

    res_off = cv2.matchTemplate(screenshot, TEMPLATE_AUTO_OFF, cv2.TM_CCOEFF_NORMED)
    min_val_off, max_val_off, min_loc_off, max_loc_off = cv2.minMaxLoc(res_off)

    # 2. Определяем, какое состояние имеет большую уверенность
    if max_val_on > max_val_off:
        best_confidence = max_val_on
        best_state = 'on'
        best_loc = max_loc_on
        template_h, template_w = TEMPLATE_AUTO_ON.shape
    else:
        best_confidence = max_val_off
        best_state = 'off'
        best_loc = max_loc_off
        template_h, template_w = TEMPLATE_AUTO_OFF.shape

    # 3. Применяем защиту от ложных срабатываний
    if best_confidence < confidence_threshold:
        return 'unknown', None, best_confidence

    # 4. Рассчитываем координаты центра найденной кнопки
    center_x = best_loc[0] + template_w // 2
    center_y = best_loc[1] + template_h // 2
    
    return best_state, (center_x, center_y), best_confidence