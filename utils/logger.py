# -*- coding: utf-8 -*-
import os
import re
from datetime import datetime
from config import LOG_FILE, MAX_LOG_SIZE_MB
from utils.chat_names import chat_name_cache


def format_chat_ids_in_message(msg: str) -> str:
    """Заменяет ID каналов на их названия в сообщении"""
    # Паттерн для поиска ID каналов (отрицательные числа, обычно начинаются с -100)
    pattern = r'(-?\d{8,})'
    
    def replace_id(match):
        chat_id_str = match.group(1)
        try:
            chat_id = int(chat_id_str)
            # Используем кэш для получения названия
            if chat_id in chat_name_cache._cache:
                name = chat_name_cache._cache[chat_id]
                return f"{name} ({chat_id_str})"
            return chat_id_str
        except ValueError:
            return chat_id_str
    
    return re.sub(pattern, replace_id, msg)


def log(msg: str, format_chat_ids: bool = True) -> None:
    """Записывает сообщение в лог-файл с ротацией по размеру"""
    try:
        # Форматируем сообщение, заменяя ID на названия
        if format_chat_ids:
            msg = format_chat_ids_in_message(msg)
        
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE_MB * 1024 * 1024:
            os.remove(LOG_FILE)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except Exception:
        pass
