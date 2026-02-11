# -*- coding: utf-8 -*-
from typing import List, Optional
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


def render_sources_view(db) -> tuple[str, List]:
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


def render_targets_view(db) -> tuple[str, List]:
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


def chunk_buttons(buttons: list, per_row: int = 2) -> List[List]:
    """Разбивает кнопки на строки"""
    if per_row < 1:
        per_row = 1
    return [buttons[i:i+per_row] for i in range(0, len(buttons), per_row)]


def get_chat_name(chat: Channel | Chat) -> str:
    """Получает название чата"""
    return getattr(chat, "title", None) or get_display_name(chat) or str(chat.id)
