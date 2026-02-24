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

USER_CLIENT_RECONNECT_DELAY = 30  # секунд перед переподключением


async def notify_admins(client: TelegramClient, text: str):
    """Отправляет сообщение всем админам"""
    for owner_id in OWNER_IDS:
        try:
            await client.send_message(owner_id, text)
        except Exception as e:
            log(f"Не удалось отправить уведомление админу {owner_id}: {e}")


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
    register_user_handler = setup_messages(client, db, forwarder, user_client)
    
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
        if user_client and MODE in ("bot", "auto"):
            # User client с автопереподключением
            user_api_id = USER_API_ID or API_ID
            user_api_hash = USER_API_HASH or API_HASH
            current_user_client = user_client
            user_task = None
            user_should_stop = False

            async def run_user_client_with_reconnect():
                nonlocal current_user_client, user_task
                while not user_should_stop:
                    try:
                        await current_user_client.run_until_disconnected()
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        log(f"User client упал: {e}")
                        try:
                            await notify_admins(
                                client,
                                f"⚠️ User bot упал: {str(e)[:200]}\n\nПереподключаю через {USER_CLIENT_RECONNECT_DELAY} сек..."
                            )
                        except Exception:
                            pass
                        try:
                            await current_user_client.disconnect()
                        except Exception:
                            pass
                        if user_should_stop:
                            break
                        await asyncio.sleep(USER_CLIENT_RECONNECT_DELAY)
                        try:
                            new_client = TelegramClient(USER_SESSION_NAME, user_api_id, user_api_hash)
                            await new_client.start()
                            current_user_client = new_client
                            forwarder.set_user_client(new_client)
                            chat_name_cache.set_user_client(new_client)
                            register_user_handler(new_client)
                            log("User client переподключен")
                            await notify_admins(client, "✓ User bot переподключен.")
                        except Exception as e2:
                            log(f"Не удалось переподключить user client: {e2}")
                            await notify_admins(
                                client,
                                f"❌ Не удалось переподключить user bot: {e2}"
                            )

            user_task = asyncio.create_task(run_user_client_with_reconnect())
            try:
                await client.run_until_disconnected()
            finally:
                user_should_stop = True
                if user_task:
                    user_task.cancel()
                    try:
                        await user_task
                    except asyncio.CancelledError:
                        pass
                try:
                    await current_user_client.disconnect()
                except Exception:
                    pass
        else:
            await client.run_until_disconnected()
    finally:
        if user_client:
            try:
                await user_client.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log("Бот остановлен")
    except Exception as e:
        log(f"Критическая ошибка: {e}")
        raise
