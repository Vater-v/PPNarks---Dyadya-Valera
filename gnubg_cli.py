# gnubg_cli.py
from __future__ import annotations
import os
import re
import json
import logging
import subprocess
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

# ---- Настройки окружения ----
GNUBG_PATH = os.environ.get("GNUBG_PATH", r"C:\Program Files (x86)\gnubg\gnubg-cli.exe")
GNUBG_ARGS = ["-t", "-q"]  # text mode, quiet
GNUBG_TIMEOUT_SEC = float(os.environ.get("GNUBG_TIMEOUT_SEC", "8.0"))

# Когда True — команды не запускаются, а только выводятся (удобно для CI)
DRY_RUN = bool(int(os.environ.get("GNUBG_DRY_RUN", "0")))

# ---- Логирование (по умолчанию — тихо) ----
logger = logging.getLogger("gnubg")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.WARNING)  # INFO включай только при x=2 (комбо/минимальные логи)

# ==== Режимы вывода ====
class RequestMode(IntEnum):
    HUMAN = 0    # Красивый русский текст
    MACHINE = 1  # Только машинный формат (JSON-строка)
    COMBO = 2    # JSON + краткие логи через logging (без print)

# ==== Результат (на будущее — удобно для тестов/расширений) ====
@dataclass
class HintResult:
    status: str               # "OK"|"ERROR"
    human_text: str           # Человеческое описание (пусто в MACHINE)
    moves: List[str]          # Нормализованные токены хода ["24/20","13/8",...]
    cube: Optional[str]       # "no_double"|"double_take"|"double_pass"|"beaver"|"take"|"pass"|None
    raw: str                  # Сырой stdout gnubg
    meta: Dict[str, Any]      # служебные поля (pos_id, match_id, kind, debug)

# -------- команды к GNUbg --------
def cmds_form(start: str, pos_id: str, match_id: str) -> List[str]:
    """Собирает команды в корректном порядке для GNUbg, запрашивает решение."""
    cmds: List[str] = []
    # TODO add match game support (match_length) при необходимости
    if 'game' in start:
        cmds.append("new game")
    cmds.append("12")
    cmds.append("clear turn")
    cmds.append(f"set board {pos_id}")
    cmds.append(f"set matchid {match_id}")
    cmds.append("hint 1")
    return cmds

def _run_gnubg_once(commands: List[str]) -> str:
    """Запускает GNUbg один раз с набором команд. Возвращает stdout."""
    script = "\n".join(commands) + "\n"
    if DRY_RUN:
        return f"[DRY-RUN]\n{script}"
    try:
        proc = subprocess.run(
            [GNUBG_PATH] + GNUBG_ARGS,
            input=script.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=GNUBG_TIMEOUT_SEC,
        )
        return proc.stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        return f"[ERROR] gnubg not found at '{GNUBG_PATH}'. Commands were:\n{script}"
    except subprocess.TimeoutExpired:
        return f"[ERROR] gnubg timeout after {GNUBG_TIMEOUT_SEC}s. Commands were:\n{script}"

# -------- ходовый парсер --------
def _expand_chain_token(token: str) -> list[str]:
    """
    V3: Корректно раскладывает цепочки типа "21/18*/15" → ["21/18*", "18/15"].
    Звёздочка после узла относится к прибытию в этот узел (предыдущий сегмент).
    Сохраняет повторы "(n)" как дублирование последнего сегмента.
    """
    token = token.strip()
    if not token:
        return []

    # 1) Счётчик повторов, например "8/4*(2)"
    cnt = 1
    m = re.search(r"\((\d+)\)\s*$", token)
    if m:
        cnt = int(m.group(1))
        token = token[:m.start()].strip()

    parts_raw = token.split('/')
    if len(parts_raw) <= 2:
        # простой ход, повторяем как есть
        return [token] * cnt

    # 2) Размечаем узлы: (value, has_star_after_this_point)
    nodes: list[tuple[str, bool]] = []
    for p in parts_raw:
        p = p.strip()
        has_star = p.endswith('*')
        if has_star:
            p = p[:-1]  # убрать '*', чтобы узел был "чистым"
        nodes.append((p, has_star))

    # 3) Собираем сегменты: star берётся у ТОЧКИ ПРИБЫТИЯ (узел i+1)
    segs: list[str] = []
    for i in range(len(nodes) - 1):
        fr, _ = nodes[i]
        to, star_on_to = nodes[i + 1]
        segs.append(f"{fr}/{to}{'*' if star_on_to else ''}")

    # 4) Повторяем последний сегмент при "(n)"
    if cnt > 1 and segs:
        segs.extend([segs[-1]] * (cnt - 1))

    return segs


