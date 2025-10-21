# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
from typing import Any, Optional, Dict, List, Tuple
import time
from concurrent.futures import ThreadPoolExecutor
from telegram_sender import send_notification
from hero import HeroState
from message_formatter import format_match_end_message
from gnubg_posid import generate_match_id, generate_position_id
from gnubg_cli import hint_request
import logging
from session_logger import log_session
import hashlib
from autoclicker import Clicker
import os
import random
import json
import copy
from debouncer import Debouncer
from coords import BackgammonBoard


# ==== опциональная подсветка белым ====
try:
    from colorama import just_fix_windows_console, Fore, Style
    just_fix_windows_console()
    WHITE_BOLD = Style.BRIGHT + Fore.WHITE
    RESET = Style.RESET_ALL
except Exception:
    WHITE_BOLD = ""
    RESET = ""

# ===================== Конфиг =====================
DEBOUNCE = Debouncer(ttl=0.45)
DEBUG_MODE = False

log = logging.getLogger("log_handle")
log.setLevel(logging.INFO)

# ===================== Утилиты =====================
def logically_invert_board_state(game_state: Dict) -> Dict:
    """
    Создает новую версию состояния игры, логически "разворачивая" доску.
    Пункт 1 становится пунктом 24, 2 -> 23 и т.д.
    Это нужно, когда мы играем с startPos: 0, чтобы привести доску к
    стандартному виду, который ожидает GNUbg.
    """
    if not game_state or 'board' not in game_state:
        return game_state

    # Глубокое копирование, чтобы не изменять оригинальный стейт
    inverted_state = copy.deepcopy(game_state)
    original_points = inverted_state['board']['points']
    
    # Создаем карту старых номеров на новые данные
    # {1: (данные пункта 24), 2: (данные пункта 23), ...}
    new_points_data_map = {p['number']: p for p in original_points}
    
    inverted_points_list = []
    for i in range(1, 25):
        # Для нового пункта i берем данные из старого пункта (25-i)
        original_point_data = new_points_data_map.get(25 - i)
        if original_point_data:
            # Создаем новый объект, чтобы не было проблем со ссылками
            new_point = copy.deepcopy(original_point_data)
            # Присваиваем ему правильный новый номер
            new_point['number'] = i
            inverted_points_list.append(new_point)

    inverted_state['board']['points'] = inverted_points_list
    return inverted_state


def get_in(d: Any, path: list, default=None):
    if d is None:
        return default
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur

def pick(*vals):
    for v in vals:
        if v is not None:
            return v
    return None

# Для анти-спама: последняя строка каждого типа
_last_lines: Dict[str, str] = {}
def print_once(tag: str, line: str):
    prev = _last_lines.get(tag)
    if prev == line:
        return
    _last_lines[tag] = line
    print(line, flush=True)

def moves_to_short(moves: List[str]) -> str:
    """
    "24/18", "13/11*", "bar/23", "6/off" -> "24-18, 13-11*, bar-23, 6-off"
    """
    out = []
    for m in moves:
        s = m.strip()
        star = "*" if "*" in s else ""
        s = s.replace("*", "")
        if "/" in s:
            a, b = s.split("/", 1)
            out.append(f"{a}-{b}{star}")
        else:
            out.append(s + star)
    return ", ".join(out)

def invert_move_str(move_str: str) -> str:
    """
    Инвертирует ход, если доска перевернута (e.g., "8/2" -> "17/23").
    Сохраняет звездочку (*) для ударов.
    """
    try:
        is_hit = '*' in move_str
        clean_move = move_str.replace('*', '')
        from_str, to_str = clean_move.split('/')

        # Инвертируем только числовые пункты
        inv_from = str(25 - int(from_str)) if from_str.isdigit() else from_str
        inv_to = str(25 - int(to_str)) if to_str.isdigit() else to_str
        
        return f"{inv_from}/{inv_to}{'*' if is_hit else ''}"
    except (ValueError, IndexError):
        # Если что-то пошло не так (например, ход не в формате "a/b"), возвращаем как есть
        return move_str


# ===================== Глобалы =====================
OUR_PIDS = set()
HERO_STATE: Optional[HeroState] = None
HERO_ID: Optional[str] = None
OPPONENT_ID: Optional[str] = None
POSITION_ID: Optional[str] = None
MATCH_ID: Optional[str] = None

first: Optional[int] = None
second: Optional[int] = None
DICE_ROLL_ATTEMPTS = 0
LAST_DICE_ROLL_TIME = 0
WAITING_FOR_DICE = False
DICE_ROLLED_RECEIVED = False
MATCH_TO_SCORE = 0
HERO_SCORE = 0
OPPONENT_SCORE = 0
current_game_id = None
START_SENT = False
END_SENT = False
LAST_HERO_BALANCES = {"gold": None, "diamond": None, "chips": None}
MATCH_START_DATA = {}
HASH_SALT = "здарова"
HERO_IS_PLAYER_ZERO = True
HERO_BOARD_PERSPECTIVE_IS_INVERTED = False
TURN_STATE = {
    "active": False,
    "dice_initial": None,
    "dice_remaining": [],
    "plan_gnubg": [],
}

