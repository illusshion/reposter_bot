# -*- coding: utf-8 -*-
"""
Операции с базой данных
"""
import sqlite3
from typing import List, Tuple, Optional
from .models import init_db
from utils.channel_id import normalize_channel_id


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        init_db(db_path)

    def source_exists(self, cid: int) -> bool:
        """Проверяет, существует ли источник с данным ID"""
        normalized_id = normalize_channel_id(cid)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT 1 FROM sources WHERE id = ?", (normalized_id,)).fetchone()
            return row is not None

    def target_exists(self, cid: int) -> bool:
        """Проверяет, существует ли склад с данным ID"""
        normalized_id = normalize_channel_id(cid)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT 1 FROM targets WHERE id = ?", (normalized_id,)).fetchone()
            return row is not None

    def add_source(self, cid: int, name: str, username: Optional[str] = None, invite_link: Optional[str] = None) -> bool:
        """
        Добавляет источник. Возвращает True если добавлен новый, False если уже существовал.
        """
        # Нормализуем ID канала
        normalized_id = normalize_channel_id(cid)
        with sqlite3.connect(self.db_path) as conn:
            # Проверяем, существует ли уже
            exists = conn.execute("SELECT 1 FROM sources WHERE id = ?", (normalized_id,)).fetchone() is not None
            if exists:
                # Обновляем существующий
                conn.execute(
                    "UPDATE sources SET name = ?, username = ?, invite_link = ? WHERE id = ?",
                    (name, username, invite_link, normalized_id)
                )
                conn.commit()
                return False
            else:
                # Добавляем новый
                conn.execute(
                    "INSERT INTO sources (id, name, username, invite_link) VALUES (?, ?, ?, ?)",
                    (normalized_id, name, username, invite_link)
                )
                conn.commit()
                return True

    def add_target(self, cid: int, name: str, username: Optional[str] = None, invite_link: Optional[str] = None) -> bool:
        """
        Добавляет склад. Возвращает True если добавлен новый, False если уже существовал.
        """
        # Нормализуем ID канала
        normalized_id = normalize_channel_id(cid)
        with sqlite3.connect(self.db_path) as conn:
            # Проверяем, существует ли уже
            exists = conn.execute("SELECT 1 FROM targets WHERE id = ?", (normalized_id,)).fetchone() is not None
            if exists:
                # Обновляем существующий
                conn.execute(
                    "UPDATE targets SET name = ?, username = ?, invite_link = ? WHERE id = ?",
                    (name, username, invite_link, normalized_id)
                )
                conn.commit()
                return False
            else:
                # Добавляем новый
                conn.execute(
                    "INSERT INTO targets (id, name, username, invite_link) VALUES (?, ?, ?, ?)",
                    (normalized_id, name, username, invite_link)
                )
                conn.commit()
                return True

    def update_source_invite(self, cid: int, invite_link: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE sources SET invite_link = ? WHERE id = ?", (invite_link, cid))
            conn.commit()

    def update_target_invite(self, cid: int, invite_link: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE targets SET invite_link = ? WHERE id = ?", (invite_link, cid))
            conn.commit()

    def list_sources(self) -> List[Tuple[int, str, Optional[str], Optional[str]]]:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT id, name, username, invite_link FROM sources ORDER BY name COLLATE NOCASE"
            ).fetchall()

    def list_targets(self) -> List[Tuple[int, str, Optional[str], Optional[str]]]:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT id, name, username, invite_link FROM targets ORDER BY name COLLATE NOCASE"
            ).fetchall()

    def add_binding(self, source_id: int, target_id: int) -> None:
        # Нормализуем ID перед сохранением
        normalized_source_id = normalize_channel_id(source_id)
        normalized_target_id = normalize_channel_id(target_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO bindings (source_id, target_id) VALUES (?, ?)",
                (normalized_source_id, normalized_target_id)
            )
            conn.commit()

    def remove_binding(self, source_id: int, target_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM bindings WHERE source_id=? AND target_id=?",
                (source_id, target_id)
            )
            conn.commit()

    def get_bindings(self) -> List[Tuple[int, int]]:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT source_id, target_id FROM bindings").fetchall()

    def get_targets_for_source(self, source_id: int) -> List[int]:
        # Нормализуем ID источника для поиска
        normalized_source_id = normalize_channel_id(source_id)
        with sqlite3.connect(self.db_path) as conn:
            # Пробуем найти по нормализованному ID
            rows = conn.execute(
                "SELECT target_id FROM bindings WHERE source_id=?",
                (normalized_source_id,)
            ).fetchall()
            if rows:
                return [r[0] for r in rows]
            
            # Если не нашли, пробуем найти по исходному ID (для обратной совместимости)
            rows = conn.execute(
                "SELECT target_id FROM bindings WHERE source_id=?",
                (source_id,)
            ).fetchall()
            return [r[0] for r in rows]

    def remove_source(self, source_id: int) -> Tuple[int, int, str]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            name_row = cur.execute("SELECT name FROM sources WHERE id=?", (source_id,)).fetchone()
            name = name_row[0] if name_row else str(source_id)
            binds = cur.execute("SELECT COUNT(*) FROM bindings WHERE source_id=?", (source_id,)).fetchone()[0]
            cur.execute("DELETE FROM bindings WHERE source_id=?", (source_id,))
            cur.execute("DELETE FROM sources WHERE id=?", (source_id,))
            deleted_src = cur.rowcount
            conn.commit()
            return binds, deleted_src, name

    def remove_target(self, target_id: int) -> Tuple[int, int, str]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            name_row = cur.execute("SELECT name FROM targets WHERE id=?", (target_id,)).fetchone()
            name = name_row[0] if name_row else str(target_id)
            binds = cur.execute("SELECT COUNT(*) FROM bindings WHERE target_id=?", (target_id,)).fetchone()[0]
            cur.execute("DELETE FROM bindings WHERE target_id=?", (target_id,))
            cur.execute("DELETE FROM targets WHERE id=?", (target_id,))
            deleted_tgt = cur.rowcount
            conn.commit()
            return binds, deleted_tgt, name
