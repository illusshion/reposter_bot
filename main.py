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
from utils.chat_names import chat_name_cache


async def main():
    """Основная функция запуска бота"""
    log("Бот запускается")
    
    # Инициализация базы данных
    db = Database(DB_PATH)
    
    # Инициализация основного клиента Telethon
    if MODE == "bot":
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        log(f"Клиент бота запущен")
    elif MODE == "user":
        # User mode
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        await client.start()
        log(f"Клиент пользователя запущен")
    else:
        # Auto mode - запускаем оба клиента
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        log(f"Клиент бота запущен")
    
    # Инициализация user клиента для fallback (если нужен)
    user_client = None
    if MODE == "auto" or (MODE == "bot" and (USER_API_ID or USER_API_HASH)):
        try:
            user_api_id = USER_API_ID or API_ID
            user_api_hash = USER_API_HASH or API_HASH
            user_client = TelegramClient(USER_SESSION_NAME, user_api_id, user_api_hash)
            await user_client.start()
            log(f"Клиент пользователя запущен для резервного варианта")
        except Exception as e:
            log(f"Предупреждение: Не удалось запустить клиент пользователя: {e}. Продолжаем без резервного варианта.")
            user_client = None
    
    # Инициализация кэша названий каналов
    chat_name_cache.set_clients(client, user_client)
    
    # Инициализация сервиса пересылки
    forwarder = ForwarderService(client, user_client, get_repost_step=db.get_repost_step)
    
    # Состояния пользователей (для интерактивных команд)
    user_states = {}
    
    # Настройка обработчиков
    log("Настройка обработчиков команд...")
    setup_commands(client, db, user_states, user_client)
    log("Настройка обработчиков callback...")
    setup_callbacks(client, db, user_states)
    log("Настройка обработчиков сообщений...")
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
                BotCommand(command="settings", description="Настройки (шаг репоста)"),
            ]
            await client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code="ru",
                commands=commands
            ))
            log("Меню команд бота успешно установлено")
        except Exception as e:
            log(f"Предупреждение: Не удалось установить меню команд бота: {e}")
            import traceback
            log(f"Трассировка: {traceback.format_exc()}")
    
    # Логируем список источников для отладки
    sources = db.list_sources()
    log(f"Зарегистрированные источники: {[(sid, name) for sid, name, _, _ in sources]}")
    
    log("Обработчики зарегистрированы, бот готов")
    
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
        log("Бот остановлен")
    except Exception as e:
        log(f"Критическая ошибка: {e}")
        raise
