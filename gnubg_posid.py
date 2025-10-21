import base64
from typing import Any, Dict

# Вспомогательная функция для безопасного доступа (необходима здесь)
def get_in(d: Any, path: list, default=None):
    cur = d
    if not isinstance(cur, dict): return default
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def get_movement_direction(game_state: Dict[str, Any], player_id: str) -> str:
    """
    Определяет направление движения: '1_to_24' (Снизу, BSP=0) или '24_to_1' (Сверху, BSP=23).
    """
    def check_bsp(ps_data):
        if isinstance(ps_data, dict):
            player_state = ps_data.get(player_id) or {}
            bsp = player_state.get('boardStartPosition')
            if bsp == 0: return '1_to_24'
            if bsp == 23: return '24_to_1'
        return None

    # Проверяем стандартные места для playersStates
    result = check_bsp(get_in(game_state, ['playersStates']))
    if result: return result
    result = check_bsp(get_in(game_state, ['data', 'playersStates'])) # На случай если передан payload
    if result: return result
    result = check_bsp(get_in(game_state, ['gameBoardState', 'playersStates']))
    if result: return result

    # Фолбэк на players.first/second (менее надежно)
    first_player_id = get_in(game_state, ['players', 'first', 'userId'])
    if first_player_id:
        # Стандартное предположение GNUbg: Первый игрок движется 24->1.
        return '24_to_1' if player_id == first_player_id else '1_to_24'

    return '24_to_1' # По умолчанию

def generate_position_id(board_data, game_state, player_on_roll_id):
    """
    Генерирует стандартный Position ID. 
    GNUbg ожидает, что игрок на ходу (POR) движется к пункту 1 (24->1).
    """
    if not all([board_data, game_state, player_on_roll_id]):
        return None
    
    # --- Шаг 1: Определение Перспектив ---
    players = get_in(game_state, ['players'])
    if not players:
        players = get_in(game_state, ['data', 'players'])
        if not players: return None
    
    pids = []
    p1_id = get_in(players, ['first', 'userId'])
    p2_id = get_in(players, ['second', 'userId'])
    if p1_id: pids.append(p1_id)
    if p2_id: pids.append(p2_id)
    
    if len(pids) != 2: return None

    player_not_on_roll_id = next((p for p in pids if p != player_on_roll_id), None)
    if not player_not_on_roll_id: return None

    # Определяем направление движения для игрока на ходу
    dir_on_roll = get_movement_direction(game_state, player_on_roll_id)

    checkers = {pid: [0] * 25 for pid in pids}
    
    # Заполняем бар
    for pid in pids:
        checkers[pid][0] = board_data.get('barCounts', {}).get(pid, 0)
        
    # Заполняем поля, применяя корректную трансформацию
    for point in board_data.get('points', []):
        point_num = point.get('number')
        owner = point.get('occupiedBy')
        count = point.get('checkersCount', 0)
        
        if owner not in checkers: continue

        # Логика трансформации (Стандартный Position ID):
        if owner == player_on_roll_id:
            if dir_on_roll == '1_to_24':
                # POR движется 1->24. GNUbg ожидает 24->1. Нужно перевернуть.
                checkers[owner][25 - point_num] = count
            else:
                # POR движется 24->1. Совпадает с GNUbg. Оставляем как есть.
                checkers[owner][point_num] = count
        else: # Оппонент
            if dir_on_roll == '1_to_24':
                # POR перевернут. Оппонент движется 24->1. Оставляем как есть.
                checkers[owner][point_num] = count
            else:
                # POR как есть. Оппонент движется 1->24. Нужно перевернуть.
                checkers[owner][25 - point_num] = count

    # --- Шаг 2: Генерация битовой строки (остается без изменений) ---
    bit_list = []
    
    def append_player_data(player_id):
        for i in range(1, 25):
            bit_list.extend(['1'] * checkers[player_id][i])
            bit_list.append('0')
        bit_list.extend(['1'] * checkers[player_id][0])
        bit_list.append('0')

    # ВАЖНО: Сначала данные оппонента, затем данные игрока на ходу.
    append_player_data(player_not_on_roll_id)
    append_player_data(player_on_roll_id)

    padding_needed = 80 - len(bit_list)
    if padding_needed > 0:
        bit_list.extend(['0'] * padding_needed)
    
    bit_string = "".join(bit_list)

    byte_list = []
    for i in range(0, 80, 8):
        eight_bits = bit_string[i:i+8]
        reversed_bits = eight_bits[::-1]
        byte_value = int(reversed_bits, 2)
        byte_list.append(byte_value)
        
    key = bytes(byte_list)

    encoded_key = base64.b64encode(key)
    position_id = encoded_key.decode('ascii')[:14]
    
    # print(f"Сгеренировал POS_ID: {position_id}")
    return position_id



def _bits_to_le_bytes_66bits(bits: str) -> bytes:
    # bits: строка из '0'/'1', длиной ровно 66
    assert len(bits) == 66
    # Пакуем в 9 байт (66 бит), little-endian по БИТАМ внутри байта:
    out = bytearray(9)
    bit_index = 0
    for byte_i in range(9):
        val = 0
        for b in range(8):
            if bit_index < 66 and bits[bit_index] == '1':
                val |= (1 << b)   # младший бит — первый по порядку в строке
            bit_index += 1
        out[byte_i] = val
    return bytes(out)

