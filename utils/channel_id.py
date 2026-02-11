# -*- coding: utf-8 -*-
"""
Утилиты для работы с ID каналов Telegram
"""
from typing import Optional
from telethon import utils


def normalize_channel_id(chat_id: int) -> int:
    """
    Нормализует ID канала к формату с префиксом -100.
    Для каналов: -100 + channel_id
    Для чатов: -chat_id
    Для пользователей: user_id (без изменений)
    """
    if chat_id < 0:
        # Уже нормализован
        return chat_id
    
    # Если положительный ID, это может быть:
    # 1. ID пользователя (оставляем как есть)
    # 2. ID канала (добавляем -100)
    # 3. ID чата (делаем отрицательным)
    
    # Проверяем, является ли это ID канала (обычно > 1000000000)
    if chat_id > 1000000000:
        # Это скорее всего канал, добавляем префикс -100
        return -(1000000000000 + chat_id)
    elif chat_id > 0:
        # Это может быть чат, делаем отрицательным
        return -chat_id
    
    return chat_id


def get_channel_id_from_peer(peer) -> Optional[int]:
    """
    Извлекает нормализованный ID канала из peer объекта
    """
    if hasattr(peer, 'channel_id'):
        channel_id = peer.channel_id
        return -(1000000000000 + channel_id)
    elif hasattr(peer, 'chat_id'):
        return -peer.chat_id
    elif hasattr(peer, 'user_id'):
        return peer.user_id
    return None
