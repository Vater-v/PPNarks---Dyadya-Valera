import os
import datetime
import json
from mitmproxy import http, tcp, ctx

# --- КОНФИГУРАЦИЯ ---
# По умолчанию абсолютный файл, чтобы исключить путаницу с cwd.
LOG_FILE = os.getenv("MITM_LOG_FILE", r"C:\Users\Vater\Desktop\traffic.log.txt")

def format_content(content_bytes: bytes) -> dict:
    if not content_bytes:
        return {"bytes": 0, "text": "", "hex": ""}
    try:
        text_content = content_bytes.decode('utf-8')
    except Exception:
        text_content = None
    return {
        "bytes": len(content_bytes),
        "text": text_content,
        "hex": content_bytes.hex()
    }

def log_event(event_data: dict):
    try:
        # Убедимся, что папка существует
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception as e:
        # Если запись не удалась — сообщение в консоль mitmproxy
        ctx.log.error(f"Не удалось записать в лог-файл '{LOG_FILE}': {e}")

class UltimateCatcher:
    def __init__(self):
        ctx.log.info(f"UltimateCatcher initializing. Log file: {LOG_FILE}")

    def request(self, flow: http.HTTPFlow):
        try:
            log_event({
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "eventType": "http_request",
                "flowId": str(flow.id),
                "method": flow.request.method,
                "url": flow.request.pretty_url,
                "headers": dict(flow.request.headers),
                "content": format_content(flow.request.content)
            })
        except Exception as e:
            ctx.log.error(f"Ошибка в request(): {e}")

    def response(self, flow: http.HTTPFlow):
        try:
            log_event({
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "eventType": "http_response",
                "flowId": str(flow.id),
                "statusCode": flow.response.status_code,
                "reason": getattr(flow.response, "reason", ""),
                "headers": dict(flow.response.headers),
                "content": format_content(flow.response.content)
            })
        except Exception as e:
            ctx.log.error(f"Ошибка в response(): {e}")

    def websocket_start(self, flow: http.HTTPFlow):
        try:
            log_event({
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "eventType": "websocket_start",
                "flowId": str(flow.id),
                "url": flow.request.pretty_url
            })
        except Exception as e:
            ctx.log.error(f"Ошибка в websocket_start(): {e}")

    def websocket_message(self, flow: http.HTTPFlow):
        try:
            # Защищённый доступ — только если есть сообщения
            msgs = getattr(flow.websocket, "messages", None)
            if msgs:
                message = msgs[-1]
                log_event({
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                    "eventType": "websocket_message",
                    "flowId": str(flow.id),
                    "direction": "c2s" if getattr(message, "from_client", False) else "s2c",
                    "content": format_content(getattr(message, "content", b""))
                })
        except Exception as e:
            ctx.log.error(f"Ошибка в websocket_message(): {e}")

    def tcp_start(self, flow: tcp.TCPFlow):
        try:
            addr = ""
            try:
                addr = f"{flow.server_conn.address[0]}:{flow.server_conn.address[1]}"
            except Exception:
                addr = str(getattr(flow, "server_conn", None))
            log_event({
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "eventType": "tcp_start",
                "flowId": str(flow.id),
                "serverAddress": addr
            })
        except Exception as e:
            ctx.log.error(f"Ошибка в tcp_start(): {e}")

    def tcp_message(self, flow: tcp.TCPFlow):
        try:
            msgs = getattr(flow, "messages", None)
            if msgs:
                message = msgs[-1]
                log_event({
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                    "eventType": "tcp_message",
                    "flowId": str(flow.id),
                    "direction": "c2s" if getattr(message, "from_client", False) else "s2c",
                    "content": format_content(getattr(message, "content", b""))
                })
        except Exception as e:
            ctx.log.error(f"Ошибка в tcp_message(): {e}")

    def running(self):
        ctx.log.info(f"--- 'Тотальный перехватчик' запущен. Логи пишутся в файл: {LOG_FILE} ---")

addons = [
    UltimateCatcher()
]