CURRENCY_MAP = {'gold': 'фантиков', 'diamond': 'кристаллов', 'club_chips': 'клубных фишек'}
VARIANT_MAP = {'ShortGammon': 'Короткие нарды', 'HyperGammon': 'Гипер-нарды'}
MATCH_TYPE_MAP = {'ClassicMoneyGame': 'Игра на деньги', 'ProMoneyGame': 'Турнир'}
PLAYER_TYPE_MAP = {'Any': 'скорее не бот', 'account': 'не бот наверн', 'Real': 'точно не бот'}

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="async_telegram")

board_calculator = None
try:
    clicker = Clicker()
    # Укажите путь к вашему файлу конфигурации
    board_calculator = BackgammonBoard(config_path='board_config.json')
except Exception as e:
    # pass # Можете добавить логирование ошибки, если нужно
    print(f"[INIT ERROR] Не удалось инициализировать Clicker или BoardCalculator: {e}")


# ===================== Хелперы =====================
def define_pid(player1_id, player2_id, our_pids_set):
    if player1_id in our_pids_set: return player1_id
    if player2_id in our_pids_set: return player2_id
    return None

def load_our_pids():
    """Читает ID героя из переменной окружения, установленной в main.py."""
    player_id = os.getenv("HERO_PLAYER_ID")
    return {player_id} if player_id else set()

OUR_PIDS = load_our_pids()

def run_async_task(coro):
    def run_in_thread():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                try:
                    loop.close()
                except:
                    pass
                asyncio.set_event_loop(None)
        except Exception as e:
            print(f"[ASYNC ERROR] {e}")
            return None
    future = _executor.submit(run_in_thread)
    try:
        return future.result(timeout=10.0)
    except TimeoutError:
        print("[ASYNC] Warning: Thread timeout")
        return None

_clean_cache = {}
def _clean(val, default="N/A"):
    if val is None:
        return default
    key = (val, default)
    if key in _clean_cache:
        return _clean_cache[key]
    s = str(val).strip()
    result = default if s == "" or s.lower() == "null" else s
    if len(str(val)) < 100:
        _clean_cache[key] = result
    return result

def _get_players_data(payload):
    players_dict = get_in(payload, ['context', 'players']) or get_in(payload, ['data', 'players']) or {}
    p1_data = players_dict.get('first')
    p2_data = players_dict.get('second')
    return p1_data, p2_data

def _consolidate_player_info(player_data):
    if not player_data or not isinstance(player_data, dict):
        return None
    info = {}
    profile = player_data.get('accountProfile') or {}
    user = player_data.get('user') or {}
    info['id'] = player_data.get('userId') or user.get('accountId') or profile.get('id')
    info['nickname'] = profile.get('nickname') or user.get('username')
    info['clubId'] = profile.get('clubId')
    is_guest = profile.get('isGuest')
    info['isGuest'] = bool(is_guest) if is_guest is not None else False
    if not info.get('id'):
        return None
    return info

def _extract_game_params(payload):
    return get_in(payload, ['context', 'gameParams'], {}) or get_in(payload, ['data', 'gameParams'], {}) or {}

def _format_variant(raw): return VARIANT_MAP.get(raw, raw or 'Короткие нарды')
def _format_currency(raw): return CURRENCY_MAP.get(raw, raw or '')

def format_match_start_message(data: Dict[str, Any]) -> str:
    hero_nick = data.get('hero_nickname', 'Неизвестно')
    hero_id = data.get('hero_id', 'N/A')
    opp_nick = data.get('opp_nickname', 'Неизвестно')
    vill_id = data.get('vill_id', 'N/A')
    club = data.get('hero_club', 'N/A')
    variant = data.get('game_variant', 'Короткие нарды')
    bet = data.get('bet_amount', '0')
    currency = data.get('bet_currency', '')
    match_type = data.get('match_type', 'Обычный матч')
    player_type = data.get('player_type', '')
    warning = data.get('warning_message', '')
    match_hash = data.get('match_start_hash')
    opp_status_str = " `(Гость)`" if data.get('is_opp_guest', False) else ""
    hash_line = f"🔒 **Хеш матча**: `{match_hash[:16]}...`\n" if match_hash else ""
    message = (
        f"🎮 **Новый матч!**\n\n"
        f"👤 **Наш игрок**\n"
        f"   ┣ 🎖 Ник: `{hero_nick}`\n"
        f"   ┣ 🆔 ID: `{hero_id}`\n"
        f"   ┗ 🏆 Клуб: `{club}`\n\n"
        f"⚔️ **Противник**\n"
        f"   ┣ 🎖 Ник: `{opp_nick}`{opp_status_str}\n"
        f"   ┗ 🆔 ID: `{vill_id}`\n\n"
        f"- - - - - - - - - - - - - - - -\n"
        f"🎲 **Режим игры**: `{variant}`\n"
        f"💰 **Ставка**: `{bet} {currency}`\n"
        f"📌 **Тип матча**: `{match_type}`\n"
        f"🔍 **Соперник**: ` {player_type}`\n"
        f"{hash_line}"
    )
    if warning:
        message += f"\n{warning}\n"
    message += "━━━━━━━━━━━━━━━"
    return message

