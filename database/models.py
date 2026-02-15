# -*- coding: utf-8 -*-
"""
Модели базы данных и миграции
"""
import sqlite3
from typing import List, Tuple, Optional, Set


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _normalize_id_for_migration(chat_id: int) -> int:
    """Нормализует ID для миграции"""
    if chat_id < 0:
        return chat_id
    if chat_id > 1000000000:
        return -(1000000000000 + chat_id)
    elif chat_id > 0:
        return -chat_id
    return chat_id


def _migrate_channel_ids(conn: sqlite3.Connection) -> None:
    """Мигрирует старые ID каналов к нормализованному формату"""
    # Мигрируем sources
    sources = conn.execute("SELECT id FROM sources WHERE id > 0").fetchall()
    for (old_id,) in sources:
        new_id = _normalize_id_for_migration(old_id)
        if new_id != old_id:
            # Обновляем ID источника
            conn.execute("UPDATE sources SET id = ? WHERE id = ?", (new_id, old_id))
            # Обновляем связки
            conn.execute("UPDATE bindings SET source_id = ? WHERE source_id = ?", (new_id, old_id))
    
    # Мигрируем targets
    targets = conn.execute("SELECT id FROM targets WHERE id > 0").fetchall()
    for (old_id,) in targets:
        new_id = _normalize_id_for_migration(old_id)
        if new_id != old_id:
            # Обновляем ID склада
            conn.execute("UPDATE targets SET id = ? WHERE id = ?", (new_id, old_id))
            # Обновляем связки
            conn.execute("UPDATE bindings SET target_id = ? WHERE target_id = ?", (new_id, old_id))
    
    conn.commit()


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Добавляет недостающие колонки в существующие таблицы"""
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
    
    # Мигрируем ID каналов
    _migrate_channel_ids(conn)


def init_db(db_path: str) -> None:
    """Инициализирует базу данных и создает таблицы"""
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                username TEXT,
                invite_link TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                username TEXT,
                invite_link TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bindings (
                source_id INTEGER,
                target_id INTEGER,
                UNIQUE(source_id, target_id),
                FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE,
                FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE CASCADE
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
    # Применяем миграции для существующих БД
    with sqlite3.connect(db_path) as conn:
        _ensure_columns(conn)
