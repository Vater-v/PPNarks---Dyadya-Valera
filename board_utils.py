# board_utils.py
from typing import Dict, Tuple
from collections import defaultdict
from coords import get_coords # Эта функция уже используется в _coords_dynamic

def _mirror_y(y: int, cfg: dict) -> int:
    """Зеркалит координату Y относительно высоты доски."""
    H = cfg.get("board_pixel_height")
    if not H:
        raise RuntimeError("board_pixel_height отсутствует в board_config.json")
    return H - y

def simulate_move(board: dict, from_point_str: str, to_point_str: str, hero_id: str) -> dict:
    """
    Корректная симуляция: снимаем с источника (bar или пункт),
    затем кладём на цель (hit при одиночной чужой, off — в offCounts).
    """
    if not board:
        return {}

    bar_counts = board.setdefault('barCounts', {})
    opp_id = next((pid for pid in bar_counts.keys() if pid != hero_id), None)

    if from_point_str == 'bar':
        bar_counts[hero_id] = max(0, bar_counts.get(hero_id, 0) - 1)
    else:
        for point in board.get('points', []):
            if str(point.get("number")) == from_point_str:
                if point.get('occupiedBy') == hero_id:
                    cnt = max(0, (point.get('checkersCount') or 0) - 1)
                    point['checkersCount'] = cnt
                    if cnt == 0:
                        point.pop('occupiedBy', None)
                break

    if to_point_str == 'off':
        off_map = board.setdefault('offCounts', {})
        off_map[hero_id] = off_map.get(hero_id, 0) + 1
        return board

    target = None
    for p in board.get('points', []):
        if str(p.get("number")) == to_point_str:
            target = p
            break

    if target:
        their = target.get('occupiedBy')
        cnt = target.get('checkersCount', 0) or 0
        if their and their != hero_id and cnt == 1:
            if opp_id:
                bar_counts[opp_id] = bar_counts.get(opp_id, 0) + 1
            target['occupiedBy'] = hero_id
            target['checkersCount'] = 1
        else:
            target['occupiedBy'] = hero_id
            target['checkersCount'] = cnt + 1
    else:
        board.setdefault('points', []).append({
            "number": int(to_point_str), "occupiedBy": hero_id, "checkersCount": 1
        })
    return board

def _point_checker_count(board: dict, player_id: str, point_str: str) -> int:
    """Текущее кол-во НАШИХ шашек на пункте (или на баре)."""
    if point_str == "bar":
        return board.get("barCounts", {}).get(player_id, 0) or 0
    if point_str == "off":
        return 0
    for p in board.get("points", []):
        if str(p.get("number")) == point_str and p.get("occupiedBy") == player_id:
            return p.get("checkersCount", 0) or 0
    return 0

def coords_dynamic(point_str: str, is_source: bool,
                   local_taken: defaultdict, local_placed: defaultdict,
                   board: dict, hero_id: str, cfg: dict,
                   mirror_y: bool) -> tuple[int, int] | None:
    """Считает пиксели с учётом уже взятых/положенных в ЭТОМ ходу шашек."""
    base = get_coords(point_str, board, hero_id, cfg, is_source=is_source)
    if not base:
        return None
    x, y = base
    
    # Логика сдвига и зеркалирования остается простой
    step = cfg.get("settings", {}).get("checker_step_y", 40)
    
    if not is_source and point_str == "off":
        off = cfg.get("special_points", {}).get("off")
        if off:
            y = off["y"] - local_placed[point_str] * step
    
    if mirror_y and point_str.isdigit():
        y = _mirror_y(y, cfg)

    return (x, y)