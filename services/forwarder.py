# -*- coding: utf-8 -*-
"""
Сервис пересылки сообщений с поддержкой альбомов
"""
import asyncio
from typing import Dict, List, Optional, Callable
from collections import defaultdict
from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.errors import ChatAdminRequiredError, ChatWriteForbiddenError, UserChannelsTooMuchError
from config import ALBUM_IDLE_SEC
from utils.logger import log
from utils.chat_names import chat_name_cache


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

    def __init__(self, client: TelegramClient, user_client: Optional[TelegramClient] = None,
                 get_repost_step: Optional[Callable[[], int]] = None):
        self.client = client
        self.user_client = user_client
        self.get_repost_step = get_repost_step or (lambda: 1)
        self.album_buffer: Dict[str, List[Message]] = {}
        self.album_tasks: Dict[str, asyncio.Task] = {}
        self.failed_targets: Dict[int, bool] = {}  # Кэш целей, где нужен user bot
        self.processed_messages: set = set()  # Кэш обработанных сообщений для дедупликации
        self.processing_albums: set = set()  # Альбомы, которые сейчас обрабатываются
        self.source_counters: Dict[int, int] = {}  # Счётчик постов по источникам для шага репоста
        self.skipped_albums: set = set()  # Альбомы, которые пропущены по шагу

    async def flush_album(self, key: str, from_peer, targets: List[int]):
        """Пересылает накопленные сообщения альбома после задержки"""
        try:
            await asyncio.sleep(ALBUM_IDLE_SEC)
            
            # Проверяем, не обрабатывается ли уже этот альбом
            if key in self.processing_albums:
                return  # Альбом уже обрабатывается другой задачей
            
            msgs = sorted(self.album_buffer.get(key, []), key=lambda m: m.id)
            if not msgs:
                return
            message_ids = [m.id for m in msgs]
            
            # Помечаем альбом как обрабатываемый (защита от одновременного выполнения)
            self.processing_albums.add(key)
            
            # Получаем ID источника из ключа или из первого сообщения
            source_id = None
            if '_' in key:
                source_id = int(key.split('_')[0])
            elif msgs:
                source_id = getattr(msgs[0], 'chat_id', None)
            
            # Получаем название источника для логов
            from_name = await chat_name_cache.get_name(source_id) if source_id else "Неизвестно"
            
            # Проверяем дедупликацию: если альбом уже переслан другим клиентом, пропускаем
            album_key = None
            if source_id and msgs:
                album_key = (source_id, msgs[0].grouped_id)
                if album_key in self.processed_messages:
                    return  # Альбом уже переслан, пропускаем
            
            success_count = 0
            for target in targets:
                # Получаем название цели для логов
                target_name = await chat_name_cache.get_name(target)
                
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
                    log(f"✓ Альбом переслан из {from_name} в {target_name} ({len(message_ids)} элементов)")
                    success_count += 1
                    # Если успешно через user bot, сбрасываем флаг
                    if use_user_client:
                        self.failed_targets[target] = False
                except Exception as e:
                    # Если ошибка прав и есть user client, пробуем через него
                    if is_permission_error(e) and self.user_client and not use_user_client:
                        try:
                            await self.user_client.forward_messages(
                                entity=target,
                                messages=message_ids,
                                from_peer=from_peer
                            )
                            log(f"✓ Альбом переслан из {from_name} в {target_name} ({len(message_ids)} элементов, резервный вариант)")
                            success_count += 1
                            self.failed_targets[target] = True
                        except Exception as e2:
                            log(f"ОШИБКА пересылки альбома из {from_name} в {target_name}: {e2}")
                    else:
                        log(f"ОШИБКА пересылки альбома из {from_name} в {target_name}: {e}")
            
            # Помечаем альбом как обработанный только если хотя бы одна пересылка успешна
            if success_count > 0 and album_key:
                self.processed_messages.add(album_key)
        except asyncio.CancelledError:
            return
        finally:
            self.album_buffer.pop(key, None)
            self.processing_albums.discard(key)
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
            log(f"ОШИБКА: Не удалось извлечь chat_id из сообщения {message.id}")
            return

        step = self.get_repost_step()
        
        # Обработка альбомов
        if message.grouped_id:
            key = f"{chat_id}_{message.grouped_id}"
            
            # Проверяем дедупликацию: если альбом уже полностью переслан, пропускаем
            album_key = (chat_id, message.grouped_id)
            if album_key in self.processed_messages:
                return  # Альбом уже переслан, пропускаем

            # Пропущенные по шагу альбомы
            if album_key in self.skipped_albums:
                return

            # Проверяем, не обрабатывается ли уже этот альбом
            if key in self.processing_albums:
                # Альбом обрабатывается, просто добавляем сообщение в буфер
                bucket = self.album_buffer.setdefault(key, [])
                bucket.append(message)
                return
            
            # Первое сообщение альбома — проверяем шаг репоста
            if key not in self.album_buffer:
                self.source_counters[chat_id] = self.source_counters.get(chat_id, 0) + 1
                counter = self.source_counters[chat_id]
                if step > 1 and counter % step != 0:
                    self.skipped_albums.add(album_key)
                    if len(self.skipped_albums) > 5000:
                        self.skipped_albums = set(list(self.skipped_albums)[2500:])
                    return

            # Добавляем сообщение в буфер альбома
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
        
        # Дедупликация для обычных сообщений: проверяем, не обрабатывали ли мы уже это сообщение
        message_key = (chat_id, message.id)
        if message_key in self.processed_messages:
            return  # Сообщение уже обработано, пропускаем

        # Проверка шага репоста для обычных сообщений
        self.source_counters[chat_id] = self.source_counters.get(chat_id, 0) + 1
        counter = self.source_counters[chat_id]
        if step > 1 and counter % step != 0:
            self.processed_messages.add(message_key)  # Помечаем, чтобы не считать дважды
            return  # Пропускаем по шагу
        
        # Добавляем в кэш обработанных сообщений
        self.processed_messages.add(message_key)
        
        # Ограничиваем размер кэша (храним последние 10000 записей)
        if len(self.processed_messages) > 10000:
            # Удаляем старые записи (просто очищаем половину)
            self.processed_messages = set(list(self.processed_messages)[5000:])

        # Получаем название источника для логов
        from_name = await chat_name_cache.get_name(chat_id)
        
        # Обычное сообщение - пересылаем сразу
        for target in targets:
            # Получаем название цели для логов
            target_name = await chat_name_cache.get_name(target)
            
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
                log(f"✓ Сообщение переслано из {from_name} в {target_name}")
                # Если успешно через user bot, сбрасываем флаг
                if use_user_client:
                    self.failed_targets[target] = False
            except Exception as e:
                # Если ошибка прав и есть user client, пробуем через него
                if is_permission_error(e) and self.user_client and not use_user_client:
                    try:
                        await self.user_client.forward_messages(
                            entity=target,
                            messages=message.id,
                            from_peer=message.peer_id
                        )
                        log(f"✓ Сообщение переслано из {from_name} в {target_name} (резервный вариант)")
                        self.failed_targets[target] = True
                    except Exception as e2:
                        log(f"ОШИБКА пересылки из {from_name} в {target_name}: {e2}")
                else:
                    log(f"ОШИБКА пересылки из {from_name} в {target_name}: {e}")