def _mk_start_data(payload):
    global MATCH_TO_SCORE, HERO_SCORE, OPPONENT_SCORE
    p1_raw, p2_raw = _get_players_data(payload)
    p1 = _consolidate_player_info(p1_raw)
    p2 = _consolidate_player_info(p2_raw)
    gp = _extract_game_params(payload)
    if not HERO_ID or not p1 or not p2:
        return None
    hero = p1 if p1.get('id') == HERO_ID else p2
    opp  = p2 if p1.get('id') == HERO_ID else p1
    if hero.get('id') != HERO_ID:
        return None
    club = hero.get('clubId')
    club = 'Нет клуба' if not club or str(club).lower() == 'null' else club
    MATCH_TO_SCORE = gp.get('winPointsCount', 0)
    HERO_SCORE = 0
    OPPONENT_SCORE = 0
    rmsg = {
        "hero_nickname": _clean(hero.get('nickname'), 'HERO'),
        "hero_id": _clean(hero.get('id'), 'N/A'),
        "opp_nickname": _clean(opp.get('nickname'), 'VILLAIN'),
        "vill_id": _clean(opp.get('id'), 'N/A'),
        "hero_club": club,
        "match_type": MATCH_TYPE_MAP.get(gp.get('matchType'), _clean(gp.get('matchType'))),
        "player_type": PLAYER_TYPE_MAP.get(gp.get('playerType'), _clean(gp.get('playerType'))),
        "time_control": "Стандартный",
        "is_opp_guest": opp.get('isGuest', False),
        "game_variant": _format_variant(gp.get('gameVariant') or get_in(payload, ['data', 'gameVariant'])),
        "bet_amount": gp.get('bet', 0),
        "bet_currency": _format_currency(gp.get('betAmountType')),
        "warning_message": ""
    }
    if current_game_id:
        hash_string = f"{current_game_id}|{rmsg['hero_id']}|{rmsg['vill_id']}|{rmsg['bet_amount']}|{rmsg['bet_currency']}|{HASH_SALT}".encode('utf-8')
        match_hash = hashlib.sha256(hash_string).hexdigest()
        rmsg['match_start_hash'] = match_hash
        MATCH_START_DATA[current_game_id] = rmsg
    return rmsg

def _mk_end_data(payload):
    w = get_in(payload, ['data','gameResult','winner','user'], {}) or {}
    winner_id = w.get('accountId')
    winner_name = w.get('username') or winner_id or 'Неизвестно'
    stake = get_in(payload, ['data','stake'], {}) or {}
    bet = stake.get('initialValue', 0)
    currency = _format_currency(stake.get('amountType'))
    profit = None
    if HERO_ID and winner_id:
        net_bank_str = stake.get('netBankValue')
        stakes_by_player = stake.get('stakesByPlayer', {})
        hero_stake_str = stakes_by_player.get(HERO_ID)
        if net_bank_str is not None and hero_stake_str is not None:
            try:
                net_bank = float(net_bank_str) if net_bank_str else 0.0
                hero_stake = float(hero_stake_str) if hero_stake_str else 0.0
                profit = (net_bank - hero_stake) if HERO_ID == winner_id else -hero_stake
            except (ValueError, TypeError):
                profit = None
    p1_raw, p2_raw = _get_players_data(payload)
    p1 = _consolidate_player_info(p1_raw)
    p2 = _consolidate_player_info(p2_raw)
    hero = opp = None
    club = 'Нет клуба'
    if HERO_ID and p1 and p2:
        hero = p1 if p1.get('id') == HERO_ID else p2
        opp  = p2 if p1.get('id') == HERO_ID else p1
        if hero and hero.get('id') == HERO_ID:
            club_raw = hero.get('clubId')
            club = 'Нет клуба' if not club_raw or str(club_raw).lower() == 'null' else club_raw
    pips = get_in(payload, ['data','pipsCounts'], [])
    pips_map = {i.get('accountId'): i.get('pipsCount') for i in pips if isinstance(i, dict)}
    hero_pips = pips_map.get(HERO_ID)
    opp_pips = pips_map.get(OPPONENT_ID)
    result_score = f"pips: наш `{hero_pips}` / соперник `{opp_pips}`" if hero_pips is not None and opp_pips is not None else ""
    gp = _extract_game_params(payload)
    variant = _format_variant(gp.get('gameVariant') or get_in(payload, ['data','gameVariant']))
    return {
        "hero_nickname": _clean(hero.get('nickname') if hero else None, 'HERO'),
        "hero_id": _clean(hero.get('id') if hero else None, 'N/A'),
        "opp_nickname": _clean(opp.get('nickname') if hero else None, 'VILLAIN'),
        "vill_id": _clean(opp.get('id') if opp else None, 'N/A'),
        "hero_club": club,
        "game_variant": variant,
        "bet_amount": bet,
        "bet_currency": currency,
        "match_type": _clean(gp.get('matchType'), 'Обычный матч'),
        "player_type": _clean(gp.get('playerType'), 'Неизвестно'),
        "winner": winner_name,
        "result_score": result_score,
        "profit": profit,
        "duration": "",
        "warning_message": ""
    }

