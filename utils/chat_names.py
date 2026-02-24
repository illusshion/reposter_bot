# -*- coding: utf-8 -*-
"""
Утилиты для получения и кэширования названий чатов/каналов
"""
from typing import Optional, Dict
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User
from telethon.utils import get_display_name


class ChatNameCache:
    """Кэш для названий чатов/каналов"""
    
    def __init__(self):
        self._cache: Dict[int, str] = {}
        self._client: Optional[TelegramClient] = None
        self._user_client: Optional[TelegramClient] = None
    
    def set_clients(self, client: TelegramClient, user_client: Optional[TelegramClient] = None):
        """Устанавливает клиенты для получения информации о чатах"""
        self._client = client
        self._user_client = user_client

    def set_user_client(self, user_client: Optional[TelegramClient]):
        """Обновляет только user client (для переподключения)"""
        self._user_client = user_client
    
    def get_chat_name(self, chat) -> str:
        """Получает название чата из объекта"""
        if isinstance(chat, (Channel, Chat)):
            return getattr(chat, "title", None) or get_display_name(chat) or f"Chat {chat.id}"
        elif isinstance(chat, User):
            return get_display_name(chat) or f"User {chat.id}"
        return str(chat)
    
    async def get_name(self, chat_id: int) -> str:
        """Получает название чата по ID с кэшированием"""
        # Проверяем кэш
        if chat_id in self._cache:
            return self._cache[chat_id]
        
        # Пробуем получить через bot client
        if self._client:
            try:
                entity = await self._client.get_entity(chat_id)
                name = self.get_chat_name(entity)
                self._cache[chat_id] = name
                return name
            except Exception:
                pass
        
        # Пробуем через user client
        if self._user_client:
            try:
                entity = await self._user_client.get_entity(chat_id)
                name = self.get_chat_name(entity)
                self._cache[chat_id] = name
                return name
            except Exception:
                pass
        
        # Если не получилось, возвращаем ID
        name = f"Chat {chat_id}"
        self._cache[chat_id] = name
        return name
    
    def format_chat_id(self, chat_id: int, show_id: bool = True) -> str:
        """Форматирует ID чата для отображения (синхронная версия, использует кэш)"""
        if chat_id in self._cache:
            name = self._cache[chat_id]
            if show_id:
                return f"{name} ({chat_id})"
            return name
        if show_id:
            return str(chat_id)
        return f"Chat {chat_id}"


# Глобальный экземпляр кэша
chat_name_cache = ChatNameCache()
