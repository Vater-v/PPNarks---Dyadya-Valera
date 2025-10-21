import subprocess
import hashlib
import platform
import uuid
import cpuinfo
import sys

def get_machine_fingerprint():
    """
    Собирает уникальный отпечаток системы на основе нескольких
    идентификаторов железа и возвращает его хэш SHA256.
    """
    try:
        # 1. MAC-адрес
        mac_address = ':'.join(hex(uuid.getnode())[2:].zfill(12)[i:i+2] for i in range(0, 12, 2))

        # 2. Информация о процессоре
        cpu_info = cpuinfo.get_cpu_info()
        cpu_serial = cpu_info.get('hardware_raw', 'unknown_cpu')

        # 3. UUID системы (очень надежно для Linux/Windows)
        system_uuid = 'unknown_uuid'
        if platform.system() == "Windows":
            # Для Windows используем команду wmic
            command = "wmic csproduct get uuid"
            system_uuid = subprocess.check_output(command, shell=True).decode().split('\n')[1].strip()
        elif platform.system() == "Linux":
            # Для Linux читаем файл
            try:
                with open("/sys/class/dmi/id/product_uuid", "r") as f:
                    system_uuid = f.readline().strip()
            except FileNotFoundError:
                # Фоллбэк, если файл недоступен
                system_uuid = subprocess.check_output(['cat', '/proc/sys/kernel/random/uuid']).decode().strip()


        # Соединяем все идентификаторы в одну строку
        # Вы можете добавить больше параметров, если нужно
        fingerprint_string = f"MAC:{mac_address}-CPU:{cpu_serial}-UUID:{system_uuid}"
        
        # Хэшируем строку, чтобы получить уникальный и короткий ключ
        hashed_fingerprint = hashlib.sha256(fingerprint_string.encode('utf-8')).hexdigest()
        
        return hashed_fingerprint

    except Exception as e:
        print(f"Ошибка при получении отпечатка системы: {e}")
        return None

ALLOWED_FINGERPRINTS = [
    "здарова"
]

def verify_machine():
    """
    Проверяет, входит ли отпечаток текущей машины в список разрешенных.
    Если нет - завершает программу.
    """
    
    current_fingerprint = get_machine_fingerprint()
    print(current_fingerprint)

    if not current_fingerprint:
        print("Критическая ошибка: не удалось проверить подлинность. Завершение работы.")
        sys.exit(1)

    # === ГЛАВНОЕ ИЗМЕНЕНИЕ ЗДЕСЬ ===
    # Проверяем, что текущий отпечаток есть в нашем списке разрешенных
    if current_fingerprint not in ALLOWED_FINGERPRINTS:
        print("Ошибка: Эта программа не может быть запущена на данном оборудовании.")
        import time
        time.sleep(5)
        sys.exit(1)
