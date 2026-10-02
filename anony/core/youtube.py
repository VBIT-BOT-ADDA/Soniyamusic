# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import os
import re
import yt_dlp
import random
import asyncio
import aiohttp
from pathlib import Path

from py_yt import Playlist, VideosSearch

from anony import config, logger
from anony.helpers import Track, utils


class DummyLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass

class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.cookie_dir = "anony/cookies"
        self.warned = False
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.iregex = re.compile(
            r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)"
            r"(?!/(watch\?v=[A-Za-z0-9_-]{11}|shorts/[A-Za-z0-9_-]{11}"
            r"|playlist\?list=PL[A-Za-z0-9_-]+|[A-Za-z0-9_-]{11}))\S*"
        )

    def get_cookies(self):
        if not self.checked:
            for file in os.listdir(self.cookie_dir):
                if file.endswith(".txt"):
                    self.cookies.append(f"{self.cookie_dir}/{file}")
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return random.choice(self.cookies)

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        async with aiohttp.ClientSession() as session:
            for url in urls:
                name = url.split("/")[-1]
                link = "https://batbin.me/raw/" + name
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(f"{self.cookie_dir}/{name}.txt", "wb") as fw:
                        fw.write(await resp.read())
        logger.info(f"Cookies saved in {self.cookie_dir}.")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def invalid(self, url: str) -> bool:
        return bool(re.match(self.iregex, url))

    async def _arc_search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        if not getattr(config, "ARC_API_KEY", None):
            return None
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            api_url = f"{config.ARC_API_URL.rstrip('/')}/youtube/v2/search"
            params = {
                "query": query,
                "limit": 1,
                "api_key": config.ARC_API_KEY,
            }
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results")
                        if results and isinstance(results, list) and len(results) > 0:
                            first = results[0]
                            track_id = first.get("video_id")
                            if not track_id:
                                return None

                            dur = first.get("duration", "0:00")
                            try:
                                dur_sec = utils.to_seconds(dur)
                            except Exception:
                                dur_sec = 0

                            file_path = None
                            for c_ext in (["mp4"] if video else ["webm", "mp3", "m4a"]):
                                fn = f"downloads/{track_id}.{c_ext}"
                                if Path(fn).exists() and Path(fn).stat().st_size > 1024:
                                    file_path = fn
                                    break

                            track = Track(
                                id=track_id,
                                channel_name=first.get("channel", ""),
                                duration=dur,
                                duration_sec=dur_sec,
                                message_id=m_id,
                                title=first.get("title", "")[:25],
                                thumbnail=first.get("thumbnail", ""),
                                url=first.get("url") or f"https://www.youtube.com/watch?v={track_id}",
                                view_count=first.get("views", ""),
                                video=video,
                            )
                            if file_path:
                                track.file_path = file_path
                            return track
        except Exception as e:
            logger.warning(f"Arc API search error: {e}")
        return None

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        arc_track = await self._arc_search(query, m_id, video=video)
        if arc_track:
            return arc_track

        try:
            _search = VideosSearch(query, limit=1, with_live=False)
            results = await _search.next()
        except Exception:
            return None
        if results and results["result"]:
            data = results["result"][0]
            track_id = data.get("id")
            ext = "mp4" if video else "webm"
            fname = f"downloads/{track_id}.{ext}"
            file_path = fname if Path(fname).exists() and Path(fname).stat().st_size > 1024 else None

            track = Track(
                id=track_id,
                channel_name=data.get("channel", {}).get("name"),
                duration=data.get("duration"),
                duration_sec=utils.to_seconds(data.get("duration")),
                message_id=m_id,
                title=data.get("title")[:25],
                thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                video=video,
            )
            if file_path:
                track.file_path = file_path
            return track
        return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                track_id = data.get("id")
                ext = "mp4" if video else "webm"
                fname = f"downloads/{track_id}.{ext}"
                file_path = fname if Path(fname).exists() and Path(fname).stat().st_size > 1024 else None
                track = Track(
                    id=track_id,
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails")[-1].get("url").split("?")[0],
                    url=data.get("link").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                if file_path:
                    track.file_path = file_path
                tracks.append(track)
        except Exception:
            pass
        return tracks

    async def get_related(
        self, video_id: str, title: str = "", video: bool = False, limit: int = 15
    ) -> list[Track]:
        tracks: list[Track] = []
        if not video_id and not title:
            return tracks

        # Strategy 1: YouTube Innertube /youtubei/v1/next endpoint
        if video_id:
            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                }
                payload = {
                    "context": {
                        "client": {
                            "clientName": "WEB",
                            "clientVersion": "2.20240101.00.00",
                            "hl": "en",
                            "gl": "IN",
                        }
                    },
                    "videoId": video_id,
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://www.youtube.com/youtubei/v1/next",
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=8),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results = (
                                data.get("contents", {})
                                .get("twoColumnWatchNextResults", {})
                                .get("secondaryResults", {})
                                .get("secondaryResults", {})
                                .get("results", [])
                            )
                            for item in results:
                                cid = None
                                t_title = None
                                dur = "0:00"
                                channel = ""
                                thumb_url = None

                                if "lockupViewModel" in item:
                                    vm = item["lockupViewModel"]
                                    cid = vm.get("contentId")
                                    meta = vm.get("metadata", {}).get("lockupMetadataViewModel", {})
                                    t_title = meta.get("title", {}).get("content")
                                    rows = meta.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
                                    if rows and rows[0].get("metadataParts"):
                                        channel = rows[0]["metadataParts"][0].get("text", {}).get("content", "")
                                    for o in vm.get("contentImage", {}).get("thumbnailViewModel", {}).get("overlays", []):
                                        badges = o.get("thumbnailBottomOverlayViewModel", {}).get("badges", [])
                                        for b in badges:
                                            t = b.get("thumbnailBadgeViewModel", {}).get("text")
                                            if t:
                                                dur = t
                                                break
                                        if dur != "0:00":
                                            break
                                    thumb_url = f"https://i.ytimg.com/vi/{cid}/hqdefault.jpg"

                                elif "compactVideoRenderer" in item:
                                    cvr = item["compactVideoRenderer"]
                                    cid = cvr.get("videoId")
                                    title_dict = cvr.get("title", {})
                                    t_title = title_dict.get("simpleText") or (
                                        title_dict.get("runs", [{}])[0].get("text") if title_dict.get("runs") else ""
                                    )
                                    dur = cvr.get("lengthText", {}).get("simpleText", "0:00")
                                    channel = cvr.get("shortBylineText", {}).get("runs", [{}])[0].get("text", "")
                                    thumb_url = f"https://i.ytimg.com/vi/{cid}/hqdefault.jpg"

                                if cid and t_title and cid != video_id and len(cid) == 11 and not cid.startswith(("RD", "PL")):
                                    try:
                                        dur_sec = utils.to_seconds(dur)
                                    except Exception:
                                        dur_sec = 0
                                    if dur_sec < 10:
                                        continue
                                    ext = "mp4" if video else "webm"
                                    fname = f"downloads/{cid}.{ext}"
                                    file_path = (
                                        fname
                                        if Path(fname).exists() and Path(fname).stat().st_size > 1024
                                        else None
                                    )
                                    trk = Track(
                                        id=cid,
                                        channel_name=channel,
                                        duration=dur,
                                        duration_sec=dur_sec,
                                        title=t_title[:25],
                                        thumbnail=thumb_url,
                                        url=f"https://www.youtube.com/watch?v={cid}",
                                        user="˹ᴧᴜᴛᴏᴘʟᴧʏ˼ 📻",
                                        video=video,
                                        file_path=file_path,
                                    )
                                    tracks.append(trk)
                                    if len(tracks) >= limit:
                                        break
            except Exception as e:
                logger.warning(f"Innertube related error: {e}")

        # Strategy 2: VideosSearch fallback
        if not tracks and title:
            try:
                query = f"{title} song"
                _search = VideosSearch(query, limit=limit, with_live=False)
                res = await _search.next()
                if res and res.get("result"):
                    for data in res["result"]:
                        cid = data.get("id")
                        if not cid or cid == video_id:
                            continue
                        dur = data.get("duration", "0:00")
                        try:
                            dur_sec = utils.to_seconds(dur)
                        except Exception:
                            dur_sec = 0
                        ext = "mp4" if video else "webm"
                        fname = f"downloads/{cid}.{ext}"
                        file_path = (
                            fname
                            if Path(fname).exists() and Path(fname).stat().st_size > 1024
                            else None
                        )
                        trk = Track(
                            id=cid,
                            channel_name=data.get("channel", {}).get("name", ""),
                            duration=dur,
                            duration_sec=dur_sec,
                            title=data.get("title", "")[:25],
                            thumbnail=data.get("thumbnails", [{}])[-1].get("url", "").split("?")[0],
                            url=data.get("link"),
                            user="˹ᴧᴜᴛᴏᴘʟᴧʏ˼ 📻",
                            video=video,
                            file_path=file_path,
                        )
                        tracks.append(trk)
                        if len(tracks) >= limit:
                            break
            except Exception as e:
                logger.warning(f"VideosSearch related fallback error: {e}")

        return tracks

    async def _arc_download(self, video_id: str, video: bool = False) -> str | None:
        if not getattr(config, "ARC_API_KEY", None):
            return None

        # Check existing downloads first
        for c_ext in (["mp4"] if video else ["webm", "mp3", "m4a"]):
            fn = f"downloads/{video_id}.{c_ext}"
            if Path(fn).exists() and Path(fn).stat().st_size > 1024:
                return fn

        try:
            api_url = f"{config.ARC_API_URL.rstrip('/')}/youtube/v2/download"
            params = {
                "query": video_id,
                "isVideo": "true" if video else "false",
                "api_key": config.ARC_API_KEY,
            }
            cdn = None
            timeout = aiohttp.ClientTimeout(total=25)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == "success" and data.get("result"):
                            cdn = data["result"].get("cdn")
                        elif data.get("status") == "queued" and data.get("job_id"):
                            job_id = data["job_id"]
                            status_url = f"{config.ARC_API_URL.rstrip('/')}/youtube/jobStatus"
                            for _ in range(12):
                                await asyncio.sleep(2)
                                async with session.get(status_url, params={"job_id": job_id}) as sresp:
                                    if sresp.status == 200:
                                        sdata = await sresp.json()
                                        job = sdata.get("job", {})
                                        if job.get("status") == "done":
                                            res = job.get("result", {})
                                            if res.get("success") and res.get("cdn"):
                                                cdn = res["cdn"]
                                            break
                                        elif job.get("status") == "failed":
                                            break

            if not cdn:
                return None

            target_ext = "mp4" if video else "mp3"
            target_file = f"downloads/{video_id}.{target_ext}"

            # Case 1: Telegram media link (e.g. https://t.me/ArcAPI_1/108)
            if "t.me/" in cdn:
                parts = cdn.rstrip("/").split("/")
                chat = parts[-2]
                msg_id = int(parts[-1])

                from anony import app, userbot
                msg = None
                client_to_use = None

                # Try userbot first if connected
                for ub in getattr(userbot, "clients", []):
                    if getattr(ub, "is_connected", False):
                        try:
                            msg = await ub.get_messages(chat, msg_id)
                            if msg and (msg.audio or msg.video or msg.document):
                                client_to_use = ub
                                break
                        except Exception:
                            continue

                # Fallback to app
                if not msg and getattr(app, "is_connected", False):
                    try:
                        msg = await app.get_messages(chat, msg_id)
                        if msg and (msg.audio or msg.video or msg.document):
                            client_to_use = app
                    except Exception:
                        pass

                if msg and client_to_use:
                    saved_path = await client_to_use.download_media(msg, file_name=target_file)
                    if saved_path and os.path.exists(saved_path) and os.path.getsize(saved_path) > 1024:
                        return saved_path

            # Case 2: Direct HTTP streaming CDN link
            elif cdn.startswith("http"):
                dl_timeout = aiohttp.ClientTimeout(
                    connect=10,
                    sock_read=60,
                    total=360,
                )
                async with aiohttp.ClientSession(timeout=dl_timeout) as dl_session:
                    async with dl_session.get(cdn) as dl_resp:
                        if dl_resp.status == 200:
                            with open(target_file, "wb") as f:
                                async for chunk in dl_resp.content.iter_chunked(1024 * 1024):
                                    f.write(chunk)
                            if os.path.exists(target_file) and os.path.getsize(target_file) > 1024:
                                return target_file

        except Exception as e:
            logger.warning(f"Arc API download error for {video_id}: {e}")

        return None

    async def download(self, video_id: str, video: bool = False) -> str | None:
        # Check cache first
        for c_ext in (["mp4"] if video else ["webm", "mp3", "m4a"]):
            fn = f"downloads/{video_id}.{c_ext}"
            if Path(fn).exists() and Path(fn).stat().st_size > 1024:
                return fn

        # Try Arc API first
        if getattr(config, "ARC_API_KEY", None):
            arc_file = await self._arc_download(video_id, video)
            if arc_file:
                return arc_file

        # Fallback to direct yt-dlp
        logger.info(f"Using yt-dlp fallback download for {video_id}")
        url = self.base + video_id
        ext = "mp4" if video else "webm"
        filename = f"downloads/{video_id}.{ext}"

        cookie = self.get_cookies()
        base_opts = {
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "logger": DummyLogger(),
            "nocheckcertificate": True,
            "cookiefile": cookie,
            "remote_components": ["ejs:github"],
        }

        if video:
            ydl_opts = {
                **base_opts,
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
                "merge_output_format": "mp4",
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio[ext=webm][acodec=opus]",
            }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError):
                    return None
                except Exception as ex:
                    logger.warning("Download failed: %s", ex)
                    return None
            return filename

        return await asyncio.to_thread(_download)
