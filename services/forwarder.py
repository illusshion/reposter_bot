# -*- coding: utf-8 -*-
"""
Сервис пересылки сообщений с поддержкой альбомов
"""
import asyncio
from typing import Dict, List, Optional
from collections import defaultdict
from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.errors import ChatAdminRequiredError, ChatWriteForbiddenError, UserChannelsTooMuchError
from config import ALBUM_IDLE_SEC
from utils.logger import log


def is_permission_error(error: Exception) -> bool:
    """Проверяет, является ли ошибка связанной с правами доступа"""
    error_str = str(error).lower()
    permission_keywords = [
        "admin required",
        "write forbidden",
        "channels too much",
        "chat_admin_required",
        "chat_write_forbidden",
        "user_channels_too_much",
        "not enough rights",
        "insufficient rights",
        "no rights",
        "private and you lack permission",
        "lack permission",
        "permission to access",
        "banned from it",
        "access denied",
        "forbidden"
    ]
    return any(keyword in error_str for keyword in permission_keywords) or isinstance(
        error, (ChatAdminRequiredError, ChatWriteForbiddenError, UserChannelsTooMuchError)
    )


class ForwarderService:
    """Сервис для пересылки сообщений с обработкой альбомов"""

    def __init__(self, client: TelegramClient, user_client: Optional[TelegramClient] = None):
        self.client = client
        self.user_client = user_client
        self.album_buffer: Dict[str, List[Message]] = {}
        self.album_tasks: Dict[str, asyncio.Task] = {}
        self.failed_targets: Dict[int, bool] = {}  # Кэш целей, где нужен user bot

    async def flush_album(self, key: str, from_peer, targets: List[int]):
        """Пересылает накопленные сообщения альбома после задержки"""
        try:
            await asyncio.sleep(ALBUM_IDLE_SEC)
            msgs = sorted(self.album_buffer.get(key, []), key=lambda m: m.id)
            if not msgs:
                return
            message_ids = [m.id for m in msgs]
            for target in targets:
                use_user_client = False
                try:
                    # Проверяем, нужен ли user bot для этого target
                    use_user_client = self.failed_targets.get(target, False) and self.user_client
                    
                    client_to_use = self.user_client if use_user_client else self.client
                    
                    await client_to_use.forward_messages(
                        entity=target,
                        messages=message_ids,
                        from_peer=from_peer
                    )
                    log(f"FORWARDED ALBUM OK: from {from_peer} to {target}, items={len(message_ids)}, key={key}, client={'user' if use_user_client else 'bot'}")
                    # Если успешно через user bot, сбрасываем флаг
                    if use_user_client:
                        self.failed_targets[target] = False
                except Exception as e:
                    error_str = str(e).lower()
                    log(f"Error forwarding album to {target}: {e}, is_permission_error={is_permission_error(e)}")
                    # Если ошибка прав и есть user client, пробуем через него
                    if is_permission_error(e) and self.user_client and not use_user_client:
                        log(f"Trying fallback to user client for album target {target}")
                        try:
                            await self.user_client.forward_messages(
                                entity=target,
                                messages=message_ids,
                                from_peer=from_peer
                            )
                            log(f"FORWARDED ALBUM OK (fallback to user): from {from_peer} to {target}, items={len(message_ids)}, key={key}")
                            self.failed_targets[target] = True
                        except Exception as e2:
                            log(f"FORWARD ALBUM ERROR to {target} (both clients failed): {e2}")
                    else:
                        log(f"FORWARD ALBUM ERROR to {target}: {e}")
        except asyncio.CancelledError:
            return
        finally:
            self.album_buffer.pop(key, None)
            task = self.album_tasks.pop(key, None)
            if task and not task.cancelled():
                try:
                    task.cancel()
                except Exception:
                    pass

    async def forward_message(self, message: Message, targets: List[int]):
        """Пересылает сообщение в указанные чаты"""
        if not targets:
            return

        # Получаем ID чата-источника
        # Используем chat_id из сообщения, который уже нормализован Telethon
        chat_id = getattr(message, 'chat_id', None)
        if not chat_id and hasattr(message, 'peer_id'):
            peer = message.peer_id
            if hasattr(peer, 'channel_id'):
                # Для каналов используем нормализованный формат
                chat_id = -(1000000000000 + peer.channel_id)
            elif hasattr(peer, 'chat_id'):
                chat_id = -peer.chat_id
            elif hasattr(peer, 'user_id'):
                chat_id = peer.user_id
        
        if not chat_id:
            log(f"ERROR: Could not extract chat_id from message {message.id}")
            return
        
        # Обработка альбомов
        if message.grouped_id:
            key = f"{chat_id}_{message.grouped_id}"
            bucket = self.album_buffer.setdefault(key, [])
            bucket.append(message)
            
            # Отменяем предыдущую задачу для этого альбома
            task = self.album_tasks.get(key)
            if task:
                try:
                    task.cancel()
                except Exception:
                    pass
            
            # Создаем новую задачу с задержкой
            self.album_tasks[key] = asyncio.create_task(
                self.flush_album(key, message.peer_id, targets)
            )
            return

        # Обычное сообщение - пересылаем сразу
        for target in targets:
            use_user_client = False
            try:
                # Проверяем, нужен ли user bot для этого target
                use_user_client = self.failed_targets.get(target, False) and self.user_client
                
                client_to_use = self.user_client if use_user_client else self.client
                
                await client_to_use.forward_messages(
                    entity=target,
                    messages=message.id,
                    from_peer=message.peer_id
                )
                log(f"FORWARDED MSG: from {chat_id} to {target}, msg_id={message.id}, client={'user' if use_user_client else 'bot'}")
                # Если успешно через user bot, сбрасываем флаг
                if use_user_client:
                    self.failed_targets[target] = False
            except Exception as e:
                error_str = str(e).lower()
                log(f"Error forwarding to {target}: {e}, is_permission_error={is_permission_error(e)}")
                # Если ошибка прав и есть user client, пробуем через него
                if is_permission_error(e) and self.user_client and not use_user_client:
                    log(f"Trying fallback to user client for target {target}")
                    try:
                        await self.user_client.forward_messages(
                            entity=target,
                            messages=message.id,
                            from_peer=message.peer_id
                        )
                        log(f"FORWARDED MSG (fallback to user): from {chat_id} to {target}, msg_id={message.id}")
                        self.failed_targets[target] = True
                    except Exception as e2:
                        log(f"ERROR FORWARD MSG to {target} (both clients failed): {e2}")
                else:
                    log(f"ERROR FORWARD MSG to {target}: {e}")
