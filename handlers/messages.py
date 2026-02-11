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
            # Логируем все входящие сообщения для отладки
            log(f"Event received: is_private={event.is_private}, client={client_name}, msg_id={event.message.id if event.message else 'N/A'}")
            
            # Проверяем, что это пост из канала (не из ЛС)
            if event.is_private:
                log(f"Skipping private message, client={client_name}")
                return
            
            # Получаем ID чата
            chat_id = get_chat_id_from_event(event)
            if not chat_id:
                log(f"Could not extract chat_id from event, client={client_name}, event={type(event)}, peer_id={getattr(event, 'peer_id', None)}")
                return
            
            # Нормализуем ID канала
            normalized_chat_id = normalize_channel_id(chat_id)
            log(f"Processing message from chat_id={chat_id} (normalized={normalized_chat_id}), client={client_name}")
            
            # Получаем целевые чаты для этого источника
            targets = db.get_targets_for_source(normalized_chat_id)
            if not targets:
                log(f"No targets found for source {chat_id}, client={client_name}")
                return
            
            log(f"Received message from channel {chat_id}, forwarding to {len(targets)} targets, client={client_name}")
            
            # Пересылаем сообщение
            await forwarder.forward_message(event.message, targets)
        except Exception as e:
            log(f"Error in handle_channel_message, client={client_name}: {e}")
            import traceback
            log(f"Traceback: {traceback.format_exc()}")

    # Настраиваем обработчик на bot клиент
    @client.on(events.NewMessage(chats=None))
    async def on_channel_post_bot(event):
        log(f"Bot client received NewMessage event")
        await handle_channel_message(event, "bot")
    
    # Настраиваем обработчик на user клиент (если доступен)
    if user_client:
        @user_client.on(events.NewMessage(chats=None))
        async def on_channel_post_user(event):
            log(f"User client received NewMessage event")
            await handle_channel_message(event, "user")
        log("User client message handler registered")
    else:
        log("User client not available, only bot client will receive messages")
    
    log("Message handlers registered successfully")
