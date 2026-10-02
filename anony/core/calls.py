# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import asyncio
from pathlib import Path

from ntgcalls import (ConnectionNotFound, TelegramServerError,
                      RTMPStreamingUnsupported, ConnectionError,
                      TransportParseException)
from pyrogram.errors import (ChatSendMediaForbidden, ChatSendPhotosForbidden,
                             MessageIdInvalid)
from pyrogram.types import InputMediaPhoto, Message
from pytgcalls import PyTgCalls, exceptions, types
from pytgcalls.pytgcalls_session import PyTgCallsSession

from anony import (app, config, db, lang, logger,
                   queue, thumb, userbot, yt)
from anony.helpers import Media, Track, buttons


class TgCall(PyTgCalls):
    def __init__(self):
        self.clients = []
        self._dl_queue = asyncio.Queue()
        self._dl_tasks = []
        self._downloading = set()
        self.last_track = {}
        self.played_tracks = {}
        self.autoplay_active = {}
        self.empty_prompt_msg = {}

    async def _dl_worker(self):
        while True:
            media = await self._dl_queue.get()
            try:
                if media and not getattr(media, "file_path", None):
                    await self.download_track(media)
            except Exception as e:
                logger.warning(f"Background download error: {e}")
            finally:
                self._dl_queue.task_done()

    def queue_download(self, media: Track | Media) -> None:
        """Enqueue track for background download so it is ready in 0 ms."""
        if not media or getattr(media, "file_path", None):
            return
        if getattr(media, "id", None) in self._downloading:
            return
        self._downloading.add(media.id)
        self._dl_queue.put_nowait(media)

    async def download_track(self, media: Track | Media) -> str | None:
        """Download track in background, pre-generate thumbnail, and cache metadata."""
        if not media:
            return None
        if getattr(media, "file_path", None) and Path(media.file_path).exists():
            return media.file_path

        video = getattr(media, "video", False)
        ext = "mp4" if video else "webm"
        fname = f"downloads/{media.id}.{ext}"

        if Path(fname).exists() and Path(fname).stat().st_size > 1024:
            media.file_path = fname
            if hasattr(media, "title") and media.title:
                await db.save_song({
                    "id": media.id,
                    "title": media.title,
                    "duration": getattr(media, "duration", "0:00"),
                    "duration_sec": getattr(media, "duration_sec", 0),
                    "file_path": fname,
                    "video": video,
                })
            return fname

        try:
            file_path = await yt.download(media.id, video=video)
            if file_path:
                media.file_path = file_path
                if config.THUMB_GEN and isinstance(media, Track):
                    try:
                        await thumb.generate(media)
                    except Exception:
                        pass
                if hasattr(media, "title") and media.title:
                    await db.save_song({
                        "id": media.id,
                        "title": media.title,
                        "duration": getattr(media, "duration", "0:00"),
                        "duration_sec": getattr(media, "duration_sec", 0),
                        "file_path": file_path,
                        "video": video,
                    })
                return file_path
        except Exception as e:
            logger.warning(f"Download failed for {media.id}: {e}")
        finally:
            self._downloading.discard(media.id)
        return None

    async def pause(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        await db.playing(chat_id, paused=True)
        try:
            return await client.pause(chat_id)
        except (ConnectionNotFound, exceptions.NotInCallError):
            await self.stop(chat_id)

    async def resume(self, chat_id: int) -> bool:
        client = await db.get_assistant(chat_id)
        await db.playing(chat_id, paused=False)
        try:
            return await client.resume(chat_id)
        except (ConnectionNotFound, exceptions.NotInCallError):
            await self.stop(chat_id)

    async def stop(self, chat_id: int) -> None:
        client = await db.get_assistant(chat_id)
        queue.clear(chat_id)
        await db.remove_call(chat_id)
        await db.set_loop(chat_id, 0)
        self.last_track.pop(chat_id, None)
        self.played_tracks.pop(chat_id, None)
        self.autoplay_active.pop(chat_id, None)
        if prompt_id := self.empty_prompt_msg.pop(chat_id, None):
            try:
                await app.delete_messages(chat_id=chat_id, message_ids=prompt_id)
            except Exception:
                pass

        try:
            await client.leave_call(chat_id, close=False)
        except Exception:
            pass


    async def play_media(
        self,
        chat_id: int,
        message: Message,
        media: Media | Track,
        seek_time: int = 0,
    ) -> None:
        client = await db.get_assistant(chat_id)
        _lang = await lang.get_lang(chat_id)
        _thumb = (
            await thumb.generate(media)
            if isinstance(media, Track)
            else config.DEFAULT_THUMB
        ) if config.THUMB_GEN else None

        if not media.file_path:
            await message.edit_text(_lang["error_no_file"].format(config.SUPPORT_CHAT))
            return await self.play_next(chat_id)

        stream = types.MediaStream(
            media_path=media.file_path,
            audio_parameters=types.AudioQuality.HIGH,
            video_parameters=types.VideoQuality.HD_720p,
            audio_flags=types.MediaStream.Flags.REQUIRED,
            video_flags=(
                types.MediaStream.Flags.AUTO_DETECT
                if media.video
                else types.MediaStream.Flags.IGNORE
            ),
            ffmpeg_parameters=f"-ss {seek_time}" if seek_time > 1 else None,
        )
        try:
            await client.play(
                chat_id=chat_id,
                stream=stream,
                config=types.GroupCallConfig(auto_start=False),
            )
            if not seek_time:
                media.time = 1
                await db.add_call(chat_id)
                self.last_track[chat_id] = media
                if getattr(media, "id", None):
                    if chat_id not in self.played_tracks:
                        self.played_tracks[chat_id] = []
                    if media.id not in self.played_tracks[chat_id]:
                        self.played_tracks[chat_id].append(media.id)
                    if len(self.played_tracks[chat_id]) > 50:
                        self.played_tracks[chat_id].pop(0)
                title = f"<a href='{media.url}'>{media.title}</a>" if media.url else media.title
                text = (
                    f"<blockquote><b>❖  𝛅ᴛᴧʀᴛєᴅ  𝛅ᴛʀєᴧϻɪηɢ</b></blockquote>\n"
                    f"<blockquote>❍ тɪᴛʟє : {title}\n"
                    f"❍ ᴅᴜʀᴧᴛɪση : {media.duration} ϻɪηᴜᴛєs\n"
                    f"❍ ʙʏ : {media.user}</blockquote>"
                )
                keyboard = buttons.controls(chat_id)
                try:
                    if _thumb:
                        await message.edit_media(
                            media=InputMediaPhoto(
                                media=_thumb,
                                caption=text,
                            ),
                            reply_markup=keyboard,
                        )
                    else:
                        await message.edit_text(text, reply_markup=keyboard)
                except (ChatSendMediaForbidden, ChatSendPhotosForbidden, MessageIdInvalid):
                    if _thumb:
                        sent = await app.send_photo(
                            chat_id=chat_id,
                            photo=_thumb,
                            caption=text,
                            reply_markup=keyboard,
                        )
                    else:
                        sent = await app.send_message(
                            chat_id=chat_id,
                            text=text,
                            reply_markup=keyboard,
                        )
                    media.message_id = sent.id
        except FileNotFoundError:
            await message.edit_text(_lang["error_no_file"].format(config.SUPPORT_CHAT))
            await self.play_next(chat_id)
        except exceptions.NoActiveGroupCall:
            await self.stop(chat_id)
            await message.edit_text(_lang["error_no_call"])
        except exceptions.NoAudioSourceFound:
            await message.edit_text(_lang["error_no_audio"])
            await self.play_next(chat_id)
        except (ConnectionError, ConnectionNotFound, TelegramServerError,
                TransportParseException, TimeoutError):
            await self.stop(chat_id)
            await message.edit_text(_lang["error_tg_server"])
        except RTMPStreamingUnsupported:
            await self.stop(chat_id)
            await message.edit_text(_lang["error_rtmp"])


    async def replay(self, chat_id: int) -> None:
        if not await db.get_call(chat_id):
            return

        media = queue.get_current(chat_id)
        _lang = await lang.get_lang(chat_id)
        msg = await app.send_message(chat_id=chat_id, text=_lang["play_again"])
        media.message_id = msg.id
        await self.play_media(chat_id, msg, media)


    async def play_next(self, chat_id: int) -> None:
        if loop := await db.get_loop(chat_id):
            await db.set_loop(chat_id, loop - 1)
            return await self.replay(chat_id)

        media = queue.get_next(chat_id)
        if not media:
            if self.autoplay_active.get(chat_id):
                if await self.handle_autoplay(chat_id):
                    return
            return await self.send_queue_empty(chat_id)

        try:
            if media.message_id:
                await app.delete_messages(
                    chat_id=chat_id,
                    message_ids=media.message_id,
                    revoke=True,
                )
                media.message_id = 0
        except Exception:
            pass

        # Check if already downloaded on disk
        if not media.file_path:
            ext = "mp4" if getattr(media, "video", False) else "webm"
            fname = f"downloads/{media.id}.{ext}"
            if Path(fname).exists() and Path(fname).stat().st_size > 1024:
                media.file_path = fname

        # Proactively queue background download for the next upcoming track in line
        upcoming = queue.get_next(chat_id, check=True)
        if upcoming and not upcoming.file_path:
            self.queue_download(upcoming)

        _lang = await lang.get_lang(chat_id)

        if media.file_path:
            # 0 ms INSTANT PLAY: play directly without waiting
            sent = await app.send_message(chat_id=chat_id, text=_lang["processing"])
            media.message_id = sent.id
            await self.play_media(chat_id, sent, media)
        else:
            msg = await app.send_message(chat_id=chat_id, text=_lang["play_next"])
            media.file_path = await self.download_track(media)
            if not media.file_path:
                await self.play_next(chat_id)
                return await msg.edit_text(
                    _lang["error_no_file"].format(config.SUPPORT_CHAT)
                )
            media.message_id = msg.id
            await self.play_media(chat_id, msg, media)


    async def send_queue_empty(self, chat_id: int) -> None:
        last_media = self.last_track.get(chat_id)
        if last_media and getattr(last_media, "message_id", None):
            try:
                await app.delete_messages(
                    chat_id=chat_id,
                    message_ids=last_media.message_id,
                    revoke=True,
                )
                last_media.message_id = 0
            except Exception:
                pass

        _lang = await lang.get_lang(chat_id)
        text = _lang.get(
            "autoplay_queue_empty",
            (
                "<blockquote><b>𝖭ᴏ 𝖬ᴏʀᴇ 𝖲ᴏɴɢs ɪɴ ᴛʜᴇ 𝖰ᴜᴇᴜᴇ\n"
                "ᴛʜᴇ ᴘʟᴀʏʟɪsᴛ ʜᴀs ᴇɴᴅᴇᴅ — ʜɪᴛ ᴀᴜᴛᴏᴘʟᴀʏ ᴛᴏ ᴋᴇᴇᴘ ᴛʜᴇ ᴍᴜsɪᴄ ɢᴏɪɴɢ.</b></blockquote>"
            ),
        )
        keyboard = buttons.autoplay_prompt_markup(chat_id)
        try:
            sent = await app.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
            )
            self.empty_prompt_msg[chat_id] = sent.id
        except Exception as e:
            logger.warning(f"Failed to send queue empty message: {e}")


    async def handle_autoplay(self, chat_id: int, force: bool = False) -> bool:
        if not force and not await db.is_autoplay(chat_id):
            return False

        last_media = self.last_track.get(chat_id)
        if not last_media or not getattr(last_media, "id", None):
            return False

        _lang = await lang.get_lang(chat_id)
        video_id = last_media.id
        title = getattr(last_media, "title", "")
        video = getattr(last_media, "video", False)

        candidates = await yt.get_related(video_id=video_id, title=title, video=video)
        if not candidates:
            return False

        played = set(self.played_tracks.get(chat_id, []))
        chosen = None
        for cand in candidates:
            if cand.id not in played:
                chosen = cand
                break

        if not chosen:
            for cand in candidates:
                if cand.id != video_id:
                    chosen = cand
                    break
            if not chosen:
                chosen = candidates[0]

        chosen.user = "˹ᴧᴜᴛᴏᴘʟᴧʏ˼ 📻"
        chosen.video = video

        queue.add(chat_id, chosen)
        if chat_id not in self.played_tracks:
            self.played_tracks[chat_id] = []
        if chosen.id not in self.played_tracks[chat_id]:
            self.played_tracks[chat_id].append(chosen.id)

        ext = "mp4" if video else "webm"
        fname = f"downloads/{chosen.id}.{ext}"
        if Path(fname).exists() and Path(fname).stat().st_size > 1024:
            chosen.file_path = fname

        # Proactively queue background download for the next recommendation
        for next_cand in candidates:
            if next_cand.id != chosen.id and next_cand.id not in played:
                self.queue_download(next_cand)
                break

        # Delete previous track message or empty prompt if present
        if last_media and getattr(last_media, "message_id", None):
            try:
                await app.delete_messages(
                    chat_id=chat_id,
                    message_ids=last_media.message_id,
                    revoke=True,
                )
            except Exception:
                pass

        if prompt_id := self.empty_prompt_msg.pop(chat_id, None):
            try:
                await app.delete_messages(
                    chat_id=chat_id,
                    message_ids=prompt_id,
                    revoke=True,
                )
            except Exception:
                pass

        self.autoplay_active[chat_id] = True

        if chosen.file_path:
            sent = await app.send_message(chat_id=chat_id, text=_lang["processing"])
            chosen.message_id = sent.id
            await self.play_media(chat_id, sent, chosen)
        else:
            msg = await app.send_message(chat_id=chat_id, text=_lang["processing"])
            chosen.file_path = await self.download_track(chosen)
            if not chosen.file_path:
                queue.remove_current(chat_id)
                return await self.handle_autoplay(chat_id, force=force)
            chosen.message_id = msg.id
            await self.play_media(chat_id, msg, chosen)

        return True


    async def ping(self) -> float:
        pings = [client.ping for client in self.clients]
        return round(sum(pings) / len(pings), 2)


    async def decorators(self, client: PyTgCalls) -> None:
        @client.on_update()
        async def update_handler(_, update: types.Update) -> None:
            if isinstance(update, types.StreamEnded):
                if update.stream_type == types.StreamEnded.Type.AUDIO:
                    await self.play_next(update.chat_id)
            elif isinstance(update, types.ChatUpdate):
                if update.status in [
                    types.ChatUpdate.Status.KICKED,
                    types.ChatUpdate.Status.LEFT_GROUP,
                    types.ChatUpdate.Status.CLOSED_VOICE_CHAT,
                ]:
                    await self.stop(update.chat_id)


    async def boot(self) -> None:
        PyTgCallsSession.notice_displayed = True
        for ub in userbot.clients:
            client = PyTgCalls(ub, cache_duration=100)
            await client.start()
            self.clients.append(client)
            await self.decorators(client)
        for _ in range(2):
            self._dl_tasks.append(asyncio.create_task(self._dl_worker()))
        logger.info("PyTgCalls client(s) started.")
