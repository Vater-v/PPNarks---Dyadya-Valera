# utils.py
from typing import Any, Dict, Optional

def get_in(d: Any, path: list, default=None):
    """
    Безопасно извлекает вложенное значение из словаря по пути.
    Оптимизировано для раннего выхода при None или неверном типе.
    """
    if d is None:
        return default

    # Убедимся, что входные данные похожи на словарь
    if not isinstance(d, dict):
        return default

    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur

# Кеш для clean_string
_clean_cache = {}

def clean_string(val: Any, default: str = "N/A") -> str:
    """
    Очищает значение: strip() и проверка на None/'null'.
    Возвращает default, если значение пустое. С кешированием.
    """
    if val is None:
        return default
    
    cache_key = (val, default)
    if cache_key in _clean_cache:
        return _clean_cache[cache_key]
    
    s = str(val).strip()
    result = default if s == "" or s.lower() == "null" else s
    
    # Кешируем только небольшие строки
    if len(str(val)) < 100:
        _clean_cache[cache_key] = result
    
    return result

def balances_list_to_map(balances_list: Optional[list]) -> Dict[str, float]:
    """
    Конвертирует список балансов в словарь {'gold': 100.0}.
    Обрабатывает разные форматы чисел.
    """
    if not balances_list:
        return {}
    
    out = {}
    for b in balances_list:
        ctype, amt = b.get("amountType"), b.get("amount")
        if not ctype or amt is None: 
            continue
        try: 
            out[ctype] = float(amt)
        except (ValueError, TypeError):
            try: 
                # Обработка строк с запятой как разделителем
                out[ctype] = float(str(amt).replace(",", "."))
            except: 
                pass
    return out