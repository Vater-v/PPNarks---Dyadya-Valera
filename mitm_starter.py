# mitm_starter.py — версия для HTTP upstream с видимой консолью mitmdump (Windows)
import subprocess
import sys
from urllib.parse import urlparse, unquote
import os

def get_path(filename):
    """Определяет путь к файлу, который лежит рядом с exe."""
    if getattr(sys, 'frozen', False):
        # Если программа скомпилирована (запущена как .exe)
        application_path = os.path.dirname(sys.executable)
    else:
        # Если запускается как обычный .py скрипт
        application_path = os.path.dirname(__file__)
    return os.path.join(application_path, filename)

def StartMitm(port: int = 8080, upstream_proxy: str = None):
    """
    Формирует и запускает mitmdump:
    - если upstream_proxy содержит http(s)://user:pass@host:port -> вынесет user:pass в --upstream-auth
    - откроет mitmdump в новой консоли на Windows (CREATE_NEW_CONSOLE), чтобы вы видели вывод
    Возвращает Popen или None.
    """

    command = [
        "mitmdump",
        "-s", "traffic_catcher.py",
        "--listen-port", str(port),
        "--ssl-insecure"
    ]

    if upstream_proxy:
        parsed = urlparse(upstream_proxy)
        scheme = (parsed.scheme or "http").lower()

        # Примем только http/https для этого варианта
        if scheme not in ("http", "https"):
            print(f"⚠️ Внимание: обработка только http/https в этом режиме. Получена схема: {scheme}")
            # попробуем передать как есть (но mitmdump может ругнуться)
            command.extend(["--mode", f"upstream:{upstream_proxy}"])
        else:
            # Собираем адрес без userinfo
            host = parsed.hostname
            port_parsed = parsed.port
            if host is None:
                # если парсинг провалился — используем как есть
                address = upstream_proxy
            else:
                address = f"{scheme}://{host}"
                if port_parsed:
                    address += f":{port_parsed}"

            # Если есть credentials — вынести их в --upstream-auth
            if parsed.username or parsed.password:
                username = unquote(parsed.username or "")
                password = unquote(parsed.password or "")
                auth = f"{username}:{password}"
                command.extend(["--mode", f"upstream:{address}"])
                command.extend(["--upstream-auth", auth])
                print(f"🚀 Mitmdump запущен с upstream-прокси: {address} (credentials -> --upstream-auth)")
            else:
                command.extend(["--mode", f"upstream:{address}"])
                print(f"🚀 Mitmdump запущен в режиме upstream-прокси, направляя трафик на {address}")
    else:
        print("ℹ️ Upstream-прокси не задан — запускаю mitmdump без upstream.")

    # Показать команду для копирования
    print("🔧 Выполняется команда:\n  " + " ".join(command))

    # На Windows — открываем новую консоль, чтобы mitmdump был виден отдельным окном
    creation_flags = 0
    if sys.platform.startswith("win"):
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

    try:
        # Запускаем процесс. На Windows он откроет новое окно.
        proc = subprocess.Popen(command, creationflags=creation_flags)
        return proc
    except FileNotFoundError:
        print("❌ Ошибка: команда 'mitmdump' не найдена. Убедитесь, что mitmproxy установлен и mitmdump в PATH.")
        return None
    except Exception as e:
        print(f"❌ Не удалось запустить mitmdump: {e}")
        return None
