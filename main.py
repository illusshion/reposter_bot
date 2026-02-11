# -*- coding: utf-8 -*-
"""
Главный файл запуска бота
"""
import asyncio
from telethon import TelegramClient
from telethon.tl.types import BotCommand, BotCommandScopeDefault
from telethon.tl.functions.bots import SetBotCommandsRequest
from config import (
    MODE, BOT_TOKEN, API_ID, API_HASH, SESSION_NAME,
    USER_API_ID, USER_API_HASH, USER_SESSION_NAME,
    DB_PATH, OWNER_IDS
)
from database import Database
from services.forwarder import ForwarderService
from handlers import setup_commands, setup_callbacks, setup_messages
from utils.logger import log


async def main():
    """Основная функция запуска бота"""
    log("Bot starting")
    
    # Инициализация базы данных
    db = Database(DB_PATH)
    
    # Инициализация основного клиента Telethon
    if MODE == "bot":
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        log(f"Bot client started")
    elif MODE == "user":
        # User mode
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        await client.start()
        log(f"User client started")
    else:
        # Auto mode - запускаем оба клиента
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        log(f"Bot client started")
    
    # Инициализация user клиента для fallback (если нужен)
    user_client = None
    if MODE == "auto" or (MODE == "bot" and (USER_API_ID or USER_API_HASH)):
        try:
            user_api_id = USER_API_ID or API_ID
            user_api_hash = USER_API_HASH or API_HASH
            user_client = TelegramClient(USER_SESSION_NAME, user_api_id, user_api_hash)
            await user_client.start()
            log(f"User client started for fallback")
        except Exception as e:
            log(f"Warning: Failed to start user client: {e}. Will continue without fallback.")
            user_client = None
    
    # Инициализация сервиса пересылки
    forwarder = ForwarderService(client, user_client)
    
    # Состояния пользователей (для интерактивных команд)
    user_states = {}
    
    # Настройка обработчиков
    log("Setting up command handlers...")
    setup_commands(client, db, user_states, user_client)
    log("Setting up callback handlers...")
    setup_callbacks(client, db, user_states)
    log("Setting up message handlers...")
    setup_messages(client, db, forwarder, user_client)
    
    # Устанавливаем команды меню для бота (только для bot режима)
    if MODE in ("bot", "auto"):
        try:
            commands = [
                BotCommand(command="help", description="Справка по командам"),
                BotCommand(command="add_source", description="Добавить канал-источник"),
                BotCommand(command="add_target", description="Добавить канал-склад"),
                BotCommand(command="sources", description="Список источников"),
                BotCommand(command="targets", description="Список складов"),
                BotCommand(command="bind", description="Создать связку"),
                BotCommand(command="list", description="Список связок"),
                BotCommand(command="remove", description="Удалить связку"),
            ]
            await client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code="ru",
                commands=commands
            ))
            log("Bot commands menu set successfully")
        except Exception as e:
            log(f"Warning: Failed to set bot commands menu: {e}")
            import traceback
            log(f"Traceback: {traceback.format_exc()}")
    
    # Логируем список источников для отладки
    sources = db.list_sources()
    log(f"Registered sources: {[(sid, name) for sid, name, _, _ in sources]}")
    
    log("Handlers registered, bot is ready")
    
    # Запуск бота
    try:
        if user_client:
            # Запускаем user клиент в фоне
            user_task = asyncio.create_task(user_client.run_until_disconnected())
            # Запускаем bot клиент (основной)
            try:
                await client.run_until_disconnected()
            finally:
                # Отменяем user клиент при остановке bot клиента
                user_task.cancel()
                try:
                    await user_task
                except asyncio.CancelledError:
                    pass
        else:
            await client.run_until_disconnected()
    finally:
        if user_client:
            await user_client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log("Bot stopped")
    except Exception as e:
        log(f"Fatal error: {e}")
        raise