def parse_gnubg(move_text: str) -> list[str]:
    """
    Парсит строк(и) хода GNUbg в нормализованный список сегментов.
    Поддерживает цепную форму: "6/2*/1*", повторы "(2)", bar/off.
    """
    if not move_text:
        return []
    s = move_text.strip()
    tokens = [t for t in s.split() if "/" in t]
    moves: list[str] = []
    for tok in tokens:
        moves.extend(_expand_chain_token(tok))
    return moves


# -------- humanize хода --------
def _ru_point(x: str) -> str:
    if x == "bar": return "бар"
    if x == "off": return "снятие"
    return x

def _pretty_arrows(parts: list[str]) -> str:
    if not parts:
        return ""
    arrows = []
    for p in parts:
        a, b = p.split("/", 1)
        arrows.append(f"{_ru_point(a)}→{_ru_point(b)}")
    return "Ходи: " + ", ".join(arrows)

def _humanize_move_line(move_line: str) -> Tuple[str, list[str]]:
    parts = parse_gnubg(move_line)
    if parts:
        return _pretty_arrows(parts), parts
    # если не распарсили — покажем как есть
    return f"Ход: {move_line.strip()}", []

# -------- humanize куба --------
def _humanize_cube(cube_text: str) -> str:
    t = cube_text.strip().lower()

    # короткие формы (однострочные решения)
    if "no double" in t and "beaver" in t:
        return "Куб: не удваивать (бейвер возможен)"
    if "no double" in t:
        return "Куб: не удваивать"
    if "double, pass" in t and "proper cube action" not in t:
        return "Куб: дабл — пас"
    if "double, take" in t and "proper cube action" not in t:
        return "Куб: дабл — тейк"

    # «шапка» из анализа
    if "proper cube action" in t:
        # напр.: "Proper cube action: No double, beaver (26,9%)"
        m = re.search(r"proper cube action:\s*(.+)", t)
        if m:
            action = m.group(1)
            action = action.replace("no double", "не удваивать")
            action = action.replace("double, pass", "дабл — пас")
            action = action.replace("double, take", "дабл — тейк")
            action = action.replace("beaver", "бейвер")
            return f"Куб: {action}".strip()

    # дефолт
    return "Куб: " + cube_text.strip()

# -------- вырезаем "островок" ходов из строки с Eq. --------
_MOVE_ISLAND_RE = re.compile(
    r"((?:"  # Начало группы для всей последовательности ходов
    r"\b(?:bar|off|\d{1,2})\*?"  # Начальный пункт (24)
    r"(?:/(?:bar|off|\d{1,2})\*?)+"  # ОДИН ИЛИ БОЛЕЕ сегментов (/12*, /8)
    r"(?:\(\d+\))?"  # Опциональный повторитель (2)
    r"\s*"  # Пробелы после токена
    r")+)",  # Вся эта конструкция может повторяться для нескольких ходов
    re.IGNORECASE,
)
def _extract_move_island(line: str) -> Optional[str]:
    """
    Из строки вида:
      "1. Cubeful 3-ply    24/20 13/8                   Eq.: +0,029"
    возвращает "24/20 13/8".
    Берём левую часть до "Eq.:" и вырезаем хвост, похожий на последовательность ходов.
    """
    if "Eq.:" not in line:
        return None
    left = line.rsplit("Eq.:", 1)[0].rstrip()
    m = _MOVE_ISLAND_RE.search(left)
    if m:
        return m.group(1).strip()
    return None


# -------- выбор строк --------
def _pick_cube_decision(lines: list[str]) -> Optional[str]:
    # Примерный эвристический отбор: первая строка с "No double", "Double" или "Proper cube action"
    for ln in lines:
        low = ln.lower()
        if ("no double" in low) or ("double, pass" in low) or ("double, take" in low) or ("proper cube action" in low):
            return ln
    return None

