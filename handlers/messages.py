# -*- coding: utf-8 -*-
"""
Обработчики сообщений из каналов
"""
from telethon import events
from telethon.tl.types import Channel, Chat
from typing import Optional
from database import Database
from services.forwarder import ForwarderService
from utils.logger import log
from utils.channel_id import normalize_channel_id
from utils.chat_names import chat_name_cache


def get_chat_id_from_event(event) -> Optional[int]:
    """Извлекает ID чата из события"""
    # Пробуем разные способы получения ID
    if hasattr(event, 'chat_id') and event.chat_id:
        return event.chat_id
    
    if hasattr(event, 'peer_id'):
        peer = event.peer_id
        if hasattr(peer, 'channel_id'):
            return peer.channel_id
        if hasattr(peer, 'chat_id'):
            return peer.chat_id
        if hasattr(peer, 'user_id'):
            return peer.user_id
    
    if hasattr(event.message, 'peer_id'):
        peer = event.message.peer_id
        if hasattr(peer, 'channel_id'):
            return peer.channel_id
        if hasattr(peer, 'chat_id'):
            return peer.chat_id
    
    return None


def setup_messages(client, db: Database, forwarder: ForwarderService, user_client=None):
    """Настраивает обработчики сообщений из каналов"""
    
    async def handle_channel_message(event, client_name: str):
        """Обработчик сообщений из каналов"""
        try:
            # Проверяем, что это пост из канала (не из ЛС)
            if event.is_private:
                return
            
            # Получаем ID чата
            chat_id = get_chat_id_from_event(event)
            if not chat_id:
                log(f"ОШИБКА: Не удалось извлечь chat_id из события, клиент={client_name}")
                return
            
            # Нормализуем ID канала
            normalized_chat_id = normalize_channel_id(chat_id)
            
            # Получаем целевые чаты для этого источника
            targets = db.get_targets_for_source(normalized_chat_id)
            if not targets:
                return
            
            # Пересылаем сообщение
            await forwarder.forward_message(event.message, targets)
        except Exception as e:
            # Получаем название канала для лога ошибки
            try:
                chat_id = get_chat_id_from_event(event) if 'event' in locals() else None
                if chat_id:
                    chat_name = await chat_name_cache.get_name(chat_id)
                    log(f"Error in handle_channel_message for {chat_name}, client={client_name}: {e}")
                else:
                    log(f"Error in handle_channel_message, client={client_name}: {e}")
            except:
                log(f"Error in handle_channel_message, client={client_name}: {e}")
            import traceback
            log(f"Traceback: {traceback.format_exc()}")

    # Настраиваем обработчик на bot клиент
    @client.on(events.NewMessage(chats=None))
    async def on_channel_post_bot(event):
        await handle_channel_message(event, "bot")
    
    # Настраиваем обработчик на user клиент (если доступен)
    if user_client:
        @user_client.on(events.NewMessage(chats=None))
        async def on_channel_post_user(event):
            await handle_channel_message(event, "user")
    
    log("Обработчики сообщений успешно зарегистрированы")
