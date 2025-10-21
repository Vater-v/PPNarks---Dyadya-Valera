# message_formatter.py
from typing import Dict, Any
from utils import clean_string # Эта функция тоже используется
from constants import CURRENCY_MAP, MATCH_TYPE_MAP, PLAYER_TYPE_MAP # Импортируем константы

def format_match_start_message(data: Dict[str, Any]) -> str:
    """Форматирует красивое и подробное сообщение о начале матча."""
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

def format_balance_change_message(data: Dict[str, Any]) -> str:
    nickname, changes = data.get("nickname", "HERO"), data.get("changes", {})
    if not changes: 
        return ""

    lines = [
        f"{'➕' if info.get('delta', 0.0) >= 0 else '➖'} `{ctype}` ({CURRENCY_MAP.get(ctype, ctype)}): "
        f"{info.get('delta', 0.0):+.2f} → теперь `{info.get('now', 0.0):.2f}`"
        for ctype, info in changes.items()
    ]

    return f"💳 **Изменение баланса**\n👤 Аккаунт: `{nickname}`\n" + "\n".join(lines)

def format_match_end_message(data: Dict[str, Any]) -> str:
    """Форматирует красивое и подробное сообщение об окончании матча."""
    
    hero_nick = data.get('hero_nickname', 'Неизвестно')
    hero_id = data.get('hero_id', 'N/A')
    club = data.get('hero_club', 'N/A')
    opp_nick = data.get('opp_nickname', 'Неизвестно')
    vill_id = data.get('vill_id', 'N/A')
    variant = data.get('game_variant', 'Короткие нарды')
    bet = data.get('bet_amount', '0')
    currency = data.get('bet_currency', '')
    match_type = data.get('match_type', 'Обычный матч')
    player_type = data.get('player_type', '')

    winner = data.get('winner', 'Неизвестно')
    result = data.get('result_score', '')
    profit = data.get('profit', None)
    duration = data.get('duration', '')

    message = (
        f"🏁 **Матч завершён!**\n"
        f"- - - - - - - - - - - - - - - -\n"
        f"💰 **Ставка**: `{bet} {currency}`\n"
        f"🏆 **Победитель:** `{winner}`\n"
    )

    if result:
        message += f"📊 **Счёт:** `{result}`\n"

    if profit is not None:
        sign = "➕" if profit >= 0 else "➖"
        message += f"💵 **Результат для нас:** {sign}`{profit} {currency}`\n"

    if duration:
        message += f"⏱ **Длительность:** {duration}\n"

    message += "━━━━━━━━━━━━━━━"
    return message
