# -*- coding: utf-8 -*-
"""
Обработчики команд бота
"""
from telethon import events, Button
from telethon.tl.types import Channel, Chat
from config import OWNER_IDS, COPY_HINT
from database import Database
from utils.formatters import get_chat_name, make_channel_link, render_sources_view, render_targets_view, chunk_buttons
from utils.validators import is_invite_link
from utils.channel_id import normalize_channel_id


def setup_commands(client, db: Database, user_states: dict, user_client=None):
    """Настраивает обработчики команд"""

    @client.on(events.NewMessage(pattern=r'^/start', func=lambda e: e.is_private))
    async def cmd_start(event):
        if event.sender_id not in OWNER_IDS:
            return
        await event.respond(
            "Бот-репостер готов.\n\nКоманды:\n"
            "/add_source — добавить канал-источник\n"
            "/add_target — добавить канал-склад\n"
            "/sources — список источников (с удалением)\n"
            "/targets — список складов (с удалением)\n"
            "/bind — создать связку\n"
            "/list — список связок\n"
            "/remove — удалить связку\n"
            "/help — помощь"
        )

    @client.on(events.NewMessage(pattern=r'^/help', func=lambda e: e.is_private))
    async def cmd_help(event):
        if event.sender_id not in OWNER_IDS:
            return
        await event.respond(
            "Команды:\n"
            "/add_source — добавить канал-источник\n"
            "/add_target — добавить канал-склад\n"
            "/sources — список источников (с удалением)\n"
            "/targets — список складов (с удалением)\n"
            "/bind — создать связку\n"
            "/list — список связок\n"
            "/remove — удалить связку\n"
            "/help — помощь"
        )

    @client.on(events.NewMessage(pattern=r'^/add_source', func=lambda e: e.is_private))
    async def cmd_add_source(event):
        if event.sender_id not in OWNER_IDS:
            return
        user_states[event.sender_id] = {"step": "add_source"}
        cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
        await event.respond("Перешли сообщение из канала-источника.", buttons=cancel_keyboard)

    @client.on(events.NewMessage(pattern=r'^/add_target', func=lambda e: e.is_private))
    async def cmd_add_target(event):
        if event.sender_id not in OWNER_IDS:
            return
        user_states[event.sender_id] = {"step": "add_target"}
        cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
        await event.respond("Перешли сообщение из канала-склада.", buttons=cancel_keyboard)

    @client.on(events.NewMessage(pattern=r'^/sources', func=lambda e: e.is_private))
    async def cmd_sources(event):
        if event.sender_id not in OWNER_IDS:
            return
        text, buttons = render_sources_view(db)
        await event.respond(text, buttons=buttons, parse_mode='html', link_preview=False)

    @client.on(events.NewMessage(pattern=r'^/targets', func=lambda e: e.is_private))
    async def cmd_targets(event):
        if event.sender_id not in OWNER_IDS:
            return
        text, buttons = render_targets_view(db)
        await event.respond(text, buttons=buttons, parse_mode='html', link_preview=False)

    @client.on(events.NewMessage(pattern=r'^/bind', func=lambda e: e.is_private))
    async def cmd_bind(event):
        if event.sender_id not in OWNER_IDS:
            return
        sources = db.list_sources()
        targets = db.list_targets()
        if not sources or not targets:
            await event.respond("Нет источников или складов. Сначала добавь их.")
            return
        # Сначала выбираем склады
        buttons = [
            Button.inline(f"▫ {tname}", f"bind_tgt_{tid}".encode())
            for tid, tname, _, _ in targets
        ]
        rows = chunk_buttons(buttons, per_row=2)
        rows.append([
            Button.inline("✓ Далее", b"bind_next_to_sources"),
            Button.inline("✕ Отмена", b"bind_cancel"),
        ])
        user_states[event.sender_id] = {
            "step": "bind_choose_tgts",
            "selected_tgts": set(),
            "selected_srcs": set()
        }
        await event.respond("Выбери склады для связки (можно несколько):", buttons=rows)

    @client.on(events.NewMessage(pattern=r'^/list', func=lambda e: e.is_private))
    async def cmd_list(event):
        if event.sender_id not in OWNER_IDS:
            return
        binds = db.get_bindings()
        if not binds:
            await event.respond("Связок нет.")
            return
        src_rows = {sid: (name, username, invite_link) for sid, name, username, invite_link in db.list_sources()}
        tgt_rows = {tid: (name, username, invite_link) for tid, name, username, invite_link in db.list_targets()}
        # Группируем по складам (targets), а не по источникам
        groups = {}
        for src_id, tgt_id in binds:
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
        await event.respond("\n".join(lines), parse_mode='html', link_preview=False)

    @client.on(events.NewMessage(pattern=r'^/remove', func=lambda e: e.is_private))
    async def cmd_remove(event):
        if event.sender_id not in OWNER_IDS:
            return
        binds = db.get_bindings()
        if not binds:
            await event.respond("Связок нет.")
            return
        src_rows = {sid: name for sid, name, _, _ in db.list_sources()}
        tgt_rows = {tid: name for tid, name, _, _ in db.list_targets()}
        buttons = []
        for sid, tid in binds:
            sname = src_rows.get(sid, str(sid))
            tname = tgt_rows.get(tid, str(tid))
            buttons.append([Button.inline(f"{sname} → {tname}", f"remove_{sid}_{tid}".encode())])
        buttons.append([Button.inline("✕ Отмена", b"bind_cancel")])
        await event.respond("Выбери связку для удаления:", buttons=buttons)

    # Обработка команды /skip
    @client.on(events.NewMessage(pattern=r'^/skip', func=lambda e: e.is_private))
    async def cmd_skip(event):
        if event.sender_id not in OWNER_IDS:
            return
        state = user_states.get(event.sender_id)
        if state and state.get("step") == "wait_invite_optional":
            user_states.pop(event.sender_id, None)
            await event.respond("Хорошо, канал добавлен без ссылки.", buttons=Button.clear())
        else:
            await event.respond("Эта команда доступна только при добавлении канала.")

    # Обработка добавления источников/складов
    @client.on(events.NewMessage(func=lambda e: e.is_private and not (e.message.text and e.message.text.startswith('/'))))
    async def private_steps(event):
        if event.sender_id not in OWNER_IDS:
            return
        state = user_states.get(event.sender_id)
        if not state:
            return
        step = state.get("step")
        
        # Обработка отмены через кнопку
        text = (event.message.text or "").strip()
        if text == "✕ Отмена" or text.lower() == "отмена":
            user_states.pop(event.sender_id, None)
            # Убираем клавиатуру
            await event.respond("Операция отменена.", buttons=Button.clear())
            return

        # Добавление источника/склада
        if step in {"add_source", "add_target"}:
            chat_id = None
            chat_title = None
            chat_username = None

            try:
                # Проверяем форвард
                if event.message.fwd_from:
                    from_id = event.message.fwd_from.from_id
                    if from_id:
                        # Пробуем извлечь ID напрямую из from_id
                        if hasattr(from_id, 'channel_id'):
                            raw_chat_id = from_id.channel_id
                            chat_id = normalize_channel_id(-(1000000000000 + raw_chat_id))
                            # Пробуем получить информацию о канале
                            try:
                                chat = await client.get_entity(from_id)
                                chat_id = normalize_channel_id(chat.id)
                                chat_title = get_chat_name(chat)
                                chat_username = getattr(chat, "username", None)
                            except Exception:
                                # Если не получилось получить информацию через bot client, пробуем через user client
                                chat_title = None
                                chat_username = None
                                if user_client:
                                    try:
                                        chat = await user_client.get_entity(from_id)
                                        chat_id = normalize_channel_id(chat.id)
                                        chat_title = get_chat_name(chat)
                                        chat_username = getattr(chat, "username", None)
                                    except Exception:
                                        pass
                                
                                # Если все еще нет названия, пробуем извлечь из форварда
                                if not chat_title:
                                    fwd_from = event.message.fwd_from
                                    if hasattr(fwd_from, 'from_name') and fwd_from.from_name:
                                        chat_title = fwd_from.from_name
                                    # Если названия нет, попросим пользователя указать его
                        else:
                            # Пробуем получить сущность
                            try:
                                chat = await client.get_entity(from_id)
                                chat_id = chat.id
                                chat_title = get_chat_name(chat)
                                chat_username = getattr(chat, "username", None)
                            except Exception as access_error:
                                # Если ошибка доступа, пробуем извлечь ID другим способом
                                error_str = str(access_error).lower()
                                if "private" in error_str or "permission" in error_str or "banned" in error_str:
                                    # Пробуем получить ID из peer
                                    peer = event.message.fwd_from.from_peer
                                    if peer and hasattr(peer, 'channel_id'):
                                        raw_chat_id = peer.channel_id
                                        chat_id = normalize_channel_id(-(1000000000000 + raw_chat_id))
                                        
                                        # Пробуем получить название через user client
                                        chat_title = None
                                        chat_username = None
                                        if user_client:
                                            try:
                                                chat = await user_client.get_entity(peer)
                                                chat_id = normalize_channel_id(chat.id)
                                                chat_title = get_chat_name(chat)
                                                chat_username = getattr(chat, "username", None)
                                            except Exception:
                                                pass
                                        
                                        # Если все еще нет названия, пробуем извлечь из пересланного сообщения
                                        if not chat_title:
                                            fwd_from = event.message.fwd_from
                                            if hasattr(fwd_from, 'from_name') and fwd_from.from_name:
                                                chat_title = fwd_from.from_name
                                            # Если названия нет, попросим пользователя указать его
                                    else:
                                        raise ValueError("Не удалось определить ID канала из форварда. Убедись, что бот добавлен в канал, или отправь ID канала напрямую.")
                                else:
                                    raise
                    else:
                        # Если нет from_id, пробуем получить из peer
                        peer = event.message.fwd_from.from_peer
                        if peer:
                            if hasattr(peer, 'channel_id'):
                                raw_chat_id = peer.channel_id
                                chat_id = normalize_channel_id(-(1000000000000 + raw_chat_id))
                                try:
                                    chat = await client.get_entity(peer)
                                    chat_title = get_chat_name(chat)
                                    chat_username = getattr(chat, "username", None)
                                    # Нормализуем ID из полученного чата
                                    chat_id = normalize_channel_id(chat.id)
                                except Exception:
                                    # Если не получилось получить информацию через bot client, пробуем через user client
                                    chat_title = None
                                    chat_username = None
                                    if user_client:
                                        try:
                                            chat = await user_client.get_entity(peer)
                                            chat_id = normalize_channel_id(chat.id)
                                            chat_title = get_chat_name(chat)
                                            chat_username = getattr(chat, "username", None)
                                        except Exception:
                                            pass
                                    
                                    # Если все еще нет названия, пробуем извлечь из форварда
                                    if not chat_title:
                                        fwd_from = event.message.fwd_from
                                        if hasattr(fwd_from, 'from_name') and fwd_from.from_name:
                                            chat_title = fwd_from.from_name
                                        # Если названия нет, попросим пользователя указать его
                            else:
                                chat = await client.get_entity(peer)
                                chat_id = normalize_channel_id(chat.id)
                                chat_title = get_chat_name(chat)
                                chat_username = getattr(chat, "username", None)
                        else:
                            raise ValueError("Не удалось определить источник форварда. Перешли сообщение из канала или отправь ID канала.")
                else:
                    # Проверяем текст (@username или id)
                    text = (event.message.text or "").strip()
                    if not text:
                        await event.respond("Пришли @username или numeric id канала.")
                        user_states.pop(event.sender_id, None)
                        return
                    
                    # Если это числовой ID
                    if text.lstrip('-').isdigit():
                        raw_chat_id = int(text)
                        chat_id = normalize_channel_id(raw_chat_id)
                        try:
                            chat = await client.get_entity(raw_chat_id)
                            chat_id = normalize_channel_id(chat.id)
                            chat_title = get_chat_name(chat)
                            chat_username = getattr(chat, "username", None)
                        except Exception as access_error:
                            error_str = str(access_error).lower()
                            if "private" in error_str or "permission" in error_str:
                                chat_title = f"Приватный канал {chat_id}"
                                chat_username = None
                            else:
                                raise
                    else:
                        # Пробуем получить по username или другому идентификатору
                        chat = await client.get_entity(text)
                        chat_id = normalize_channel_id(chat.id)
                        chat_title = get_chat_name(chat)
                        chat_username = getattr(chat, "username", None)

            except Exception as e:
                error_msg = str(e)
                if "private" in error_msg.lower() or "permission" in error_msg.lower() or "banned" in error_msg.lower():
                    await event.respond(
                        f"<b>Не удалось получить доступ к приватному каналу.</b>\n\n"
                        f"Варианты решения:\n"
                        f"1. Добавь бота в канал как администратора\n"
                        f"2. Отправь ID канала напрямую (например: <code>-1001234567890</code>)\n"
                        f"3. Перешли сообщение из канала (бот должен быть в канале)\n\n"
                        f"Ошибка: {error_msg}",
                        parse_mode='html',
                        buttons=Button.clear()
                    )
                else:
                    await event.respond(f"Ошибка: {error_msg}", buttons=Button.clear())
                user_states.pop(event.sender_id, None)
                return

            if not chat_id:
                await event.respond("Не удалось определить id канала. Попробуй отправить ID канала напрямую.", buttons=Button.clear())
                user_states.pop(event.sender_id, None)
                return

            if step == "add_source":
                # Проверяем, не добавлен ли уже этот источник
                if db.source_exists(chat_id):
                    existing_sources = db.list_sources()
                    for sid, sname, suser, sinv in existing_sources:
                        if sid == normalize_channel_id(chat_id):
                            await event.respond(
                                f"⚠️ Этот источник уже добавлен: {make_channel_link(sname, sid, suser, sinv)}\n\n"
                                f"Используй /sources чтобы посмотреть все источники.",
                                parse_mode='html',
                                link_preview=False,
                                buttons=Button.clear()
                            )
                            user_states.pop(event.sender_id, None)
                            return
                
                # Если название не получено, запрашиваем у пользователя
                if not chat_title:
                    user_states[event.sender_id] = {
                        "step": "wait_source_name",
                        "chat_id": chat_id,
                        "chat_username": chat_username,
                        "kind": "source"
                    }
                    await event.respond(
                        f"Не удалось получить название канала.\n\n"
                        f"ID канала: <code>{chat_id}</code>\n\n"
                        f"Пожалуйста, отправь название канала (можно просто текстом).",
                        parse_mode='html'
                    )
                    return
                
                is_new = db.add_source(chat_id, chat_title, chat_username, None)
                if is_new:
                    await event.respond(
                        f"<b>Источник добавлен:</b> {make_channel_link(chat_title, chat_id, chat_username, None)}",
                        parse_mode='html',
                        link_preview=False,
                        buttons=Button.clear()
                    )
                else:
                    await event.respond(
                        f"<b>Информация об источнике обновлена:</b> {make_channel_link(chat_title, chat_id, chat_username, None)}",
                        parse_mode='html',
                        link_preview=False,
                        buttons=Button.clear()
                    )
                if not chat_username:
                    # Предлагаем опционально добавить invite-ссылку
                    user_states[event.sender_id] = {
                        "step": "wait_invite_optional",
                        "chat_id": chat_id,
                        "kind": "source"
                    }
                    cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
                    await event.respond(
                        "Для удобства можешь прислать ссылку на канал или ссылку-приглашение (если канал приватный), "
                        "чтобы я мог добавить её в название канала для быстрого доступа.\n\n"
                        "Или отправь /skip чтобы пропустить этот шаг.",
                        parse_mode='html',
                        buttons=cancel_keyboard
                    )
                else:
                    user_states.pop(event.sender_id, None)
            else:
                # Проверяем, не добавлен ли уже этот склад
                if db.target_exists(chat_id):
                    existing_targets = db.list_targets()
                    for tid, tname, tuser, tinv in existing_targets:
                        if tid == normalize_channel_id(chat_id):
                            await event.respond(
                                f"<b>Этот склад уже добавлен:</b> {make_channel_link(tname, tid, tuser, tinv)}\n\n"
                                f"Используй /targets чтобы посмотреть все склады.",
                                parse_mode='html',
                                link_preview=False,
                                buttons=Button.clear()
                            )
                            user_states.pop(event.sender_id, None)
                            return
                
                # Если название не получено, запрашиваем у пользователя
                if not chat_title:
                    user_states[event.sender_id] = {
                        "step": "wait_target_name",
                        "chat_id": chat_id,
                        "chat_username": chat_username,
                        "kind": "target"
                    }
                    cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
                    await event.respond(
                        f"Не удалось получить название канала.\n\n"
                        f"ID канала: <code>{chat_id}</code>\n\n"
                        f"Пожалуйста, отправь название канала (можно просто текстом).",
                        parse_mode='html',
                        buttons=cancel_keyboard
                    )
                    return
                
                is_new = db.add_target(chat_id, chat_title, chat_username, None)
                if is_new:
                    await event.respond(
                        f"<b>Склад добавлен:</b> {make_channel_link(chat_title, chat_id, chat_username, None)}",
                        parse_mode='html',
                        link_preview=False,
                        buttons=Button.clear()
                    )
                else:
                    await event.respond(
                        f"<b>Информация о складе обновлена:</b> {make_channel_link(chat_title, chat_id, chat_username, None)}",
                        parse_mode='html',
                        link_preview=False,
                        buttons=Button.clear()
                    )
                if not chat_username:
                    # Предлагаем опционально добавить invite-ссылку
                    user_states[event.sender_id] = {
                        "step": "wait_invite_optional",
                        "chat_id": chat_id,
                        "kind": "target"
                    }
                    cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
                    await event.respond(
                        "Для удобства можешь прислать ссылку на канал или ссылку-приглашение (если канал приватный), "
                        "чтобы я мог добавить её в название канала для быстрого доступа.\n\n"
                        "Или отправь /skip чтобы пропустить этот шаг.",
                        parse_mode='html',
                        buttons=cancel_keyboard
                    )
                else:
                    user_states.pop(event.sender_id, None)
            return

        # Ожидание названия канала
        if step in {"wait_source_name", "wait_target_name"}:
            name = (event.message.text or "").strip()
            if not name:
                cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
                await event.respond("Название не может быть пустым. Отправь название канала текстом.", buttons=cancel_keyboard)
                return
            
            cid = state.get("chat_id")
            c_username = state.get("chat_username")
            kind = state.get("kind")
            
            if not cid or kind not in {"source", "target"}:
                user_states.pop(event.sender_id, None)
                await event.respond("Состояние сброшено. Повтори добавление.")
                return
            
            if kind == "source":
                # Проверяем, не добавлен ли уже этот источник
                if db.source_exists(cid):
                    existing_sources = db.list_sources()
                    for sid, sname, suser, sinv in existing_sources:
                        if sid == normalize_channel_id(cid):
                            await event.respond(
                                f"⚠️ Этот источник уже добавлен: {make_channel_link(sname, sid, suser, sinv)}\n\n"
                                f"Используй /sources чтобы посмотреть все источники.",
                                parse_mode='html',
                                link_preview=False,
                                buttons=Button.clear()
                            )
                            user_states.pop(event.sender_id, None)
                            return
                
                is_new = db.add_source(cid, name, c_username, None)
                if is_new:
                    await event.respond(
                        f"<b>Источник добавлен:</b> {make_channel_link(name, cid, c_username, None)}",
                        parse_mode='html',
                        link_preview=False,
                        buttons=Button.clear()
                    )
                else:
                    await event.respond(
                        f"<b>Информация об источнике обновлена:</b> {make_channel_link(name, cid, c_username, None)}",
                        parse_mode='html',
                        link_preview=False,
                        buttons=Button.clear()
                    )
                if not c_username:
                    user_states[event.sender_id] = {
                        "step": "wait_invite_optional",
                        "chat_id": cid,
                        "kind": "source"
                    }
                    cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
                    await event.respond(
                        "💡 Для удобства можешь прислать ссылку на канал или ссылку-приглашение (если канал приватный), "
                        "чтобы я мог добавить её в название канала для быстрого доступа.\n\n"
                        "Или отправь /skip чтобы пропустить этот шаг.",
                        parse_mode='html',
                        buttons=cancel_keyboard
                    )
                else:
                    user_states.pop(event.sender_id, None)
            else:
                # Проверяем, не добавлен ли уже этот склад
                if db.target_exists(cid):
                    existing_targets = db.list_targets()
                    for tid, tname, tuser, tinv in existing_targets:
                        if tid == normalize_channel_id(cid):
                            await event.respond(
                                f"<b>Этот склад уже добавлен:</b> {make_channel_link(tname, tid, tuser, tinv)}\n\n"
                                f"Используй /targets чтобы посмотреть все склады.",
                                parse_mode='html',
                                link_preview=False,
                                buttons=Button.clear()
                            )
                            user_states.pop(event.sender_id, None)
                            return
                
                is_new = db.add_target(cid, name, c_username, None)
                if is_new:
                    await event.respond(
                        f"<b>Склад добавлен:</b> {make_channel_link(name, cid, c_username, None)}",
                        parse_mode='html',
                        link_preview=False,
                        buttons=Button.clear()
                    )
                else:
                    await event.respond(
                        f"<b>Информация о складе обновлена:</b> {make_channel_link(name, cid, c_username, None)}",
                        parse_mode='html',
                        link_preview=False,
                        buttons=Button.clear()
                    )
                if not c_username:
                    user_states[event.sender_id] = {
                        "step": "wait_invite_optional",
                        "chat_id": cid,
                        "kind": "target"
                    }
                    cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
                    await event.respond(
                        "💡 Для удобства можешь прислать ссылку на канал или ссылку-приглашение (если канал приватный), "
                        "чтобы я мог добавить её в название канала для быстрого доступа.\n\n"
                        "Или отправь /skip чтобы пропустить этот шаг.",
                        parse_mode='html',
                        buttons=cancel_keyboard
                    )
                else:
                    user_states.pop(event.sender_id, None)
            return

        # Ожидание инвайта (опционально)
        if step == "wait_invite_optional":
            cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
            text = (event.message.text or "").strip()
            
            # Пропуск шага
            if text.lower() == "/skip":
                user_states.pop(event.sender_id, None)
                await event.respond("Хорошо, канал добавлен без ссылки.", buttons=Button.clear())
                return
            
            # Проверяем, является ли это ссылкой (invite или обычная ссылка на канал)
            is_link = False
            invite_link = None
            
            # Проверяем invite-ссылку
            if is_invite_link(text):
                is_link = True
                invite_link = text
            # Проверяем обычную ссылку на канал (https://t.me/username или https://t.me/+...)
            elif text.startswith("https://t.me/") or text.startswith("tg://"):
                is_link = True
                invite_link = text
            
            if not is_link:
                cancel_keyboard = [[Button.text("✕ Отмена", resize=True, single_use=True)]]
                await event.respond(
                    "Это не похоже на ссылку. Пришли ссылку на канал или ссылку-приглашение.\n\n"
                    "Или отправь /skip чтобы пропустить этот шаг.",
                    buttons=cancel_keyboard
                )
                return
            
            cid = state.get("chat_id")
            kind = state.get("kind")
            if not cid or kind not in {"source", "target"}:
                user_states.pop(event.sender_id, None)
                await event.respond("Состояние сброшено. Повтори добавление.", buttons=Button.clear())
                return
            
            try:
                if kind == "source":
                    db.update_source_invite(cid, invite_link)
                    await event.respond("<b>Ссылка сохранена для источника.</b> Теперь название канала будет кликабельным.", parse_mode='html', link_preview=False, buttons=Button.clear())
                else:
                    db.update_target_invite(cid, invite_link)
                    await event.respond("<b>Ссылка сохранена для склада.</b> Теперь название канала будет кликабельным.", parse_mode='html', link_preview=False, buttons=Button.clear())
            except Exception as e:
                # Если ошибка при сохранении (например, API restriction), просто сохраняем ссылку без проверки
                if kind == "source":
                    db.update_source_invite(cid, invite_link)
                    await event.respond("<b>Ссылка сохранена для источника.</b>", parse_mode='html', link_preview=False, buttons=Button.clear())
                else:
                    db.update_target_invite(cid, invite_link)
                    await event.respond("<b>Ссылка сохранена для склада.</b>", parse_mode='html', link_preview=False, buttons=Button.clear())
            
            user_states.pop(event.sender_id, None)
            return
