# -*- coding: utf-8 -*-
"""
Обработчики callback кнопок
"""
from telethon import events, Button
from config import OWNER_IDS
from database import Database
from utils.formatters import render_sources_view, render_targets_view, chunk_buttons, make_channel_link
from utils.channel_id import normalize_channel_id


def setup_callbacks(client, db: Database, user_states: dict):
    """Настраивает обработчики callback кнопок"""

    @client.on(events.CallbackQuery())
    async def callback_handler(event):
        if event.sender_id not in OWNER_IDS:
            await event.answer("Доступ запрещен", alert=True)
            return

        data = event.data.decode() if isinstance(event.data, bytes) else event.data

        # Выбор склада для связки (первый шаг)
        if data.startswith("bind_tgt_"):
            tid = int(data.split("_")[-1])
            st = user_states.get(event.sender_id)
            if not st or st.get("step") != "bind_choose_tgts":
                await event.answer("Ошибка состояния. Начни заново.", alert=True)
                return
            selected = st.get("selected_tgts", set())
            if tid in selected:
                selected.remove(tid)
            else:
                selected.add(tid)
            st["selected_tgts"] = selected
            targets = db.list_targets()
            buttons = [
                Button.inline(
                    ("✓" if _tid in selected else "▫") + f" {name}",
                    f"bind_tgt_{_tid}".encode()
                )
                for _tid, name, _, _ in targets
            ]
            rows = chunk_buttons(buttons, per_row=2)
            rows.append([
                Button.inline("✓ Далее", b"bind_next_to_sources"),
                Button.inline("✕ Отмена", b"bind_cancel"),
            ])
            await event.edit(f"Выбрано складов: {len(selected)}", buttons=rows)
            await event.answer()

        # Переход к выбору источников
        elif data == "bind_next_to_sources":
            st = user_states.get(event.sender_id)
            if not st or st.get("step") != "bind_choose_tgts":
                await event.answer("Ошибка состояния.", alert=True)
                return
            selected_tgts = st.get("selected_tgts", set())
            if not selected_tgts:
                await event.answer("Нужно выбрать хотя бы один склад.", alert=True)
                return
            # Переходим к выбору источников
            st["step"] = "bind_choose_srcs"
            sources = db.list_sources()
            buttons = [
                Button.inline(f"▫ {sname}", f"bind_src_{sid}".encode())
                for sid, sname, _, _ in sources
            ]
            rows = chunk_buttons(buttons, per_row=2)
            rows.append([
                Button.inline("✓ Сохранить", b"bind_confirm"),
                Button.inline("✕ Отмена", b"bind_cancel"),
            ])
            await event.edit("Выбери источники для связки (можно несколько):", buttons=rows)
            await event.answer()

        # Выбор источника для связки (второй шаг)
        elif data.startswith("bind_src_"):
            src_id = int(data.split("_")[-1])
            st = user_states.get(event.sender_id)
            if not st or st.get("step") != "bind_choose_srcs":
                await event.answer("Ошибка состояния. Начни заново.", alert=True)
                return
            selected_srcs = st.get("selected_srcs", set())
            if src_id in selected_srcs:
                selected_srcs.remove(src_id)
            else:
                selected_srcs.add(src_id)
            st["selected_srcs"] = selected_srcs
            sources = db.list_sources()
            buttons = [
                Button.inline(
                    ("✓" if _sid in selected_srcs else "▫") + f" {name}",
                    f"bind_src_{_sid}".encode()
                )
                for _sid, name, _, _ in sources
            ]
            rows = chunk_buttons(buttons, per_row=2)
            rows.append([
                Button.inline("✓ Сохранить", b"bind_confirm"),
                Button.inline("✕ Отмена", b"bind_cancel"),
            ])
            await event.edit(f"Выбрано источников: {len(selected_srcs)}", buttons=rows)
            await event.answer()

        # Подтверждение связки - создаем все комбинации
        elif data == "bind_confirm":
            st = user_states.get(event.sender_id)
            if not st or st.get("step") != "bind_choose_srcs":
                await event.answer("Ошибка состояния.", alert=True)
                return
            selected_tgts = st.get("selected_tgts", set())
            selected_srcs = st.get("selected_srcs", set())
            if not selected_tgts or not selected_srcs:
                await event.answer("Нужно выбрать хотя бы один склад и один источник.", alert=True)
                return
            
            already, added = 0, 0
            added_bindings = []  # Сохраняем созданные связки для отображения
            import sqlite3
            with sqlite3.connect(db.db_path) as conn:
                cur = conn.cursor()
                # Создаем все комбинации: каждый источник → каждый склад
                for src_id in selected_srcs:
                    normalized_src_id = normalize_channel_id(src_id)
                    for tgt_id in selected_tgts:
                        normalized_tgt_id = normalize_channel_id(tgt_id)
                        # Проверяем, существует ли связка
                        if cur.execute("SELECT 1 FROM bindings WHERE source_id=? AND target_id=?", (normalized_src_id, normalized_tgt_id)).fetchone():
                            already += 1
                        else:
                            db.add_binding(normalized_src_id, normalized_tgt_id)
                            added += 1
                            added_bindings.append((normalized_src_id, normalized_tgt_id))
            
            user_states.pop(event.sender_id, None)
            msg = []
            if added:
                msg.append(f"<b>Связок добавлено:</b> {added}")
            if already:
                msg.append(f"<b>Уже были:</b> {already}")
            
            # Если есть созданные связки, показываем их список
            if added_bindings:
                src_rows = {sid: (name, username, invite_link) for sid, name, username, invite_link in db.list_sources()}
                tgt_rows = {tid: (name, username, invite_link) for tid, name, username, invite_link in db.list_targets()}
                # Группируем по складам (targets), как в /list
                groups = {}
                for src_id, tgt_id in added_bindings:
                    if tgt_id not in groups:
                        groups[tgt_id] = []
                    groups[tgt_id].append(src_id)
                
                lines = []
                for tgt_id, src_ids in sorted(groups.items(), key=lambda x: tgt_rows.get(x[0], (str(x[0]), None, None))[0]):
                    t_name, t_user, t_inv = tgt_rows.get(tgt_id, (str(tgt_id), None, None))
                    tgt_link = make_channel_link(t_name, tgt_id, t_user, t_inv)
                    src_link_strs = []
                    for sid in sorted(src_ids, key=lambda x: src_rows.get(x, (str(x), None, None))[0]):
                        s_name, s_user, s_inv = src_rows.get(sid, (str(sid), None, None))
                        src_link_strs.append(make_channel_link(s_name, sid, s_user, s_inv))
                    lines.append(f"{tgt_link} ← {' + '.join(src_link_strs)}")
                
                if lines:
                    msg.append("")  # Пустая строка для разделения
                    msg.extend(lines)
            
            await event.edit("\n".join(msg) if msg else "Нет новых связок.", parse_mode='html', link_preview=False)
            await event.answer()

        # Отмена операции
        elif data == "bind_cancel":
            user_states.pop(event.sender_id, None)
            await event.edit("Операция отменена.")
            await event.answer()

        # Удаление связки
        elif data.startswith("remove_") and data.count("_") == 2:
            _, s, t = data.split("_")
            db.remove_binding(int(s), int(t))
            await event.edit("Связка удалена.")
            await event.answer()

        # Удаление источника
        elif data.startswith("del_src_"):
            sid = int(data.split("_")[-1])
            binds, deleted, name = db.remove_source(sid)
            if deleted:
                await event.answer(f"Источник удалён. Связок удалено: {binds}.")
                text, buttons = render_sources_view(db)
                await event.edit(text, buttons=buttons, parse_mode='html', link_preview=False)
                await event.respond(f"Удалён источник «{name}». Удалено связок: {binds}.")
            else:
                await event.answer("Такого источника уже нет.", alert=True)

        # Удаление склада
        elif data.startswith("del_tgt_"):
            tid = int(data.split("_")[-1])
            binds, deleted, name = db.remove_target(tid)
            if deleted:
                await event.answer(f"Склад удалён. Связок удалено: {binds}.")
                text, buttons = render_targets_view(db)
                await event.edit(text, buttons=buttons, parse_mode='html', link_preview=False)
                await event.respond(f"Удалён склад «{name}». Удалено связок: {binds}.")
            else:
                await event.answer("Такого склада уже нет.", alert=True)

        # Настройка шага репоста
        elif data.startswith("set_step_"):
            try:
                step = int(data.split("_")[-1])
                if 1 <= step <= 10:
                    db.set_repost_step(step)
                    if step == 1:
                        msg = "Готово. Теперь репощу всё подряд."
                    else:
                        msg = f"Готово. Буду репостить каждый {step}-й пост."
                    await event.answer(msg, alert=False)
                    await event.edit(msg, parse_mode='html')
                else:
                    await event.answer("Шаг должен быть от 1 до 10.", alert=True)
            except (ValueError, IndexError):
                await event.answer("Ошибка.", alert=True)

        # Закрытие сообщения
        elif data == "close_msg":
            try:
                await event.delete()
            except Exception:
                pass
            await event.answer()
