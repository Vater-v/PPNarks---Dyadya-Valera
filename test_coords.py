# test_coords.py
# Тестер для coords.get_coords: печатает координаты from->to для разных сценариев
# Запуск:
#   python test_coords.py
#   python test_coords.py --config path/to/board_config.json

import argparse
import json
from typing import Any, Dict, Tuple, Optional

from coords import get_coords  # важно: coords.py должен лежать рядом

Point = Tuple[int, int]

# ---------- УТИЛЫ ----------

def get_in(d: Dict[str, Any], path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def load_board_cfg(path: Optional[str]) -> Dict[str, Any]:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    # ----- МОК КОНФИГ -----
    # Координаты условные, сетка 50px, высота стека 18px.
    # 1..12 снизу слева->справа, 13..24 сверху справа->слева (как пример).
    settings = {"checker_step_y": 18}
    points = {}
    # нижняя линия: пункты 1..12 растут "вверх" (direction = -1 чтобы складывать вверх при base внизу)
    x0, y_bottom = 40, 540
    for i in range(1, 13):
        points[str(i)] = {
            "base_coords": [x0 + (i - 1) * 40, y_bottom],
            "direction": -1
        }
    # верхняя линия: пункты 13..24 растут "вниз"
    y_top = 60
    for idx, p in enumerate(range(13, 25), start=0):
        # справа->слева для разнообразия
        points[str(p)] = {
            "base_coords": [x0 + (11 - idx) * 40, y_top],
            "direction": 1
        }

    bar = {
        "hero":      {"base_coords": [x0 + 12 * 40 + 20, 300], "step_y": 18, "direction": -1},
        "opponent":  {"base_coords": [x0 - 20, 300],            "step_y": 18, "direction": 1},
    }
    special_points = {
        "off": {
            "hero":     {"x": x0 + 12 * 40 + 60, "y": 300},
            "opponent": {"x": x0 - 60,           "y": 300},
        }
    }
    return {"settings": settings, "points": points, "bar": bar, "special_points": special_points}

def print_move(title: str, from_key: str, to_key: str,
               from_xy: Optional[Point], to_xy: Optional[Point],
               extra=""):
    def fmt(p):
        return "None" if p is None else f"({p[0]}, {p[1]})"
    print(f"\n[{title}] {from_key} -> {to_key}")
    print(f"  from: {fmt(from_xy)}")
    print(f"  to  : {fmt(to_xy)}")
    if from_xy and to_xy:
        dx, dy = to_xy[0] - from_xy[0], to_xy[1] - from_xy[1]
        print(f"  Δ    : (dx={dx}, dy={dy})")
    if extra:
        print(f"  note : {extra}")

# ---------- ПРИМЕР СОСТОЯНИЙ ----------

def initial_like_state(hero_id: str, opp_id: str) -> Dict[str, Any]:
    # Синтетика для тестов; достаточно номеров, владельцев и стеков
    return {
        "players": {
            "first": {"userId": hero_id},    # герой ходит как первый; для инверсии будем менять
            "second": {"userId": opp_id},
        },
        "barCounts": {hero_id: 0, opp_id: 0},
        "points": [
            {"number": 1,  "checkersCount": 2, "occupiedBy": hero_id},
            {"number": 6,  "checkersCount": 5, "occupiedBy": hero_id},
            {"number": 8,  "checkersCount": 3, "occupiedBy": hero_id},
            {"number": 12, "checkersCount": 5, "occupiedBy": hero_id},
            {"number": 24, "checkersCount": 1, "occupiedBy": opp_id},  # blot оппонента
            {"number": 13, "checkersCount": 3, "occupiedBy": opp_id},
            {"number": 17, "checkersCount": 2, "occupiedBy": opp_id},
            {"number": 19, "checkersCount": 5, "occupiedBy": opp_id},
        ]
    }

def state_with_bar(hero_id: str, opp_id: str) -> Dict[str, Any]:
    s = initial_like_state(hero_id, opp_id)
    s["barCounts"][hero_id] = 2
    return s

def state_for_bearing_off(hero_id: str, opp_id: str) -> Dict[str, Any]:
    # все шашки героя в доме (1..6) — упростим: только на 1 и 2
    return {
        "players": {
            "first": {"userId": hero_id},
            "second": {"userId": opp_id},
        },
        "barCounts": {hero_id: 0, opp_id: 0},
        "points": [
            {"number": 1, "checkersCount": 4, "occupiedBy": hero_id},
            {"number": 2, "checkersCount": 8, "occupiedBy": hero_id},
            {"number": 7, "checkersCount": 0},
            {"number": 24, "checkersCount": 3, "occupiedBy": opp_id},
        ]
    }

# ---------- ТЕСТ-КЕЙСЫ ----------

def run_cases(board_cfg: Dict[str, Any]):
    HERO = "hero"
    OPP  = "opponent"

    # 1) Обычный ход: из стека с n>1, без инверсии
    bs1 = initial_like_state(HERO, OPP)  # hero == first -> без инверсии
    f = get_coords("6", bs1, hero_id=HERO, board_cfg=board_cfg, is_source=True)
    t = get_coords("1", bs1, hero_id=HERO, board_cfg=board_cfg, is_source=False)
    print_move("regular", "6", "1", f, t, "Ожидаем разные y; to — на вершину стека пункта 1")

    # sanity asserts
    assert f is not None and t is not None
    assert t[1] < f[1] or t[1] > f[1]  # просто чтобы координаты не совпали случайно

    # 2) Ход с взятием (hit): цель — чужой blot (count==1)
    f2 = get_coords("8", bs1, hero_id=HERO, board_cfg=board_cfg, is_source=True)
    t2 = get_coords("24", bs1, hero_id=HERO, board_cfg=board_cfg, is_source=False)
    print_move("hit blot", "8", "24", f2, t2, "Целевая позиция должна класться в stack_pos=0 для взятия")

    assert f2 and t2

    # 3) Инверсия ракурса: герой НЕ первый игрок
    bs2 = initial_like_state(HERO, OPP)
    bs2["players"]["first"]["userId"] = OPP  # теперь герой «снизу» (invert=True в предлагаемой логике)
    f3 = get_coords("6", bs2, hero_id=HERO, board_cfg=board_cfg, is_source=True)
    t3 = get_coords("1", bs2, hero_id=HERO, board_cfg=board_cfg, is_source=False)
    print_move("inverted perspective", "6", "1", f3, t3, "X координаты должны отличаться от случая без инверсии")

    assert f3 and t3
    # при инверсии часто меняются X (зеркалятся)
    assert f3[0] != f[0] or t3[0] != t[0]

    # 4) Ход с бара: источник = 'bar' (у героя 2 шашки на баре)
    bs3 = state_with_bar(HERO, OPP)
    f4 = get_coords("bar", bs3, hero_id=HERO, board_cfg=board_cfg, is_source=True)
    t4 = get_coords("24",  bs3, hero_id=HERO, board_cfg=board_cfg, is_source=False)
    print_move("from bar", "bar", "24", f4, t4, "Источник берёт верхнюю шашку с бара")

    assert f4 and t4

    # 5) Ход на бар (моделируем как цель 'bar' для проверки координат укладки)
    # Обычно на бар отправляет логика взятия, но мы просто сверим координату цели бара при is_source=False
    t5 = get_coords("bar", bs3, hero_id=HERO, board_cfg=board_cfg, is_source=False)
    print_move("to bar (target slot check)", "24*", "bar", None, t5, "Должна быть позиция укладки на баре")

    assert t5

    # 6) Снятие шашки (bearing off): цель 'off'
    bs4 = state_for_bearing_off(HERO, OPP)
    f6 = get_coords("2", bs4, hero_id=HERO, board_cfg=board_cfg, is_source=True)
    t6 = get_coords("off", bs4, hero_id=HERO, board_cfg=board_cfg, is_source=False)
    print_move("bearing off", "2", "off", f6, t6, "Проверка special_points.off (hero/opponent)")

    assert f6 and t6

    # 7) Пустой источник: берём с пустого пункта -> None
    # делаем пункт 7 пустым явно; is_source=True -> None
    f7 = get_coords("7", bs1, hero_id=HERO, board_cfg=board_cfg, is_source=True)
    print_move("empty source", "7", "1", f7, None, "Источник пуст => None")
    assert f7 is None

    # 8) Переполнение стека на цели (визуальная проверка смещения):
    # ставим 10 шашек на пункт 1 и кладём ещё одну — проверим корректность step/смещения
    bs_over = initial_like_state(HERO, OPP)
    for p in bs_over["points"]:
        if str(p["number"]) == "1":
            p["checkersCount"] = 10
            p["occupiedBy"] = HERO
            break
    f8 = get_coords("6", bs_over, hero_id=HERO, board_cfg=board_cfg, is_source=True)
    t8 = get_coords("1", bs_over, hero_id=HERO, board_cfg=board_cfg, is_source=False)
    print_move("tall stack", "6", "1", f8, t8, "Цель должна быть base + 10*step*direction")
    assert f8 and t8
    base = board_cfg["points"]["1"]["base_coords"]
    dir1 = board_cfg["points"]["1"]["direction"]
    step = board_cfg["settings"]["checker_step_y"]
    expected_y = base[1] + 10 * step * dir1
    assert t8[1] == expected_y, f"ожидался y={expected_y}, а пришёл {t8[1]}"

    print("\nВсе кейсы прошли без assert-ошибок ✅")

def main():
    ap = argparse.ArgumentParser(description="Tester for coords.get_coords")
    ap.add_argument("--config", type=str, default=None, help="path to board_config.json (optional)")
    args = ap.parse_args()

    board_cfg = load_board_cfg(args.config)
    run_cases(board_cfg)

if __name__ == "__main__":
    main()
