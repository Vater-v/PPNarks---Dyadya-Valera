# coords.py (СУПЕР-УПРОЩЕННАЯ ВЕРСИЯ БЕЗ ВИЗУАЛЬНОЙ ИНВЕРСИИ)
import json
from typing import Dict, Tuple, Union, List
import copy

class BackgammonBoard:
    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.settings = self.config.get('settings', {})
        self.board_height = self.config.get('board_pixel_height', 1275)

    @staticmethod
    def parse_game_state_from_log(full_log_str: str) -> Dict:
        log_data = json.loads(full_log_str)
        game_data = log_data['data']['payload']['data']
        players_info = {}
        for p_key in ['first', 'second']:
            player_data = game_data.get('players', {}).get(p_key)
            if not player_data: continue
            uuid = player_data['userId']
            players_info[uuid] = {"color": player_data['checkerColor']}
        return { "players_info": players_info, "board": game_data['board'] }

    def _get_single_move_coords(self, current_state: Dict, from_point: Union[int, str], to_point: Union[int, str], player_uuid: str, **kwargs) -> Dict:
        # **kwargs добавлен, чтобы код не падал, если log_handle.py все еще передает is_inverted
        players_info = current_state['players_info']
        opponent_uuid = next((uuid for uuid in players_info if uuid != player_uuid), None)
        board_points = current_state['board']['points']
        from_xy, to_xy, error_msg = None, None, None
        
        from_data = next((p for p in board_points if p.get('number') == from_point), None) if from_point != 'bar' else {"info": "bar"}
        to_data = next((p for p in board_points if p.get('number') == to_point), None) if to_point != 'off' else {"info": "off"}

        if from_point == 'bar':
            bar_count = current_state['board']['barCounts'].get(player_uuid, 0)
            if bar_count > 0:
                bar_config = self.config['bar']['hero']
                base_coords, direction, step_y = bar_config['base_coords'], bar_config['direction'], bar_config['step_y']
                from_xy = (base_coords[0], base_coords[1] + ((bar_count - 1) * step_y * direction))
            else:
                error_msg = f"FROM 'bar': на баре нет шашек игрока."
        else:
            point_data = from_data
            if not point_data: error_msg = f"FROM {from_point}: пункт не найден."
            elif point_data.get('occupiedBy') != player_uuid: error_msg = f"FROM {from_point}: попытка хода с чужого/пустого пункта."
            else:
                checkers_count = point_data['checkersCount']
                point_config = self.config['points'][str(from_point)]
                base_coords, direction, step_y = point_config['base_coords'], point_config['direction'], self.settings.get('checker_step_y', 40)
                from_xy = (base_coords[0], base_coords[1] + ((checkers_count - 1) * step_y * direction))

        if error_msg: return {'from': None, 'to': None, 'error': error_msg}

        if to_point == 'off':
            to_xy = (self.config['special_points']['off']['x'], self.config['special_points']['off']['y'])
        else:
            point_data = to_data
            if not point_data: error_msg = f"TO {to_point}: пункт не найден."
            else:
                point_config = self.config['points'][str(to_point)]
                base_coords, direction, step_y = point_config['base_coords'], point_config['direction'], self.settings.get('checker_step_y', 40)
                occupied_by, checkers_count = point_data.get('occupiedBy'), point_data.get('checkersCount', 0)
                is_blot = occupied_by == opponent_uuid and checkers_count == 1
                is_blocked = occupied_by == opponent_uuid and checkers_count >= 2
                if is_blocked: error_msg = f"TO {to_point}: пункт заблокирован ({checkers_count} шашки)."
                elif point_data.get('isFreePoint') or is_blot or occupied_by == player_uuid:
                    next_idx = checkers_count if occupied_by == player_uuid else 0
                    to_xy = (base_coords[0], base_coords[1] + (next_idx * step_y * direction))
                else: error_msg = f"TO {to_point}: неизвестная ошибка."
        
        ### ГЛАВНОЕ ИЗМЕНЕНИЕ: ЛОГИКА ИНВЕРСИИ ПОЛНОСТЬЮ УДАЛЕНА ###
               
        return {'from': from_xy, 'to': to_xy, 'error': error_msg}

    def calculate_full_move_sequence_coords(self, initial_game_state: Dict, move_plan: List[str], player_uuid: str, **kwargs) -> List[Dict]:
        # Этот метод остается без изменений
        if not move_plan: return []
        simulated_state = copy.deepcopy(initial_game_state)
        points_map = {p['number']: p for p in simulated_state['board']['points']}
        all_move_coords = []
        for move_str in move_plan:
            parts = move_str.replace('*', '').split('/')
            if len(parts) != 2: continue
            from_p = int(parts[0]) if parts[0].isdigit() else parts[0]
            to_p = int(parts[1]) if parts[1].isdigit() else parts[1]
            coords_result = self._get_single_move_coords(simulated_state, from_p, to_p, player_uuid)
            all_move_coords.append(coords_result)
            if coords_result.get('error'): break 
            # ... остальная часть симуляции без изменений ...
            if from_p != 'bar':
                points_map[from_p]['checkersCount'] -= 1
                if points_map[from_p]['checkersCount'] == 0:
                    points_map[from_p]['isFreePoint'] = True
                    points_map[from_p].pop('occupiedBy', None)
            else:
                simulated_state['board']['barCounts'][player_uuid] -= 1
            if to_p != 'off':
                opponent_uuid = next((uuid for uuid in simulated_state['players_info'] if uuid != player_uuid), None)
                is_hit = points_map[to_p].get('occupiedBy') == opponent_uuid and points_map[to_p]['checkersCount'] == 1
                if is_hit:
                    simulated_state['board']['barCounts'].setdefault(opponent_uuid, 0)
                    simulated_state['board']['barCounts'][opponent_uuid] += 1
                    points_map[to_p]['checkersCount'] = 1
                else:
                    points_map[to_p]['checkersCount'] += 1
                points_map[to_p]['isFreePoint'] = False
                points_map[to_p]['occupiedBy'] = player_uuid
        while len(all_move_coords) < len(move_plan):
            all_move_coords.append({'from': None, 'to': None, 'error': 'Симуляция прервана из-за предыдущей ошибки.'})
        return all_move_coords