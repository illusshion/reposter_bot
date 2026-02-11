# -*- coding: utf-8 -*-
import os
import sys
import re
import asyncio
import sqlite3
from datetime import datetime
from collections import defaultdict
from typing import List, Tuple, Optional, Set

# === ЗАГРУЗКА .env ДО ЛЮБЫХ os.getenv ===
try:
    from dotenv import load_dotenv, find_dotenv  # python-dotenv==1.0.1
except Exception:
    print("Не установлен пакет python-dotenv. Установи: pip install python-dotenv==1.0.1", file=sys.stderr)
    raise

ENV_PATH = find_dotenv(filename=".env", usecwd=True)
load_dotenv(dotenv_path=ENV_PATH)

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart, or_f, BaseFilter
from aiogram.enums import ParseMode, ChatType
from aiogram.utils.markdown import hlink
from aiogram.client.default import DefaultBotProperties

# ---------- УТИЛИТЫ ОКРУЖЕНИЯ ----------
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

# ---------- КОНФИГ ----------
BOT_TOKEN = env_str("BOT_TOKEN", required=True)
OWNER_IDS = parse_owner_ids()
DB_PATH = env_str("DB_PATH", "forwarder.db")
LOG_FILE = env_str("LOG_FILE", "bot.log")
MAX_LOG_SIZE_MB = env_int("MAX_LOG_SIZE_MB", 10) or 10
DISPATCHER_DELAY = env_float("DISPATCHER_DELAY", 1.5)
ALBUM_IDLE_SEC = env_float("ALBUM_IDLE_SEC", 4.5)

# ---------- ЛОГИ ----------
def log(msg: str) -> None:
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE_MB * 1024 * 1024:
            os.remove(LOG_FILE)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except Exception:
        pass

# ---------- БД + миграции ----------
def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())

