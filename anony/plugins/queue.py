# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import time
from pyrogram import filters, types

from anony import app, config, db, lang, queue, thumb
from anony.helpers import Track, buttons


@app.on_message(filters.command(["queue", "playing"]) & filters.group & ~app.bl_users)
@lang.language()
async def _queue_func(_, m: types.Message):
    if not await db.get_call(m.chat.id):
        return await m.reply_text(m.lang["not_playing"])

    _reply = await m.reply_text(m.lang["queue_fetching"])
    _queue = queue.get_queue(m.chat.id)
    if not _queue:
        return await _reply.edit_text(m.lang["not_playing"])

    _media = _queue[0]
    _thumb = (
        await thumb.generate(_media)
        if isinstance(_media, Track)
        else config.DEFAULT_THUMB
    ) if config.THUMB_GEN else None

    bot_mention = app.me.mention if hasattr(app, "me") and app.me else "Bot"
    stream_type = "Video" if getattr(_media, "video", False) else "Audio"
    title = f"<a href='{_media.url}'>{_media.title}</a>" if _media.url else _media.title
    user = _media.user or "Unknown"

    _text = (
        f"{bot_mention} ᴘʟᴀʏᴇʀ\n\n"
        f"🎄 sᴛʀᴇᴀᴍɪɴɢ : {title}\n\n"
        f"🔗 sᴛʀᴇᴀᴍ ᴛʏᴘᴇ : {stream_type}\n"
        f"🥀 ʀᴇǫᴜᴇsᴛᴇᴅ ʙʏ : {user}\n\n"
        f"ᴄʟɪᴄᴋ ᴏɴ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ɢᴇᴛ ᴡʜᴏʟᴇ ǫᴜᴇᴜᴇᴅ ʟɪsᴛ."
    )

    played = _media.time or 0
    duration = _media.duration_sec or 0
    if duration:
        remaining = max(duration - played, 0)
        length = 10
        pos = min(int((played / duration) * length), length - 1)
        bar = "—" * pos + "◉" + "—" * (length - pos - 1)
        slidebar = f"{time.strftime('%M:%S', time.gmtime(played))} | {bar} | -{time.strftime('%M:%S', time.gmtime(remaining))}"
    else:
        slidebar = "00:00 | ◉————————— | -00:00"

    _buttons = buttons.queue_markup(m.chat.id, slidebar)
    try:
        if _thumb:
            await _reply.edit_media(
                media=types.InputMediaPhoto(
                    media=_thumb,
                    caption=_text,
                ),
                reply_markup=_buttons,
            )
        else:
            await _reply.edit_text(
                text=_text,
                reply_markup=_buttons,
            )
    except Exception:
        await _reply.edit_text(
            text=_text,
            reply_markup=_buttons,
        )