def _uN_to_bits_le(n: int, width: int) -> str:
    # Возвращаем строку бит '0'/'1' длиной width, с МЛАДШИМИ битами ВПЕРЕДИ (т.е. порядок: b0, b1, ...),
    # чтобы потом _bits_to_le_bytes_66bits читала по порядку.
    bits = []
    for i in range(width):
        bits.append('1' if (n >> i) & 1 else '0')
    return ''.join(bits)

def generate_match_id(
    *,
    match_length: int,         # 0 для money game
    score_p0: int, score_p1: int,
    cube_value: int,           # 1,2,4,8,...
    cube_owner: int | None,    # 0,1 или None (центр)
    player_on_roll: int,       # 0 или 1
    turn_owner: int,           # 0 или 1 (чья очередь решать: ход/принимать дабл/резайн)
    is_crawford: bool,
    is_double_offered: bool,   # 1 если ДАБЛ предложен сейчас
    resign_flag: int,          # 0=none, 1=single, 2=gammon, 3=backgammon
    die1: int | None, die2: int | None,   # 1..6 или None (0 по протоколу = «не брошено»)
) -> str:
    # Bit поля (в указанном порядке; все — LE внутри общего потока):
    #  1-4   Cube (log2)   width=4
    #  5-6   CubeOwner     width=2  (00 p0, 01 p1, 11 center)
    #  7     DiceOwner     width=1  (кто «на броске»/кто бросил) — упростим = player_on_roll
    #  8     Crawford      width=1
    #  9-11  GameState     width=3  (001 playing, 000 no game, ...)
    #  12    TurnOwner     width=1
    #  13    Double        width=1
    #  14-15 Resign        width=2
    #  16-18 Dice1         width=3 (0 если нет, иначе 1..6 в двоичном виде)
    #  19-21 Dice2         width=3
    #  22-36 MatchLen      width=15
    #  37-51 Score p0      width=15
    #  52-66 Score p1      width=15

    # 1) cube log2
    log2 = 0
    v = cube_value
    while v > 1:
        v >>= 1
        log2 += 1
    cube_bits = _uN_to_bits_le(log2, 4)

    # 2) owner
    if cube_owner is None:
        owner_code = 0b11
    elif cube_owner == 0:
        owner_code = 0b00
    elif cube_owner == 1:
        owner_code = 0b01
    else:
        raise ValueError("cube_owner must be 0,1 or None")
    owner_bits = _uN_to_bits_le(owner_code, 2)

    # 3) dice owner (player on roll)
    dice_owner_bits = _uN_to_bits_le(player_on_roll, 1)

    # 4) crawford
    crawford_bits = _uN_to_bits_le(1 if is_crawford else 0, 1)

    # 5) game state: игра идёт -> 001
    game_state_bits = _uN_to_bits_le(0b001, 3)

    # 6) turn owner (кто принимает решение прямо сейчас)
    turn_owner_bits = _uN_to_bits_le(turn_owner, 1)

    # 7) double flag
    double_bits = _uN_to_bits_le(1 if is_double_offered else 0, 1)

    # 8) resign
    resign_bits = _uN_to_bits_le(resign_flag, 2)

    # 9) dice1/dice2 (0 если нет броска)
    d1 = 0 if die1 is None else int(die1)
    d2 = 0 if die2 is None else int(die2)
    dice1_bits = _uN_to_bits_le(d1, 3)
    dice2_bits = _uN_to_bits_le(d2, 3)

    # 10) match len, scores
    ml_bits = _uN_to_bits_le(match_length, 15)
    s0_bits = _uN_to_bits_le(score_p0, 15)
    s1_bits = _uN_to_bits_le(score_p1, 15)

    bits = (
        cube_bits + owner_bits + dice_owner_bits + crawford_bits +
        game_state_bits + turn_owner_bits + double_bits + resign_bits +
        dice1_bits + dice2_bits + ml_bits + s0_bits + s1_bits
    )
    assert len(bits) == 66

    key = _bits_to_le_bytes_66bits(bits)

    # Base64 без паддинга, 12 символов
    mid = base64.b64encode(key).decode('ascii').rstrip('=')
    return mid

def decode_position_id(pos_id: str):
    """
    Декодирует Position ID обратно в количество шашек на доске.
    Возвращает {'p1_checkers': [0]*25, 'p2_checkers': [0]*25},
    где p1 - игрок НЕ на ходе, p2 - игрок НА ходе.
    Индекс [0] - бар, [1-24] - пункты в "мировоззрении" GNUbg (от 1 до 24).
    """
    try:
        padded_id = pos_id + '=' * (-len(pos_id) % 4)
        key_bytes = base64.b64decode(padded_id)
    except Exception:
        return None

    bit_list = [format(byte, '08b')[::-1] for byte in key_bytes]
    bit_string = "".join(bit_list)[:80]

    if len(bit_string) < 80: return None

    checkers = {'p1_checkers': [0] * 25, 'p2_checkers': [0] * 25}
    players = ['p1_checkers', 'p2_checkers']
    
    current_bit = 0
    for player_key in players:
        # Сначала пункты с 1 по 24
        for point_index in range(1, 25):
            count = 0
            while current_bit < 80 and bit_string[current_bit] == '1':
                count += 1
                current_bit += 1
            checkers[player_key][point_index] = count
            if current_bit < 80: current_bit += 1 
            
        # Затем бар (индекс 0)
        count = 0
        while current_bit < 80 and bit_string[current_bit] == '1':
            count += 1
            current_bit += 1
        checkers[player_key][0] = count
        if current_bit < 80: current_bit += 1

    return checkers