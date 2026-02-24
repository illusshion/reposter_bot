# -*- coding: utf-8 -*-
from typing import List, Optional, Tuple, Union
from telethon.tl.types import Channel, Chat
from telethon.utils import get_display_name
from telethon import Button


def make_channel_link(name: str, chat_id: int, username: Optional[str] = None, invite_link: Optional[str] = None) -> str:
    """Создает HTML-ссылку на канал"""
    if username:
        return f'<a href="https://t.me/{username}">{name}</a>'
    if invite_link:
        return f'<a href="{invite_link}">{name}</a>'
    return name


def render_sources_view(db) -> Tuple[str, List]:
    """Формирует текст и кнопки для списка источников"""
    items = db.list_sources()
    if not items:
        text = "Источников нет."
        buttons = [[Button.inline("Закрыть", b"close_msg")]]
        return text, buttons
    lines = ["<b>Список источников:</b>"]
    buttons = []
    for sid, name, username, invite_link in items:
        lines.append(f"• {make_channel_link(name, sid, username, invite_link)}")
        buttons.append([Button.inline(f"🗑 {name}", f"del_src_{sid}".encode())])
    buttons.append([Button.inline("Закрыть", b"close_msg")])
    return "\n".join(lines), buttons


def render_targets_view(db) -> Tuple[str, List]:
    """Формирует текст и кнопки для списка складов"""
    items = db.list_targets()
    if not items:
        text = "Складов нет."
        buttons = [[Button.inline("Закрыть", b"close_msg")]]
        return text, buttons
    lines = ["<b>Список складов:</b>"]
    buttons = []
    for tid, name, username, invite_link in items:
        lines.append(f"• {make_channel_link(name, tid, username, invite_link)}")
        buttons.append([Button.inline(f"🗑 {name}", f"del_tgt_{tid}".encode())])
    buttons.append([Button.inline("Закрыть", b"close_msg")])
    return "\n".join(lines), buttons


def render_settings_main(db) -> Tuple[str, List]:
    """Формирует текст и кнопки для главного экрана настроек шага репостов"""
    default_step = db.get_repost_step()
    default_desc = "все посты" if default_step == 1 else f"каждый {default_step}-й пост"
    lines = [f"<b>Шаг репостов</b>\n", f"По умолчанию: <b>{default_desc}</b>\n"]
    btns = [[Button.inline("По умолч. 1", b"set_step_1"), Button.inline("2", b"set_step_2"),
            Button.inline("3", b"set_step_3"), Button.inline("4", b"set_step_4")]]
    targets = db.list_targets()
    if targets:
        lines.append("Выбери склад:")
        for tid, tname, tuser, tinv in targets:
            s = db.get_repost_step(tid)
            sd = "все" if s == 1 else f"каждый {s}-й"
            lines.append(f"• {make_channel_link(tname, tid, tuser, tinv)} — {sd}")
            btns.append([Button.inline(f"⚙️ {tname[:20]}", f"tgt_step_{tid}".encode())])
    else:
        lines.append("(нет складов)")
    btns.append([Button.inline("Закрыть", b"close_msg")])
    return "\n".join(lines), btns


def chunk_buttons(buttons: list, per_row: int = 2) -> List[List]:
    """Разбивает кнопки на строки"""
    if per_row < 1:
        per_row = 1
    return [buttons[i:i+per_row] for i in range(0, len(buttons), per_row)]


def get_chat_name(chat: Union[Channel, Chat]) -> str:
    """Получает название чата"""
    return getattr(chat, "title", None) or get_display_name(chat) or str(chat.id)