def _balances_list_to_map(balances_list):
    if not balances_list: return {}
    out = {}
    for b in balances_list:
        ctype, amt = b.get("amountType"), b.get("amount")
        if not ctype or amt is None: 
            continue
        try: 
            out[ctype] = float(amt)
        except (ValueError, TypeError):
            try: 
                out[ctype] = float(str(amt).replace(",", "."))
            except: 
                pass
    return out

def format_balance_change_message(data: Dict[str, Any]) -> str:
    nickname, changes = data.get("nickname", "HERO"), data.get("changes", {})
    if not changes: return ""
    lines = [
        f"{'➕' if info.get('delta', 0.0) >= 0 else '➖'} `{ctype}` ({CURRENCY_MAP.get(ctype, ctype)}): "
        f"{info.get('delta', 0.0):+.2f} → теперь `{info.get('now', 0.0):.2f}`"
        for ctype, info in changes.items()
    ]
    return f"💳 **Изменение баланса**\n👤 Аккаунт: `{nickname}`\n" + "\n".join(lines)

def send_balance_change_notification(nickname: str, changes: Dict[str, Dict[str, float]]):
    msg = format_balance_change_message({"nickname": nickname, "changes": changes})
    if msg: run_async_task(send_notification(msg))

def _optimize_move_plan(plan: list[str]) -> list[str]:
    if len(plan) < 2:
        return plan
    processed = list(plan)
    i = 0
    while i < len(processed) - 1:
        j = i + 1
        while j < len(processed):
            try:
                from1, to1 = processed[i].replace('*', '').split('/')
                from2, to2 = processed[j].replace('*', '').split('/')
                if from1 == 'bar':
                    j += 1
                    continue
                if to1 == from2:
                    processed[i] = f"{from1}/{to2}"
                    del processed[j]
                    j = i
            except ValueError:
                pass
            j += 1
        i += 1
    return processed

def reset_turn_state():
    global TURN_STATE, WAITING_FOR_DICE, DICE_ROLLED_RECEIVED
    TURN_STATE = {
        "active": False,
        "dice_initial": None,
        "dice_remaining": [],
        "plan_gnubg": [],
    }
    WAITING_FOR_DICE = False
    DICE_ROLLED_RECEIVED = False

def extract_ctx(payload: Dict[str, Any], hero_id: Optional[str]) -> Dict[str, Any]:
    current_turn_owner = get_in(payload, ['data', 'currentTurn', 'ownerId'])
    available_actions = set(payload.get('availableActions', []))
    dice = get_in(payload, ['data', 'currentTurn', 'dice'], {}) or {}
    return {
        "event_name": payload.get("name") or payload.get("type"),
        "stage": payload.get("stage"),
        "current_turn_owner": current_turn_owner,
        "available_actions": available_actions,
        "availableActions": available_actions,    # совместимость
        "dice_first": dice.get('first'),
        "dice_second": dice.get('second'),
        "is_our_turn": (current_turn_owner == hero_id) if hero_id else None,
    }

def can_move(ctx: Dict[str, Any]) -> bool:
    return bool(ctx.get("is_our_turn")) and ("MoveChecker" in ctx.get("available_actions", set()))

def can_roll(ctx: Dict[str, Any]) -> bool:
    return "RollDice" in ctx.get("available_actions", set())

def can_offer_double(ctx: Dict[str, Any]) -> bool:
    a = ctx.get("available_actions") or ctx.get("availableActions") or set()
    return "DoublingOffer" in a

def is_respond_state(ctx: Dict[str, Any]) -> bool:
    a = ctx.get("available_actions", set())
    return any(x in a for x in ("DoublingRespond", "DoublingAccept", "DoublingReject"))

def _invert_move_if_needed(move_str: str) -> str:
    if HERO_IS_PLAYER_ZERO:
        return move_str
    try:
        is_hit = '*' in move_str
        from_str, to_str = move_str.replace('*', '').split('/')
        inv_from = str(25 - int(from_str)) if from_str.isdigit() else from_str
        inv_to = str(25 - int(to_str)) if to_str.isdigit() else to_str
        return f"{inv_from}/{inv_to}{'*' if is_hit else ''}"
    except ValueError:
        return move_str

# ===================== Минимальный вывод в консоль =====================
def print_game_header(game_id: str, hero: Optional[str], opp: Optional[str]):
    if hero and opp:
        print_once("game", f"GAME: {game_id} HERO {hero} vs OPP {opp}")
    else:
        print_once("game", f"GAME: {game_id}")

def print_dice(d1: Optional[int], d2: Optional[int]):
    if d1 is not None and d2 is not None:
        print_once("dice", f"DICE: {int(d1)}-{int(d2)}")

