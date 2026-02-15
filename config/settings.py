# -*- coding: utf-8 -*-
import os
import sys
from typing import Set, Optional
from dotenv import load_dotenv, find_dotenv

# Загрузка .env
ENV_PATH = find_dotenv(filename=".env", usecwd=True)
load_dotenv(dotenv_path=ENV_PATH)


def env_str(name: str, default: Optional[str] = None, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        print(f"{name} не задан. Проверь .env или переменные окружения", file=sys.stderr)
        raise SystemExit(1)
    return "" if val is None else str(val)


def env_int(name: str, default: Optional[int] = None) -> Optional[int]:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except ValueError:
        print(f"{name} должен быть целым числом, получено: {val!r}", file=sys.stderr)
        raise SystemExit(1)


def env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except ValueError:
        print(f"{name} должен быть числом (float), получено: {val!r}", file=sys.stderr)
        raise SystemExit(1)


def parse_owner_ids() -> Set[int]:
    """
    Поддерживаем как новый формат OWNER_IDS="1,2,3", так и старый OWNER_ID="1".
    Пустое множество не допускается.
    """
    owners: Set[int] = set()
    raw_multi = os.getenv("OWNER_IDS", "")
    if raw_multi:
        try:
            owners |= {int(x) for x in raw_multi.replace(" ", "").split(",") if x}
        except ValueError:
            print(f"OWNER_IDS должен быть списком чисел через запятую, получено: {raw_multi!r}", file=sys.stderr)
            raise SystemExit(1)
    raw_single = os.getenv("OWNER_ID", "")
    if raw_single:
        try:
            owners.add(int(raw_single))
        except ValueError:
            print(f"OWNER_ID должен быть целым числом, получено: {raw_single!r}", file=sys.stderr)
            raise SystemExit(1)
    if not owners:
        print("Не задан ни OWNER_IDS, ни OWNER_ID. Укажи хотя бы одного владельца.", file=sys.stderr)
        raise SystemExit(1)
    return owners


# === КОНФИГУРАЦИЯ ===

# Режим работы: 'bot', 'user' или 'auto' (автоматическое переключение на user bot при ошибках прав)
MODE = env_str("MODE", "bot").lower()

# Для bot mode и auto mode нужен BOT_TOKEN
BOT_TOKEN = env_str("BOT_TOKEN", required=(MODE in ("bot", "auto")))

# Telethon требует API_ID и API_HASH всегда
# Получи их на https://my.telegram.org/apps
API_ID = env_int("API_ID")
if API_ID is None:
    print("API_ID не задан. Проверь .env или переменные окружения", file=sys.stderr)
    raise SystemExit(1)
API_HASH = env_str("API_HASH", required=True)
SESSION_NAME = env_str("SESSION_NAME", "reposter_session")

# Для автоматического переключения на user bot (опционально)
# Если не указаны, будет использоваться тот же API_ID/API_HASH
USER_API_ID = env_int("USER_API_ID")
USER_API_HASH = env_str("USER_API_HASH")
USER_SESSION_NAME = env_str("USER_SESSION_NAME", "reposter_user_session")

# Общие настройки
OWNER_IDS = parse_owner_ids()
DB_PATH = env_str("DB_PATH", "forwarder.db")
LOG_FILE = env_str("LOG_FILE", "bot.log")
MAX_LOG_SIZE_MB = env_int("MAX_LOG_SIZE_MB", 10) or 10
ALBUM_IDLE_SEC = env_float("ALBUM_IDLE_SEC", 4.5)
REPOST_STEP = env_int("REPOST_STEP", 1) or 1
if REPOST_STEP < 1:
    REPOST_STEP = 1

# Подсказка для пользователей
COPY_HINT = (
    "ℹ️ Если это приватный канал, пришли ссылку-приглашение с него, "
    "чтобы я смог показывать кликабельный якорь в списках."
)
