# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


from pyrogram import filters, types

from anony import anon, app, config, db, lang
from anony.helpers import buttons, can_manage_vc


@app.on_message(filters.command(["autoplay"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def autoplay_cmd(_, m: types.Message):
    chat_id = m.chat.id
    if len(m.command) >= 2:
        arg = m.command[1].lower()
        if arg in ["on", "enable", "true", "yes"]:
            await db.set_autoplay(chat_id, True)
            anon.autoplay_active[chat_id] = True
            return await m.reply_text(m.lang["autoplay_on"])
        elif arg in ["off", "disable", "false", "no"]:
            await db.set_autoplay(chat_id, False)
            anon.autoplay_active[chat_id] = False
            return await m.reply_text(m.lang["autoplay_off"])

    status = await db.is_autoplay(chat_id)
    st_text = m.lang["autoplay_enabled"] if status else m.lang["autoplay_disabled"]
    await m.reply_text(
        m.lang["autoplay_status"].format(st_text),
        reply_markup=buttons.autoplay_markup(chat_id, status),
    )


@app.on_callback_query(filters.regex(r"^autoplay_toggle") & ~app.bl_users)
@lang.language()
@can_manage_vc
async def autoplay_cb(_, query: types.CallbackQuery):
    args = query.data.split()
    chat_id = int(args[1])
    action = args[2]
    status = action == "enable"
    await db.set_autoplay(chat_id, status)
    anon.autoplay_active[chat_id] = status

    st_text = query.lang["autoplay_enabled"] if status else query.lang["autoplay_disabled"]
    await query.edit_message_text(
        query.lang["autoplay_status"].format(st_text),
        reply_markup=buttons.autoplay_markup(chat_id, status),
    )


@app.on_callback_query(filters.regex(r"^autoplay_start") & ~app.bl_users)
@lang.language()
async def autoplay_start_cb(_, query: types.CallbackQuery):
    args = query.data.split()
    chat_id = int(args[1])
    try:
        await query.answer()
    except Exception:
        pass

    try:
        await query.message.delete()
    except Exception:
        pass

    anon.autoplay_active[chat_id] = True
    await db.set_autoplay(chat_id, True)

    success = await anon.handle_autoplay(chat_id, force=True)
    if not success:
        await app.send_message(
            chat_id=chat_id,
            text=query.lang["error_no_file"].format(config.SUPPORT_CHAT),
        )
        await anon.stop(chat_id)


@app.on_callback_query(filters.regex(r"^autoplay_close") & ~app.bl_users)
@lang.language()
async def autoplay_close_cb(_, query: types.CallbackQuery):
    args = query.data.split()
    chat_id = int(args[1])
    try:
        await query.answer()
    except Exception:
        pass

    try:
        await query.message.delete()
    except Exception:
        pass

    await anon.stop(chat_id)