def print_posid(posid: Optional[str]):
    if posid:
        print_once("posid", f"POSID: {posid}")

def print_moves(moves: List[str]):
    if not moves:
        print_once("move", f"{WHITE_BOLD}MOVE: (no legal moves){RESET}")
        time.sleep(0.6)
        clicker.turn_commit()
        return
    line = moves_to_short(moves)
    print_once("move", f"{WHITE_BOLD}MOVE: {line}{RESET}")

def print_cube(decision: str, receiving: bool):
    """
    decision: 'no_double'|'double_take'|'double_pass'|'take'|'pass' ...
    receiving: True, если к нам прилетел дабл
    """
    if receiving:
        out = "take" if decision not in ("pass", "double_pass") else "pass"
    else:
        out = "double" if decision in ("double_take","double_pass") else "no double"
    print_once("cube", f"CUBE: {out}")

# ===================== POSID & MATCH ID =====================
def get_gnubg_ids_from_payload(payload: Dict[str, Any], hero_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not payload:
        return None, None
    game_data = payload.get('data', {})
    context_data = payload.get('context', {})
    board_data = game_data.get('board')
    player_on_roll_id = get_in(game_data, ['currentTurn', 'ownerId'])
    players = game_data.get('players') or {}

    pos_id = None
    if board_data and player_on_roll_id:
        try:
            pos_id = generate_position_id(board_data, game_data, player_on_roll_id)
        except Exception as e:
            log.debug("POSID error: %s", e)

    match_id = None
    p1_id = get_in(game_data, ['players', 'first', 'userId']) or get_in(game_data, ['players', 'first', 'user', 'accountId'])
    p2_id = get_in(game_data, ['players', 'second','userId']) or get_in(game_data, ['players', 'second','user','accountId'])
    if p1_id and p2_id and player_on_roll_id:
        try:
            match_state = context_data.get('matchState') or game_data.get('matchState') or {}
            cube_data  = game_data.get('doublingCube', {}) or {}
            dice_data  = get_in(game_data, ['currentTurn','dice'], {}) or {}

            p0_map_id, p1_map_id = p1_id, p2_id
            score_p0 = match_state.get('participant1Score', 0) if match_state.get('participant1') == p0_map_id else match_state.get('participant2Score', 0)
            score_p1 = match_state.get('participant2Score', 0) if match_state.get('participant2') == p1_map_id else match_state.get('participant1Score', 0)
            cube_owner_raw = cube_data.get('ownerId')
            cube_owner_mapped = 0 if cube_owner_raw == p0_map_id else (1 if cube_owner_raw == p1_map_id else None)

            match_id = generate_match_id(
                match_length = get_in(context_data, ['gameParams','winPointsCount'], 0),
                score_p0 = score_p0,
                score_p1 = score_p1,
                cube_value = cube_data.get('value', 1),
                cube_owner = cube_owner_mapped,
                player_on_roll = 0 if player_on_roll_id == p0_map_id else 1,
                turn_owner = 0 if player_on_roll_id == p0_map_id else 1,
                is_crawford = game_data.get('isCrawfordGame', False),
                is_double_offered = "DoublingRespond" in (payload.get("availableActions") or []),
                resign_flag = 0,
                die1 = dice_data.get('first'),
                die2 = dice_data.get('second'),
            )
        except Exception as e:
            log.debug("MATCH ID error: %s", e)

    return pos_id, match_id

# ===================== Действия =====================
def _do_roll():
    """
    Бросаем кости (если доступен кликер — дергаем его).
    Без спама: вывод сделает обработчик DiceRolled.
    """
    global WAITING_FOR_DICE, DICE_ROLLED_RECEIVED, LAST_DICE_ROLL_TIME, DICE_ROLL_ATTEMPTS
    WAITING_FOR_DICE = True
    DICE_ROLLED_RECEIVED = False
    LAST_DICE_ROLL_TIME = time.time()
    DICE_ROLL_ATTEMPTS = 1
    time.sleep(0.2)
    if clicker:
        clicker.roll_dice()

def double_respond(payload, hero_id, mode: bool = False):
    """
    Решение по кубу:
      - mode=False: наш оффер (думать/шлём double)
      - mode=True : к нам прилетел double (take/pass)
    Выводим только CUBE: <...>.
    """
    pos_id, match_id = get_gnubg_ids_from_payload(payload, hero_id)
    if not pos_id or not match_id:
        print_once("cube", "CUBE: no data, do roll")
        if not mode and DEBOUNCE.should_fire("roll", (POSITION_ID, HERO_ID)):
            _do_roll()
        return

    gnu_respond_str = hint_request("game", pos_id, match_id, mode, "COMBO")
    try:
        gnu_respond_dict = json.loads(gnu_respond_str)
    except json.JSONDecodeError:
        print_once("cube", "CUBE: parse error, do roll")
        if not mode and DEBOUNCE.should_fire("roll", (POSITION_ID, HERO_ID)):
            _do_roll()
        return

    cube = gnu_respond_dict.get("cube", "no_double")
    print_cube(cube, mode)

    # Автодействие при наличии кликера
    if mode:
        if cube in ("pass", "double_pass"):
            if clicker: clicker.pass_double()
        else:
            if clicker: clicker.take_double()
    else:
        if cube in ("double_take", "double_pass"):
            if clicker: clicker.send_double()
        else:
            if DEBOUNCE.should_fire("roll", (POSITION_ID, HERO_ID)):
                _do_roll()

# ===================== Состояние доски/матча =====================
LAST_GAME_STATE: Dict[str, Any] = {}
LAST_BOARD_DATA: Dict[str, Any] = {}

TURN_TOKEN = None
HINTS_SENT_THIS_TURN = 0
MOVED_THIS_TURN = False

def _now() -> float: return time.perf_counter()

def _reset_turn(owner_id, f, s):
    global TURN_TOKEN, HINTS_SENT_THIS_TURN, MOVED_THIS_TURN
    new_token = time.time() + random.random()
    TURN_TOKEN = (owner_id, f, s, new_token)
    HINTS_SENT_THIS_TURN, MOVED_THIS_TURN = 0, False

def _update_position_from(game_state_like: Dict[str, Any]):
    global POSITION_ID, LAST_GAME_STATE, LAST_BOARD_DATA
    if not isinstance(game_state_like, dict): 
        return
    game_state = game_state_like
    board_data = game_state.get('board')
    owner_for_pos = get_in(game_state, ['currentTurn', 'ownerId'])
    if not board_data or owner_for_pos is None:
        return
    pos = generate_position_id(board_data, game_state, owner_for_pos)
    if pos:
        POSITION_ID, LAST_GAME_STATE = pos, game_state
        LAST_BOARD_DATA = board_data or {}

def _update_match_score(payload: Dict[str, Any]):
    global MATCH_TO_SCORE, HERO_SCORE, OPPONENT_SCORE, HERO_ID, OPPONENT_ID
    game_params = get_in(payload, ['context', 'gameParams'], {})
    if game_params.get('winPointsCount'):
        MATCH_TO_SCORE = game_params.get('winPointsCount', 0)
    match_state = get_in(payload, ['data', 'matchState'], {})
    if match_state and HERO_ID and OPPONENT_ID:
        p1_id = match_state.get('participant1')
        p1_score = match_state.get('participant1Score', 0)
        p2_score = match_state.get('participant2Score', 0)
        new_hero_score, new_opp_score = (p1_score, p2_score) if p1_id == HERO_ID else (p2_score, p1_score)
        if HERO_SCORE != new_hero_score or OPPONENT_SCORE != new_opp_score:
            HERO_SCORE, OPPONENT_SCORE = new_hero_score, new_opp_score

def get_gnubg_ids_from_payload_simple(payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Старая сигнатура из твоего файла (оставил совместимость где вызывалась)."""
    return get_gnubg_ids_from_payload(payload, HERO_ID)

# ===================== Главный обработчик =====================
def process_log_entry(log_entry: Dict[str, Any]):
    global HERO_ID, OPPONENT_ID, START_SENT, END_SENT, current_game_id, HERO_STATE
    global POSITION_ID, first, second, TURN_TOKEN, MOVED_THIS_TURN, HINTS_SENT_THIS_TURN
    global DICE_ROLL_ATTEMPTS, LAST_DICE_ROLL_TIME, WAITING_FOR_DICE, DICE_ROLLED_RECEIVED
    global MATCH_TO_SCORE, HERO_SCORE, OPPONENT_SCORE, MATCH_ID, HERO_BOARD_PERSPECTIVE_IS_INVERTED 

    msg_type = log_entry.get('msgType')
    if not msg_type:
        return

    payload = get_in(log_entry, ['data', 'payload'], {})
    if not isinstance(payload, dict):
        return

    if get_in(payload, ['data', 'matchState']):
        _update_match_score(payload)

    ctx = extract_ctx(payload, HERO_ID)
    event_name = ctx["event_name"]
    stage = ctx["stage"]
    current_turn_owner = ctx["current_turn_owner"]
    f, s = ctx["dice_first"], ctx["dice_second"]

    # Новая игра
    new_game_id = get_in(payload, ['context', 'gameMatchId']) or get_in(payload, ['data', 'gameId'])
    if new_game_id and new_game_id != current_game_id:
        current_game_id = new_game_id
        START_SENT, END_SENT, HERO_ID, OPPONENT_ID = False, False, None, None

        # Определение HERO_ID
        p1_id = get_in(payload, ['context', 'players', 'first', 'userId']) or get_in(payload, ['data', 'players', 'first', 'userId']) or \
                get_in(payload, ['context', 'players', 'first', 'user', 'accountId']) or get_in(payload, ['data', 'players', 'first', 'user', 'accountId'])
        p2_id = get_in(payload, ['context', 'players', 'second', 'userId']) or get_in(payload, ['data', 'players', 'second', 'userId']) or \
                get_in(payload, ['context', 'players', 'second', 'user', 'accountId']) or get_in(payload, ['data', 'players', 'second', 'user', 'accountId'])

        HERO_ID = define_pid(p1_id, p2_id, OUR_PIDS) or p1_id
        OPPONENT_ID = (p2_id if HERO_ID == p1_id else p1_id) if (p1_id and p2_id and HERO_ID) else None

        # Печать шапки матча
        print_game_header(current_game_id,
                          (HERO_ID[:8] + "...") if HERO_ID else None,
                          (OPPONENT_ID[:8] + "...") if OPPONENT_ID else None)

    # Старт/конец матча — Telegram (без лишней печати)
    if msg_type == 'StageChanged' and stage == 'GamePlay' and not START_SENT:
        reset_turn_state()
        try:
            if data := _mk_start_data(payload):
                msg = format_match_start_message(data)
                run_async_task(send_notification(msg))
                START_SENT = True
        except Exception:
            pass

    if msg_type == 'StageEvent' and event_name == 'GameFinished' and not END_SENT:
        if HERO_ID:
            _update_match_score(payload)
            try:
                if data := _mk_end_data(payload):
                    msg = format_match_end_message(data)
                    run_async_task(send_notification(msg))
                    start_data = MATCH_START_DATA.get(current_game_id)
                    log_session(data, start_data)
                    MATCH_START_DATA.pop(current_game_id, None)
                    END_SENT = True
            except Exception:
                pass

    # Балансы
    if msg_type == 'StageChanged' and stage == 'Lobby':
        acc_info = get_in(payload, ['context', 'accountInfo'], {})
        if acc_info.get('id') == HERO_ID:
            balances_map = _balances_list_to_map(acc_info.get('balances', []))
            if balances_map:
                changes = {}
                for ctype in ["gold", "diamond", "chips"]:
                    new_val = balances_map.get(ctype)
                    old_val = LAST_HERO_BALANCES.get(ctype)
                    if new_val is not None:
                        if old_val is None:
                            LAST_HERO_BALANCES[ctype] = new_val
                        else:
                            delta = round(new_val - old_val, 2)
                            if abs(delta) >= 0.01:
                                changes[ctype] = {"delta": delta, "now": new_val}
                                LAST_HERO_BALANCES[ctype] = new_val
                if changes:
                    nickname = get_in(acc_info, ['profile', 'nickname']) or 'HERO'
                    send_balance_change_notification(nickname, changes)

    # Поддерживаем актуальный POSID
    if get_in(payload, ['data', 'gameState']) or get_in(payload, ['data', 'board']):
        _update_position_from(get_in(payload, ['data', 'gameState'], payload.get('data', {})))

    if event_name == "TurnCheckerMovedV2":
        MOVED_THIS_TURN = True

    IS_RESPOND_STATE = is_respond_state(ctx)
    CAN_ROLL_DICE = can_roll(ctx)
    CAN_OFFER_DOUBLE = can_offer_double(ctx)

    # posid/match_id для печати/запросов
    pos_id, match_id = get_gnubg_ids_from_payload(payload, HERO_ID)
    if pos_id:
        POSITION_ID = pos_id
    if match_id:
        MATCH_ID = match_id

    # ====== Куб и броски ======
    if IS_RESPOND_STATE:
        if DEBOUNCE.should_fire("cube_respond", (pos_id, match_id, HERO_ID, True)):
            double_respond(payload, HERO_ID, True)
        return

    if CAN_ROLL_DICE:
        if CAN_OFFER_DOUBLE and DEBOUNCE.should_fire("cube_offer", (pos_id, match_id, HERO_ID, False)):
            print('dbl respond')
            double_respond(payload, HERO_ID, False)
            return
        else:
            if DEBOUNCE.should_fire("roll", (POSITION_ID, HERO_ID)):
                print("jst roll")
                _do_roll()
            return

    # ====== Наш ход — спросить подсказку и напечатать DICE/POSID/MOVE ======
    if event_name in ["DiceRolled", "GameStarted"] and current_turn_owner and HERO_ID and current_turn_owner == HERO_ID:
        reset_turn_state()
        WAITING_FOR_DICE = False
        first, second = f, s
        _reset_turn(current_turn_owner, first, second)

        # Печатаем кости (если появились)
        print_dice(first, second)

        if DEBOUNCE.should_fire("plan", ("plan", POSITION_ID, first, second)):
            pos_id, match_id = get_gnubg_ids_from_payload(payload, HERO_ID)
            if pos_id and match_id and DEBOUNCE.should_fire("hint", (pos_id, match_id, f, s)):
                # Сразу печатаем POSID (полный)
                print_posid(pos_id)

                hint_respond_str = hint_request("game", pos_id, match_id, receiving_double=False, mode="COMBO")
                try:
                    hint_respond_dict = json.loads(hint_respond_str)
                except json.JSONDecodeError:
                    return

                # Получаем оригинальный план от GNUbg
                plan = hint_respond_dict.get("moves") or []
                optimized_plan = _optimize_move_plan(plan)
                TURN_STATE["plan_gnubg"] = optimized_plan

                print_moves(optimized_plan)

                if board_calculator and HERO_ID and optimized_plan:
                    try:
                        # 1. Парсим состояние доски из лога как обычно
                        log_entry_str = json.dumps(log_entry)
                        game_state = board_calculator.parse_game_state_from_log(log_entry_str)

                        # 2. Проверяем, нужно ли разворачивать доску
                        hero_start_pos = get_in(payload, ['data', 'playersStates', HERO_ID, 'boardStartPosition'])
                        
                        final_game_state_for_calc = game_state
                        if hero_start_pos == 0:
                            print("startPos: 0")
                            final_game_state_for_calc = logically_invert_board_state(game_state)

                        # 3. Передаем в калькулятор (потенциально инвертированное) состояние
                        #    и ОРИГИНАЛЬНЫЙ, НЕИЗМЕНЕННЫЙ план ходов.
                        if HERO_ID:
                            sequence_coords = board_calculator.calculate_full_move_sequence_coords(
                                final_game_state_for_calc, # <--- Используем подготовленное состояние
                                optimized_plan,            # <--- Используем ОРИГИНАЛЬНЫЙ план
                                HERO_ID,
                                is_inverted=HERO_BOARD_PERSPECTIVE_IS_INVERTED
                            )

                            moves_for_clicker = []
                            has_errors = False

                            # 1. Собрать все валидные ходы и вывести информацию в лог
                            for move, coords_result in zip(optimized_plan, sequence_coords):
                                error = coords_result.get('error')
                                if error:
                                    print(f"  └─ COORDS ERROR for {move}: {error}")
                                    has_errors = True  # Ставим флаг, что были ошибки
                                    #time.sleep(0.6)
                                    #clicker.turn_commit()
                                    break  # Прерываем, если есть ошибка, т.к. план невыполним

                                from_c = coords_result.get('from')
                                to_c = coords_result.get('to')
                                #print(f"  └─ COORDS for {move}: FROM {from_c} -> TO {to_c}")
                                
                                if from_c and to_c:
                                    moves_for_clicker.append({
                                        'from': from_c,
                                        'to': to_c,
                                        'move_str': move  # Добавляем оригинальную строку хода для логов кликера
                                    })

                            # 2. Если не было ошибок и есть кликер, выполнить ходы
                            if not has_errors and clicker and moves_for_clicker:
                                print(f"[CLICKER] План из {len(moves_for_clicker)} ходов передан на исполнение...")
                                
                                # Генерируем новый "ритм" для движений этого хода
                                clicker.generate_new_turn_multiplier()
                                
                                # Передаем токен хода для безопасности, чтобы не выполнить старые команды
                                clicker.update_turn_token(TURN_TOKEN)
                                
                                # Выполняем ходы
                                clicker.move_checkers(moves_for_clicker, TURN_TOKEN)
                                
                                # Завершаем ход (нажимаем кнопку "готово")
                                clicker.turn_commit()
                                print(f"[CLICKER] Ход выполнен и завершен.")
                            elif has_errors:
                                print(f"[CLICKER] План не выполнен из-за ошибок в расчете координат.")
                                time.sleep(0.6)
                                clicker.turn_commit()
                                try:
                                    # Пытаемся найти состояние проблемной точки в исходном состоянии игры
                                    failed_move = next((m for m, c in zip(optimized_plan, sequence_coords) if c.get('error')), None)
                                    if failed_move:
                                        from_point_str = failed_move.replace('*', '').split('/')[0]
                                        if from_point_str.isdigit():
                                            from_point_num = int(from_point_str)
                                            # Инвертируем для поиска, если доска перевернута
                                            if HERO_BOARD_PERSPECTIVE_IS_INVERTED:
                                                from_point_num = 25 - from_point_num

                                            point_state = next((p for p in game_state['board']['points'] if p.get('number') == from_point_num), None)
                                            if point_state:
                                                owner = point_state.get('occupiedBy', 'empty')
                                                count = point_state.get('checkersCount', 0)
                                                print(f"  └─ DEBUG: Состояние точки {from_point_num} (в логе): Владелец: {owner[:8]}..., Шашек: {count}. (HERO ID: {HERO_ID[:8]}...){log_entry_str}")
                                            else:
                                                print(f"  └─ DEBUG: Точка {from_point_num} не найдена в исходном состоянии доски.")
                                except Exception as e:
                                    print(f"  └─ DEBUG: Не удалось получить доп. информацию об ошибке: {e}")
                    except Exception as e:
                        print(f"  └─ [CRITICAL] Внутренняя ошибка калькулятора или кликера: {e}")
            else:
                # Если подсказку не смогли — хотя бы POSID покажем
                print_posid(pos_id)


    # Если подсказка пришла отдельным сообщением
    if payload.get("type") == "Hint" or "moves" in payload:
        if POSITION_ID:
            print_posid(POSITION_ID)
        mv = payload.get("moves") or []
        print_moves(mv)
        return

# ===================== Завершение =====================
def on_match_end(result: Optional[str] = None):
    if result:
        print(f"\n=== Игра завершена: {result} ===\n")