def _ensure_columns() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        # sources
        if not _table_has_column(conn, "sources", "username"):
            conn.execute("ALTER TABLE sources ADD COLUMN username TEXT")
        if not _table_has_column(conn, "sources", "invite_link"):
            conn.execute("ALTER TABLE sources ADD COLUMN invite_link TEXT")
        # targets
        if not _table_has_column(conn, "targets", "username"):
            conn.execute("ALTER TABLE targets ADD COLUMN username TEXT")
        if not _table_has_column(conn, "targets", "invite_link"):
            conn.execute("ALTER TABLE targets ADD COLUMN invite_link TEXT")
        conn.commit()

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY, name TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS targets (id INTEGER PRIMARY KEY, name TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS bindings (source_id INTEGER, target_id INTEGER, UNIQUE(source_id, target_id))")
        conn.commit()
    _ensure_columns()

def add_source_db(cid: int, name: str, username: Optional[str], invite_link: Optional[str]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO sources (id, name) VALUES (?, ?)", (cid, name))
        conn.execute("UPDATE sources SET name = ?, username = ?, invite_link = ? WHERE id = ?", (name, username, invite_link, cid))
        conn.commit()

def add_target_db(cid: int, name: str, username: Optional[str], invite_link: Optional[str]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO targets (id, name) VALUES (?, ?)", (cid, name))
        conn.execute("UPDATE targets SET name = ?, username = ?, invite_link = ? WHERE id = ?", (name, username, invite_link, cid))
        conn.commit()

def update_source_invite(cid: int, invite_link: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE sources SET invite_link = ? WHERE id = ?", (invite_link, cid))
        conn.commit()

def update_target_invite(cid: int, invite_link: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE targets SET invite_link = ? WHERE id = ?", (invite_link, cid))
        conn.commit()

def list_sources_db() -> List[Tuple[int, str, Optional[str], Optional[str]]]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT id, name, username, invite_link FROM sources ORDER BY name COLLATE NOCASE").fetchall()

def list_targets_db() -> List[Tuple[int, str, Optional[str], Optional[str]]]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT id, name, username, invite_link FROM targets ORDER BY name COLLATE NOCASE").fetchall()

def add_binding_db(source_id: int, target_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO bindings (source_id, target_id) VALUES (?, ?)", (source_id, target_id))
        conn.commit()

def remove_binding_db(source_id: int, target_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM bindings WHERE source_id=? AND target_id=?", (source_id, target_id))
        conn.commit()

def get_bindings_db() -> List[Tuple[int, int]]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT source_id, target_id FROM bindings").fetchall()

def get_targets_for_source_db(source_id: int) -> List[int]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT target_id FROM bindings WHERE source_id=?", (source_id,)).fetchall()
        return [r[0] for r in rows]

def remove_source_db(source_id: int) -> tuple[int, int, str]:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        name_row = cur.execute("SELECT name FROM sources WHERE id=?", (source_id,)).fetchone()
        name = name_row[0] if name_row else str(source_id)
        binds = cur.execute("SELECT COUNT(*) FROM bindings WHERE source_id=?", (source_id,)).fetchone()[0]
        cur.execute("DELETE FROM bindings WHERE source_id=?", (source_id,))
        cur.execute("DELETE FROM sources WHERE id=?", (source_id,))
        deleted_src = cur.rowcount
        conn.commit()
        return binds, deleted_src, name

def remove_target_db(target_id: int) -> tuple[int, int, str]:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        name_row = cur.execute("SELECT name FROM targets WHERE id=?", (target_id,)).fetchone()
        name = name_row[0] if name_row else str(target_id)
        binds = cur.execute("SELECT COUNT(*) FROM bindings WHERE target_id=?", (target_id,)).fetchone()[0]
        cur.execute("DELETE FROM bindings WHERE target_id=?", (target_id,))
        cur.execute("DELETE FROM targets WHERE id=?", (target_id,))
        deleted_tgt = cur.rowcount
        conn.commit()
        return binds, deleted_tgt, name

init_db()

# ---------- ВАЛИДАЦИЯ ИНВАЙТ-ССЫЛОК ----------
INVITE_RE = re.compile(
    r'^(?:https://t\.me/(?:\+|joinchat/)[A-Za-z0-9_-]+|tg://join\?invite=[A-Za-z0-9_-]+)$'
)
def is_invite_link(s: str) -> bool:
    return bool(INVITE_RE.match((s or "").strip()))

# ---------- УТИЛИТЫ ----------
def make_channel_link(name: str, chat_id: int, username: Optional[str] = None, invite_link: Optional[str] = None) -> str:
    if username:
        return hlink(name, f"https://t.me/{username}")
    if invite_link:
        return hlink(name, invite_link)
    return name

def render_sources_view() -> tuple[str, InlineKeyboardMarkup]:
    items = list_sources_db()
    if not items:
        text = "Источников нет."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Закрыть", callback_data="close_msg")]])
        return text, kb
    lines = ["<b>Список источников:</b>"]
    buttons = []
    for sid, name, username, invite_link in items:
        lines.append(f"• {make_channel_link(name, sid, username, invite_link)}")
        buttons.append([InlineKeyboardButton(text=f"🗑 {name}", callback_data=f"del_src_{sid}")])
    buttons.append([InlineKeyboardButton(text="Закрыть", callback_data="close_msg")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)

def render_targets_view() -> tuple[str, InlineKeyboardMarkup]:
    items = list_targets_db()
    if not items:
        text = "Складов нет."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Закрыть", callback_data="close_msg")]])
        return text, kb
    lines = ["<b>Список складов:</b>"]
    buttons = []
    for tid, name, username, invite_link in items:
        lines.append(f"• {make_channel_link(name, tid, username, invite_link)}")
        buttons.append([InlineKeyboardButton(text=f"🗑 {name}", callback_data=f"del_tgt_{tid}")])
    buttons.append([InlineKeyboardButton(text="Закрыть", callback_data="close_msg")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)

def chunk_buttons(buttons: list, per_row: int = 2) -> list[list]:
    if per_row < 1:
        per_row = 1
    return [buttons[i:i+per_row] for i in range(0, len(buttons), per_row)]

# ---------- ФИЛЬТРЫ ВЛАДЕЛЬЦЕВ ----------
class OwnerFilter(BaseFilter):
    def __init__(self, owners: Set[int]) -> None:
        self.owners = owners

    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in self.owners)

class OwnerCallbackFilter(BaseFilter):
    def __init__(self, owners: Set[int]) -> None:
        self.owners = owners

    async def __call__(self, cq: CallbackQuery) -> bool:
        return bool(cq.from_user and cq.from_user.id in self.owners)

is_owner_msg = OwnerFilter(OWNER_IDS)
is_owner_cq = OwnerCallbackFilter(OWNER_IDS)

# ---------- СОСТОЯНИЯ ----------
user_states: dict[int, dict] = {}
def reset_state(uid: int) -> None:
    user_states.pop(uid, None)

# ---------- AIOGRAM ИНИЦ ----------
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ---------- КОМАНДЫ (с кратким напоминанием) ----------
COPY_HINT = (
    "ℹ️ Если это приватный канал, пришли ссылку-приглашение с него, "
    "чтобы я смог показывать кликабельный якорь в списках."
)

@router.message(is_owner_msg, CommandStart())
async def cmd_start(m: Message):
    await m.reply(
        "Бот-репостер готов.\n\nКоманды:\n"
        "/add_source — добавить канал-источник\n"
        "/add_target — добавить канал-склад\n"
        "/sources — список источников (с удалением)\n"
        "/targets — список складов (с удалением)\n"
        "/bind — создать связку\n"
        "/list — список связок\n"
        "/remove (/unlink) — удалить связку\n"
        "/help — помощь\n\n" + COPY_HINT
    )

@router.message(is_owner_msg, Command("help"))
async def cmd_help(m: Message):
    await m.reply(
        "/add_source — добавить канал-источник (перешли пост, @username или id)\n"
        "/add_target — добавить канал-склад (перешли пост, @username или id)\n"
        "/sources — показать все источники и удалить нужный\n"
        "/targets — показать все склады и удалить нужный\n"
        "/bind — выбрать источник и один/несколько складов\n"
        "/list — показать все связки\n"
        "/remove (/unlink) — удалить конкретную связку\n\n" + COPY_HINT
    )

@router.message(is_owner_msg, Command("add_source"))
async def cmd_add_source(m: Message):
    user_states[m.from_user.id] = {"step": "add_source"}
    await m.reply("Перешли пост из источника или отправь @username / id.\n" + COPY_HINT)

@router.message(is_owner_msg, Command("add_target"))
async def cmd_add_target(m: Message):
    user_states[m.from_user.id] = {"step": "add_target"}
    await m.reply("Перешли пост из склада или отправь @username / id.\n" + COPY_HINT)

@router.message(is_owner_msg, Command("sources"))
async def cmd_sources(m: Message):
    text, kb = render_sources_view()
    await m.reply(text, reply_markup=kb, disable_web_page_preview=True)

@router.message(is_owner_msg, Command("targets"))
async def cmd_targets(m: Message):
    text, kb = render_targets_view()
    await m.reply(text, reply_markup=kb, disable_web_page_preview=True)

@router.message(is_owner_msg, Command("bind"))
async def cmd_bind(m: Message):
    sources = list_sources_db()
    targets = list_targets_db()
    if not sources or not targets:
        await m.reply("Нет источников или складов. Сначала добавь их.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=
        [[InlineKeyboardButton(text=name, callback_data=f"bind_src_{cid}")]
         for cid, name, _, _ in sources] +
        [[InlineKeyboardButton(text="❌ Отмена", callback_data="bind_cancel")]]
    )
    user_states[m.from_user.id] = {"step": "bind_choose_src"}
    await m.reply("Выбери источник для связки:", reply_markup=kb)

@router.message(is_owner_msg, Command("list"))
async def cmd_list(m: Message):
    binds = get_bindings_db()
    if not binds:
        await m.reply("Связок нет.")
        return
    src_rows = {sid: (name, username, invite_link) for sid, name, username, invite_link in list_sources_db()}
    tgt_rows = {tid: (name, username, invite_link) for tid, name, username, invite_link in list_targets_db()}
    groups: dict[int, list[int]] = defaultdict(list)
    for src_id, tgt_id in binds:
        groups[src_id].append(tgt_id)
    lines: List[str] = []
    for src_id, tgt_ids in groups.items():
        s_name, s_user, s_inv = src_rows.get(src_id, (str(src_id), None, None))
        src_link = make_channel_link(s_name, src_id, s_user, s_inv)
        tgt_link_strs: List[str] = []
        for tid in tgt_ids:
            t_name, t_user, t_inv = tgt_rows.get(tid, (str(tid), None, None))
            tgt_link_strs.append(make_channel_link(t_name, tid, t_user, t_inv))
        lines.append(f"{src_link} → {' + '.join(tgt_link_strs)}")
    await m.reply("\n".join(lines), disable_web_page_preview=True)

@router.message(is_owner_msg, or_f(Command("remove"), Command("unlink")))
async def cmd_remove(m: Message):
    binds = get_bindings_db()
    if not binds:
        await m.reply("Связок нет.")
        return
    src_rows = {sid: name for sid, name, _, _ in list_sources_db()}
    tgt_rows = {tid: name for tid, name, _, _ in list_targets_db()}
    kb_rows: List[List[InlineKeyboardButton]] = []
    for sid, tid in binds:
        sname = src_rows.get(sid, str(sid))
        tname = tgt_rows.get(tid, str(tid))
        kb_rows.append([InlineKeyboardButton(text=f"{sname} → {tname}", callback_data=f"remove_{sid}_{tid}")])
    kb_rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bind_cancel")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await m.reply("Выбери связку для удаления:", reply_markup=kb)

# ---------- ЛС: ДОБАВЛЕНИЕ И ОЖИДАНИЕ ИНВАЙТА ----------
@router.message(is_owner_msg, F.chat.type == ChatType.PRIVATE)
async def private_steps(m: Message, bot: Bot):
    state = user_states.get(m.from_user.id)
    if not state:
        return
    step = state.get("step")

    # 1) Добавление источника/склада — как было (форвард / @username / id)
    if step in {"add_source", "add_target"}:
        chat_id: Optional[int] = None
        chat_title: Optional[str] = None
        chat_username: Optional[str] = None

        try:
            if m.forward_origin and getattr(m.forward_origin, "chat", None):
                chat = m.forward_origin.chat
            else:
                text = (m.text or "").strip()
                if not text:
                    await m.reply("Пришли @username или numeric id.")
                    reset_state(m.from_user.id)
                    return
                if text.startswith("@"):
                    chat = await bot.get_chat(text)
                else:
                    chat = await bot.get_chat(int(text))

            chat_id = chat.id
            chat_title = getattr(chat, "title", None) or str(chat_id)
            chat_username = getattr(chat, "username", None)

        except Exception as e:
            await m.reply(f"Ошибка: {e}")
            reset_state(m.from_user.id)
            return

        if not chat_id:
            await m.reply("Не удалось определить id канала.")
            reset_state(m.from_user.id)
            return

        if step == "add_source":
            add_source_db(chat_id, chat_title, chat_username, None)
            await m.reply(
                f"Источник добавлен: {make_channel_link(chat_title, chat_id, chat_username, None)}",
                disable_web_page_preview=True
            )
            if not chat_username:
                user_states[m.from_user.id] = {"step": "wait_invite", "chat_id": chat_id, "kind": "source"}
                await m.reply(
                    "Это приватный канал. Пришли ссылку-приглашение с него, чтобы я мог показать кликабельный якорь в списках.\n"
                    "Поддерживаемые форматы: <code>https://t.me/+XXXX</code>, <code>https://t.me/joinchat/XXXX</code>, <code>tg://join?invite=XXXX</code>"
                )
            else:
                reset_state(m.from_user.id)
        else:
            add_target_db(chat_id, chat_title, chat_username, None)
            await m.reply(
                f"Склад добавлен: {make_channel_link(chat_title, chat_id, chat_username, None)}",
                disable_web_page_preview=True
            )
            if not chat_username:
                user_states[m.from_user.id] = {"step": "wait_invite", "chat_id": chat_id, "kind": "target"}
                await m.reply(
                    "Это приватный канал. Пришли ссылку-приглашение с него, чтобы я мог показать кликабельный якорь в списках.\n"
                    "Поддерживаемые форматы: <code>https://t.me/+XXXX</code>, <code>https://t.me/joinchat/XXXX</code>, <code>tg://join?invite=XXXX</code>"
                )
            else:
                reset_state(m.from_user.id)
        return

    # 2) Ожидание инвайта для только что добавленного приватного канала
    if step == "wait_invite":
        invite = (m.text or "").strip()
        if not is_invite_link(invite):
            await m.reply("Это не похоже на валидную ссылку-приглашение. Пришли корректную invite-ссылку.")
            return
        cid = state.get("chat_id")
        kind = state.get("kind")
        if not cid or kind not in {"source", "target"}:
            reset_state(m.from_user.id)
            await m.reply("Состояние сброшено. Повтори добавление.")
            return
        if kind == "source":
            update_source_invite(cid, invite)
            await m.reply("Инвайт сохранён для источника. Теперь якорь будет кликабельным.", disable_web_page_preview=True)
        else:
            update_target_invite(cid, invite)
            await m.reply("Инвайт сохранён для склада. Теперь якорь будет кликабельным.", disable_web_page_preview=True)
        reset_state(m.from_user.id)
        return

# ---------- CALLBACKS ----------
@router.callback_query(is_owner_cq)
async def cbq(cq: CallbackQuery, bot: Bot):
    data = cq.data or ""
    uid = cq.from_user.id

    if data.startswith("bind_src_"):
        src_id = int(data.split("_")[-1])
        targets = list_targets_db()
        if not targets:
            await cq.answer("Складов нет. Добавь хотя бы один через /add_target.")
            return
        user_states[uid] = {"step": "bind_choose_tgts", "src_id": src_id, "selected_tgts": set()}
        btns = [InlineKeyboardButton(text=f"▫️ {tname}", callback_data=f"bind_tgt_{tid}") for tid, tname, _, _ in targets]
        rows = chunk_buttons(btns, per_row=2)
        rows.append([
            InlineKeyboardButton(text="✅ Сохранить", callback_data="bind_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="bind_cancel"),
        ])
        await cq.message.edit_text("Выбери склады для связки (можно несколько):", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await cq.answer(); return

    if data.startswith("bind_tgt_"):
        tid = int(data.split("_")[-1])
        st = user_states.get(uid)
        if not st or st.get("step") != "bind_choose_tgts":
            await cq.answer("Ошибка состояния. Начни заново."); return
        selected: set[int] = st.get("selected_tgts", set())
        if tid in selected: selected.remove(tid)
        else: selected.add(tid)
        st["selected_tgts"] = selected
        targets = list_targets_db()
        btns = [
            InlineKeyboardButton(
                text=("✅" if _tid in selected else "▫️") + f" {name}",
                callback_data=f"bind_tgt_{_tid}"
            )
            for _tid, name, _, _ in targets
        ]
        rows = chunk_buttons(btns, per_row=2)
        rows.append([
            InlineKeyboardButton(text="✅ Сохранить", callback_data="bind_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="bind_cancel"),
        ])
        await cq.message.edit_text(f"Выбрано складов: {len(selected)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await cq.answer(); return

    if data == "bind_confirm":
        st = user_states.get(uid)
        if not st or st.get("step") != "bind_choose_tgts":
            await cq.answer("Ошибка состояния."); return
        src_id = st["src_id"]
        selected: set[int] = st.get("selected_tgts", set())
        if not selected:
            await cq.answer("Нужно выбрать хотя бы один склад."); return
        already, added = 0, 0
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            for tgt in selected:
                if cur.execute("SELECT 1 FROM bindings WHERE source_id=? AND target_id=?", (src_id, tgt)).fetchone():
                    already += 1
                else:
                    cur.execute("INSERT INTO bindings (source_id, target_id) VALUES (?, ?)", (src_id, tgt))
                    added += 1
            conn.commit()
        reset_state(uid)
        msg = []
        if added: msg.append(f"Связок добавлено: {added} ✅")
        if already: msg.append(f"Уже были: {already}")
        await cq.message.edit_text("\n".join(msg) if msg else "Нет новых связок.")
        await cq.answer(); return

    if data == "bind_cancel":
        reset_state(uid)
        await cq.message.edit_text("Операция отменена.")
        await cq.answer(); return

    if data.startswith("remove_") and data.count("_") == 2:
        _, s, t = data.split("_")
        remove_binding_db(int(s), int(t))
        await cq.message.edit_text("Связка удалена.")
        await cq.answer(); return

    if data.startswith("del_src_"):
        sid = int(data.split("_")[-1])
        binds, deleted, name = remove_source_db(sid)
        if deleted:
            await cq.answer(f"Источник удалён. Связок удалено: {binds}.")
            text, kb = render_sources_view()
            await cq.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
            await cq.message.answer(f"Удалён источник «{name}». Удалено связок: {binds}.")
        else:
            await cq.answer("Такого источника уже нет.")
        return

    if data.startswith("del_tgt_"):
        tid = int(data.split("_")[-1])
        binds, deleted, name = remove_target_db(tid)
        if deleted:
            await cq.answer(f"Склад удалён. Связок удалено: {binds}.")
            text, kb = render_targets_view()
            await cq.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
            await cq.message.answer(f"Удалён склад «{name}». Удалено связок: {binds}.")
        else:
            await cq.answer("Такого склада уже нет.")
        return

    if data == "close_msg":
        try:
            await cq.message.delete()
        except Exception:
            pass
        await cq.answer(); return

# ---------- ФОРВАРД КАНАЛОВ ----------
album_buffer: dict[str, list[Message]] = {}
album_tasks: dict[str, asyncio.Task] = {}

async def flush_album(key: str, from_chat_id: int, targets: list[int], bot: Bot):
    try:
        await asyncio.sleep(ALBUM_IDLE_SEC)
        msgs = sorted(album_buffer.get(key, []), key=lambda m: m.message_id)
        if not msgs:
            return
        message_ids = [m.message_id for m in msgs]
        for target in targets:
            try:
                await bot.forward_messages(chat_id=target, from_chat_id=from_chat_id, message_ids=message_ids)
                log(f"FORWARDED ALBUM OK: from {from_chat_id} to {target}, items={len(message_ids)}, key={key}")
            except Exception as e:
                log(f"FORWARD ALBUM ERROR to {target}: {e}")
    except asyncio.CancelledError:
        return
    finally:
        album_buffer.pop(key, None)
        task = album_tasks.pop(key, None)
        if task and not task.cancelled():
            try:
                task.cancel()
            except Exception:
                pass

@router.channel_post()
async def on_channel_post(m: Message, bot: Bot):
    targets = get_targets_for_source_db(m.chat.id)
    if not targets:
        return
    if m.media_group_id:
        key = f"{m.chat.id}_{m.media_group_id}"
        bucket = album_buffer.setdefault(key, [])
        bucket.append(m)
        t = album_tasks.get(key)
        if t:
            try:
                t.cancel()
            except Exception:
                pass
        album_tasks[key] = asyncio.create_task(flush_album(key, m.chat.id, targets, bot))
        return
    for target in targets:
        try:
            await bot.forward_message(chat_id=target, from_chat_id=m.chat.id, message_id=m.message_id)
            log(f"FORWARDED MSG: from {m.chat.id} to {target}, msg_id={m.message_id}")
        except Exception as e:
            log(f"ERROR FORWARD MSG: {e}")

# ---------- MAIN ----------
async def main():
    log("Bot starting")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log("Bot stopped")
