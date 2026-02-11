# -*- coding: utf-8 -*-
import os
from datetime import datetime
from config import LOG_FILE, MAX_LOG_SIZE_MB


def log(msg: str) -> None:
    """Записывает сообщение в лог-файл с ротацией по размеру"""
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE_MB * 1024 * 1024:
            os.remove(LOG_FILE)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except Exception:
        pass
