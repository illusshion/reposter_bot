# -*- coding: utf-8 -*-
import re

INVITE_RE = re.compile(
    r'^(?:https://t\.me/(?:\+|joinchat/)[A-Za-z0-9_-]+|tg://join\?invite=[A-Za-z0-9_-]+)$'
)


def is_invite_link(s: str) -> bool:
    """Проверяет, является ли строка валидной invite-ссылкой"""
    return bool(INVITE_RE.match((s or "").strip()))
