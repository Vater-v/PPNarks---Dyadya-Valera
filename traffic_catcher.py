import datetime
import zlib
import json
from mitmproxy import http, tcp
import os

# --- ИЗМЕНЕНИЕ ---
# Читаем путь из переменной окружения, если ее нет - используем log.txt по умолчанию
LOG_FILE = os.getenv("MITM_LOG_FILE", "log.txt")
# Фильтры для исключения шумовых сообщений
EXCLUDE_MESSAGE_TYPES = {"Ping", "Pong", "KeepAlive", "Heartbeat"}
EXCLUDE_PATHS = {"/health", "/metrics", "/ping"}


def should_log(data: dict, url: str = "") -> bool:
    """Определяет, нужно ли логировать данное сообщение."""
    # Гарантируем ожидаемый тип
    if not isinstance(data, dict):
        return False

    # Проверяем URL пути
    for path in EXCLUDE_PATHS:
        if path in url.lower():
            return False

    # Проверяем типы сообщений (для WebSocket)
    msg_type = data.get("type", "")
    if msg_type in EXCLUDE_MESSAGE_TYPES:
        return False

    # Проверяем вложенные типы
    payload = data.get("payload", {})
    if isinstance(payload, dict):
        nested_type = payload.get("type", "")
        if nested_type in EXCLUDE_MESSAGE_TYPES:
            return False

    return True


def clean_json_data(data: dict) -> dict:
    """Удаляет дублирующиеся поля и лишние данные."""
    
    def clean_recursive(obj):
        if isinstance(obj, dict):
            cleaned = {}
            seen_keys = set()
            
            for key, value in obj.items():
                # Преобразуем snake_case ключи в camelCase для единообразия
                camel_key = key
                if "_" in key:
                    parts = key.split("_")
                    camel_key = parts[0] + "".join(p.capitalize() for p in parts[1:])
                
                # Пропускаем дубликаты (приоритет у camelCase)
                base_key = camel_key.lower().replace("_", "")
                if base_key not in seen_keys:
                    seen_keys.add(base_key)
                    cleaned[camel_key] = clean_recursive(value)
            
            return cleaned
        elif isinstance(obj, list):
            return [clean_recursive(item) for item in obj]
        else:
            return obj
    
    return clean_recursive(data)


def parse_as_json(data: bytes) -> dict | None:
    """
    Пытается распарсить данные как JSON и возвращает только dict.
    Если верхний уровень не словарь (строка, число, список, null) — вернёт None.
    """
    def _loads_to_dict(b: bytes) -> dict | None:
        obj = json.loads(b.decode("utf-8"))
        return obj if isinstance(obj, dict) else None

    # Attempt 1: Direct UTF-8 JSON
    try:
        parsed = _loads_to_dict(data)
        if parsed is not None:
            return parsed
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass

    # Attempt 2: Raw DEFLATE
    try:
        decompressed = zlib.decompress(data, -zlib.MAX_WBITS)
        parsed = _loads_to_dict(decompressed)
        if parsed is not None:
            return parsed
    except (zlib.error, UnicodeDecodeError, json.JSONDecodeError):
        pass

    # Attempt 3: Gzip
    try:
        decompressed = zlib.decompress(data, 16 + zlib.MAX_WBITS)
        parsed = _loads_to_dict(decompressed)
        if parsed is not None:
            return parsed
    except (zlib.error, UnicodeDecodeError, json.JSONDecodeError):
        pass

    return None


def log_json_line(log_entry: dict):
    """Записывает JSON в одну строку в лог-файл."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        # Compact JSON - всё в одну строку, без лишних пробелов
        f.write(json.dumps(log_entry, ensure_ascii=False, separators=(",", ":")) + "\n")


class JsonTrafficLogger:
    """
    Mitmproxy addon для логирования JSON трафика в машиночитаемом формате.
    """
    
    def request(self, flow: http.HTTPFlow):
        """Обрабатывает HTTP запросы."""
        if not flow.request or not flow.request.content:
            return
        
        parsed = parse_as_json(flow.request.content)
        if parsed and should_log(parsed, flow.request.pretty_url):
            cleaned = clean_json_data(parsed)
            
            log_entry = {
                "t": datetime.datetime.utcnow().isoformat() + "Z",  # timestamp
                "src": "http_req",  # source type
                "method": flow.request.method,
                "url": flow.request.pretty_url,
                "data": cleaned
            }
            log_json_line(log_entry)
    
    def response(self, flow: http.HTTPFlow):
        """Обрабатывает HTTP ответы."""
        if not flow.response or not flow.response.content:
            return
        
        parsed = parse_as_json(flow.response.content)
        if parsed and should_log(parsed, flow.request.pretty_url):
            cleaned = clean_json_data(parsed)
            
            log_entry = {
                "t": datetime.datetime.utcnow().isoformat() + "Z",
                "src": "http_res",
                "method": flow.request.method,
                "url": flow.request.pretty_url,
                "status": flow.response.status_code,
                "data": cleaned
            }
            log_json_line(log_entry)
    
    def websocket_message(self, flow: http.HTTPFlow):
        """Обрабатывает WebSocket сообщения."""
        message = flow.websocket.messages[-1]
        content_bytes = message.text.encode("utf-8") if message.is_text else message.content
        
        parsed = parse_as_json(content_bytes)
        if parsed and should_log(parsed, flow.request.pretty_url):
            cleaned = clean_json_data(parsed)
            
            # Извлекаем важные метаданные если есть
            msg_id = cleaned.get("id")
            msg_type = cleaned.get("type")
            client_msg_id = cleaned.get("clientMessageId")
            
            log_entry = {
                "t": datetime.datetime.utcnow().isoformat() + "Z",
                "src": "ws",
                "dir": "c2s" if message.from_client else "s2c",  # direction
                "url": flow.request.pretty_url
            }
            
            # Добавляем метаданные на верхний уровень для быстрого поиска
            if msg_id:
                log_entry["msgId"] = msg_id
            if msg_type:
                log_entry["msgType"] = msg_type
            if client_msg_id:
                log_entry["clientMsgId"] = client_msg_id
            
            log_entry["data"] = cleaned
            log_json_line(log_entry)
    
    def tcp_message(self, flow: tcp.TCPFlow):
        """Обрабатывает TCP сообщения."""
        message = flow.messages[-1]
        
        parsed = parse_as_json(message.content)
        if parsed:
            cleaned = clean_json_data(parsed)
            
            server_addr = f"{flow.server_conn.address[0]}:{flow.server_conn.address[1]}"
            
            log_entry = {
                "t": datetime.datetime.utcnow().isoformat() + "Z",
                "src": "tcp",
                "dir": "c2s" if message.from_client else "s2c",
                "server": server_addr,
                "data": cleaned
            }
            log_json_line(log_entry)

addons = [
    JsonTrafficLogger()
]