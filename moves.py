# moves.py
from itertools import combinations, permutations
from typing import Callable, Iterable, List, Optional, Tuple

StepValidator = Callable[[int, int, int], bool]
# signature: (from_pos, to_pos, i) -> bool
# i = индекс под-хода внутри последовательности (0 для первого шага "bar -> ...")

def decompose_bar_move(
    to_point_str: str,
    available_dice: Iterable[int],
    is_legal_step: Optional[StepValidator] = None,
) -> List[str]:
    """
    Декомпозирует ход с бара до конкретного пункта в последовательность микро-ходов.
    Возвращает список строк вида: ["bar/22", "22/19", ...].
    Если ничего легального не нашли — ["bar/<to_point>"] как фоллбэк.
    
    Правила/предпочтения:
    - Пытаемся использовать МАКСИМАЛЬНОЕ число кубиков (важное правило BG).
    - Каждый промежуточный шаг проверяем через is_legal_step (если передан).
    - Нумерация предполагается НЕинвертированной (реальный номер 1..24).
    """
    try:
        to_point = int(to_point_str)
    except (ValueError, TypeError):
        return []

    if not (1 <= to_point <= 24):
        return []

    dice = list(available_dice)
    if not dice:
        return [f"bar/{to_point_str}"]

    pips_needed = 25 - to_point  # вход с бара вниз по номерам

    # вспомогательная проверка шага
    def _ok_step(frm: int, to: int, i: int) -> bool:
        if not (1 <= to <= 24):
            return False
        if is_legal_step is None:
            return True
        return is_legal_step(frm, to, i)

    # Ищем по убыванию числа кубиков (максимально возможное использование).
    # Например, если есть решение на 2 кубах — не берём на 1.
    for num_dice in range(len(dice), 0, -1):
        # все мультисеты из dice длины num_dice с точной суммой
        combos = set()
        for combo in combinations(dice, num_dice):
            if sum(combo) == pips_needed:
                combos.add(tuple(sorted(combo)))  # нормализуем для set

        if not combos:
            continue

        # для каждой комбинации — все перестановки (порядок розыгрыша важен)
        for combo in combos:
            seen_perms = set()
            for perm in permutations(combo):
                if perm in seen_perms:
                    continue
                seen_perms.add(perm)

                sub_moves: List[str] = []
                cur = 25  # бар как "25"
                ok = True
                for i, die in enumerate(perm):
                    nxt = cur - die
                    frm_str = "bar" if i == 0 else str(cur)
                    if not _ok_step(cur, nxt, i):
                        ok = False
                        break
                    sub_moves.append(f"{frm_str}/{nxt}")
                    cur = nxt

                if ok and cur == to_point:
                    return sub_moves

    # Ничего не нашли (или нельзя по валидатору) — оставим агрегированный ход
    return [f"bar/{to_point_str}"]