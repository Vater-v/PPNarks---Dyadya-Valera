# constants.py

"""
Здесь хранятся статические словари-преобразователи (карты) 
для всего проекта.
"""

CURRENCY_MAP = {
    'gold': 'фантиков', 
    'diamond': 'кристаллов', 
    'club_chips': 'клубных фишек'
}

VARIANT_MAP = {
    'ShortGammon': 'Короткие нарды', 
    'HyperGammon': 'Гипер-нарды'
}

MATCH_TYPE_MAP = {
    'ClassicMoneyGame': 'Игра на деньги', 
    'ProMoneyGame': 'Турнир'
}

PLAYER_TYPE_MAP = {
    'Any': 'скорее не бот', 
    'account': 'не бот наверн', 
    'Real': 'точно не бот'
}