def _pick_move_line(lines: list[str]) -> Optional[str]:
    """
    Находит и возвращает САМИ ХОДЫ, а не всю строку.
    Приоритет: строки с "Eq.:" + валидные токены вида "24/20", "bar/23", ...
    Игнорируем "Position ID", "Match ID", ASCII-борд и т.п.
    """
    def looks_like_move_token(s: str) -> bool:
        return bool(re.search(
            r'\b(?:bar|off|\d{1,2})\*?/(?:bar|off|\d{1,2})\*?(?:/\d{1,2}\*?)*\b',
            s, re.IGNORECASE
        ))


    def banned(s: str) -> bool:
        low = s.lower()
        return (
            "position id" in low or
            "match id" in low or
            "gnu backgammon" in low or
            "on roll" in low or
            "rolled" in low or
            "очков" in low or
            "bar|" in low  # от ASCII-борда
        )

    # 1) Сначала — строки с Eq.: (самый надёжный признак)
    for ln in lines:
        if banned(ln):
            continue
        if "Eq.:" in ln and looks_like_move_token(ln):
            island = _extract_move_island(ln)
            if island:
                return island

    # 2) Без Eq.: — берём «последний островок» токенов с '/'
    for ln in lines:
        if banned(ln):
            continue
        if looks_like_move_token(ln):
            # заберём хвост, где идут токены ходов (последний «остров» с '/')
            parts = [p.strip() for p in re.split(r'\s{2,}', ln) if "/" in p]
            if parts:
                return parts[-1]
            # fallback: начиная с первого токена со слешем
            toks = ln.split()
            for i, t in enumerate(toks):
                if "/" in t:
                    return " ".join(toks[i:]).strip()

    return None


_PROPER_RE = re.compile(
    r"proper cube action:\s*(?P<action>.+?)(?:\((?P<pct>[\d.,]+)%\))?\s*$",
    re.IGNORECASE
)

def decide_take_pass_from_cubelist(lines: list[str]) -> str:
    """
    Короткий RU-совет для ПОЛУЧАТЕЛЯ дабла: 'Прими' / 'Пас'
    + опционально ' (бейвер возможен, ~N%)'.
    """
    text_full = "\n".join(lines)
    text = text_full.lower()

    # 1) Пытаемся вытащить ровно строку Proper cube action: ...
    m = _PROPER_RE.search(text_full)
    if m:
        action_raw = m.group("action").strip().lower()  # напр.: "No double, beaver "
        pct = m.group("pct")  # может быть None
        beaver_note = (f", ~{pct}%" if pct else "")
        if "double, pass" in action_raw:
            return "Пас"
        if "double, take" in action_raw:
            return "Прими"
        if "no double" in action_raw:
            # Для получателя: если правильное действие дающего — не даблить,
            # значит при уже полученном дабле: Прими
            if "beaver" in action_raw:
                return "Прими (бейвер возможен" + beaver_note + ")"
            return "Прими"
        # На всякий случай дефолт.
        return "Прими"

    # 2) Если отдельной строки нет — грубые эвристики по всему блоку
    if "double, pass" in text and "no double" not in text:
        return "Пас"
    if "double, take" in text:
        return "Прими"
    if "no double" in text:
        return "Прими"

    # 3) Безопасный дефолт
    return "Прими"

def render_any(out: str, receiving_double: bool = False):
    """
    Возвращает (human_text, aux, raw_text, debug_note)
    """
    text = out or ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # ---- НОВОЕ: Явная проверка на отсутствие ходов ----
    # Gnubg может ответить на кириллице в зависимости от локали системы
    if any("нет разрешённых ходов" in line.lower() for line in lines):
        return ("Нет разрешённых ходов", "kind=no_legal_moves", text, "[auto] detected 'no legal moves'")
    # --------------------------------------------------

    # Ветка для ситуации «соперник предложил дабл»
    if receiving_double and "cube analysis" in text.lower():
        # ... (остальная часть функции без изменений)
        cube_block = []
        seen = False
        for ln in lines:
            if ln.lower().startswith("cube analysis"):
                seen = True
            if seen:
                cube_block.append(ln)
        human = decide_take_pass_from_cubelist(cube_block)
        return (f"Решение по даблу: {human}", "kind=offer", text, "[auto] receiving_double")

    # Обычная логика, если дабла «со стороны соперника» нет
    cube = _pick_cube_decision(lines)
    move_line = _pick_move_line(lines)

    if cube and not move_line:
        human = _humanize_cube(cube)
        return (human, "kind=offer", text, "[auto] detected cube decision (humanized)")

    if move_line and not cube:
        human, parts = _humanize_move_line(move_line)
        return (human, "kind=hint", text, f"[auto] detected move line; parsed={parts!r}")

    if cube and move_line:
        human_move, parts = _humanize_move_line(move_line)
        human_cube = _humanize_cube(cube)
        human = f"{human_cube}; {human_move}"
        return (human, "kind=offer", text, f"[auto] both found; parsed_moves={parts!r}")

    return ("Бросай кости", "kind=none", text, "[auto] nothing matched; default to 'roll dice'")

