# -*- coding: utf-8 -*-
"""
Скрипт для входа user client через QR-код.
Запусти один раз, отсканируй QR в Telegram на телефоне — сессия сохранится.
После этого main.py будет использовать эту сессию без запроса кода.
"""
import asyncio
import sys

# Загружаем конфиг до импорта telethon
from config import API_ID, API_HASH, USER_SESSION_NAME, USER_API_ID, USER_API_HASH

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

from telethon import TelegramClient


async def main():
    api_id = USER_API_ID or API_ID
    api_hash = (USER_API_HASH or "").strip() or API_HASH
    if not api_hash:
        print("USER_API_HASH или API_HASH не задан в .env")
        sys.exit(1)

    client = TelegramClient(USER_SESSION_NAME, api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Уже авторизован как: {me.first_name} (@{me.username or '—'})")
        await client.disconnect()
        return

    print("Вход через QR-код (код по SMS/приложению часто не приходит)...")
    print()

    try:
        qr = await client.qr_login()
        print(f"Открой Telegram на телефоне → Настройки → Устройства → Подключить рабочий стол")
        print(f"Или отсканируй QR-код ниже:\n")
        print(f"Ссылка: {qr.url}\n")

        if HAS_QR:
            qr_img = qrcode.QRCode(border=1)
            qr_img.add_data(qr.url)
            qr_img.make(fit=True)
            qr_img.print_ascii(invert=True)
        else:
            print("Установи qrcode для отображения: pip install qrcode")

        print("\nЖду сканирования (60 сек)...")
        await qr.wait(timeout=60)
        print("✓ Вход выполнен! Сессия сохранена.")
        me = await client.get_me()
        print(f"  {me.first_name} (@{me.username or '—'})")

    except asyncio.TimeoutError:
        print("Время вышло. Запусти скрипт снова.")
    except Exception as e:
        if "AuthTokenExpiredError" in str(type(e).__name__):
            print("QR истёк. Запусти скрипт снова.")
        else:
            print(f"Ошибка: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
