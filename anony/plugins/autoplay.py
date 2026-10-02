# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


from pyrogram import filters, types

from anony import app, db, lang
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
            return await m.reply_text(m.lang["autoplay_on"])
        elif arg in ["off", "disable", "false", "no"]:
            await db.set_autoplay(chat_id, False)
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

    st_text = query.lang["autoplay_enabled"] if status else query.lang["autoplay_disabled"]
    await query.edit_message_text(
        query.lang["autoplay_status"].format(st_text),
        reply_markup=buttons.autoplay_markup(chat_id, status),
    )