# ---- Нормализация решения по кубу в «машинный» ярлык ----
def _normalize_cube_label(human_ru: str) -> Optional[str]:
    """
    Из human-строки вида 'Куб: не удваивать', 'Куб: дабл — пас',
    'Решение по даблу: Прими' и т.п. делает:
      "no_double" | "double_pass" | "double_take" | "beaver" | "take" | "pass" | None
    """
    if not human_ru:
        return None
    t = human_ru.lower()
    if "бейвер" in t:
        return "beaver"
    if "не удваивать" in t:
        return "no_double"
    if "дабл — пас" in t or "double, pass" in t:
        return "double_pass"
    if "дабл — тейк" in t or "double, take" in t:
        return "double_take"
    if "решение по даблу:" in t:
        if "пас" in t:
            return "pass"
        if "прими" in t:
            return "take"
    return None

def _cube_verbose(cube_label: Optional[str], receiving_double: bool, meta_kind: str) -> str:
    if receiving_double:
        if cube_label in ("pass", "double_pass"): return "Решение по даблу: Пас"
        if cube_label in ("take", "double_take"): return "Решение по даблу: Прими"
        return "Решение по даблу: Прими"

    mapping = {
        "no_double":   "Куб: не удваивать",
        "double_take": "Куб: удваивай (оппонент берёт)",
        "double_pass": "Куб: удваивай (оппонент пасует)",
        "beaver":      "Куб: не удваивать (возможен бейвер)",
    }
    if cube_label in mapping:
        return mapping[cube_label]
    if meta_kind == "kind=hint":
        return "Куб: нет рекомендации (занятие ходом)"
    return "Куб: решение не определено"

# ==== Единая функция запроса (x = 0/1/2) ====
def hint_request(
    start: str,
    pos_id: str,
    match_id: str,
    receiving_double: bool,
    mode: RequestMode = RequestMode.HUMAN
) -> str:
    """
    Возвращает строку:
      - mode=HUMAN (0): человекочитаемый RU-текст
      - mode=MACHINE (1): JSON-строка (только команды/данные)
      - mode=COMBO (2): JSON-строка + минимальные логи через logging (без print)
    """
    commands = cmds_form(start, pos_id, match_id)
    out = _run_gnubg_once(commands)

    human, kind, raw, debug_note = render_any(out, receiving_double)

    # --- КЛЮЧЕВОЕ: парсим ходы ИМЕННО из «островка» move_line, а не из всего raw
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    sel_move_line = _pick_move_line(lines) or ""
    moves = parse_gnubg(sel_move_line)
    # если звёздочки не нужны автокликеру — срежь их:
    moves = [m.replace("*", "") for m in moves]

    cube_label = _normalize_cube_label(human)
    cube_msg = _cube_verbose(cube_label, receiving_double, kind)

    result = HintResult(
        status="OK" if not out.startswith("[ERROR]") else "ERROR",
        human_text=(human if mode == RequestMode.HUMAN else ""),
        moves=moves,
        cube=cube_label,
        raw=raw,
        meta={
            "kind": kind,
            "debug": debug_note,
            "pos_id": pos_id,
            "match_id": match_id,
            "commands": commands,
            "move_line": sel_move_line,
        },
    )

    if mode == RequestMode.HUMAN:
        pretty = [
            human,
            cube_msg,                 # явный вывод по кубу
            f"POSID: {pos_id}",
            f"MATID: {match_id}",
        ]
        return "\n".join(pretty)

    payload = {
        "status": result.status,
        "moves": result.moves,        # ["24/20","13/8",...]
        "cube": result.cube,          # "no_double"|"double_take"|...|None
        "cube_verbose": cube_msg,     # явный русский вердикт
        "meta": {"kind": kind},       # компактный минимум
    }
    js = json.dumps(payload, ensure_ascii=False)

    if mode == RequestMode.COMBO:
        logger.info("gnubg: %s", result.meta.get("debug"))
        logger.info("gnubg: pos=%s match=%s", pos_id, match_id)
        logger.info("gnubg: move_line='%s'", sel_move_line)
        logger.info("[CUBE] %s", cube_msg)

    return js