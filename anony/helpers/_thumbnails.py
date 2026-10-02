# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import math
import os
import re
import aiohttp
from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
)

from anony import config, logger
from anony.helpers import Track


def draw_star_outline(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    r_outer: float,
    r_inner: float,
    outline_color: tuple,
    width: int = 2,
):
    points = []
    cx, cy = center
    for i in range(10):
        r = r_outer if i % 2 == 0 else r_inner
        angle = i * math.pi / 5 - math.pi / 2
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    for i in range(len(points)):
        p1 = points[i]
        p2 = points[(i + 1) % len(points)]
        draw.line([p1, p2], fill=outline_color, width=width)


def draw_airplay(draw: ImageDraw.ImageDraw, center: tuple[int, int], color: tuple):
    cx, cy = center
    # Upward solid triangle
    tri_h = 12
    tri_w = 16
    tri_points = [
        (cx, cy - 2),
        (cx - tri_w // 2, cy + tri_h - 2),
        (cx + tri_w // 2, cy + tri_h - 2),
    ]
    draw.polygon(tri_points, fill=color)

    # Concentric wave rings radiating around the top of the triangle
    r1 = 12
    draw.arc(
        (cx - r1, cy - r1 - 2, cx + r1, cy + r1 - 2),
        start=135,
        end=405,
        fill=color,
        width=2,
    )
    r2 = 18
    draw.arc(
        (cx - r2, cy - r2 - 2, cx + r2, cy + r2 - 2),
        start=140,
        end=400,
        fill=color,
        width=2,
    )


def draw_lyrics(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    color: tuple,
    font: ImageFont.FreeTypeFont,
):
    cx, cy = center
    w, h = 28, 22
    x1, y1 = cx - w // 2, cy - h // 2
    x2, y2 = cx + w // 2, cy + h // 2
    # Bubble outline
    draw.rounded_rectangle((x1, y1, x2, y2), radius=6, outline=color, width=2)
    # Pointer tail at bottom left
    draw.polygon([(x1 + 4, y2), (x1, y2 + 6), (x1 + 10, y2)], fill=color)
    # Double quote marks inside
    draw.text((cx - 8, cy - 11), "”", font=font, fill=color)
    draw.text((cx - 2, cy - 11), "”", font=font, fill=color)


def draw_queue(draw: ImageDraw.ImageDraw, center: tuple[int, int], color: tuple):
    cx, cy = center
    for dy in (-7, 0, 7):
        # Bullet dot
        draw.ellipse((cx - 14, cy + dy - 2, cx - 10, cy + dy + 2), fill=color)
        # Horizontal line
        draw.rounded_rectangle(
            (cx - 6, cy + dy - 1.5, cx + 14, cy + dy + 1.5),
            radius=1,
            fill=color,
        )


def draw_speaker_left(draw: ImageDraw.ImageDraw, pos: tuple[int, int], color: tuple):
    x, y = pos
    draw.rounded_rectangle((x, y - 4, x + 4, y + 4), radius=1, fill=color)
    draw.polygon(
        [(x + 4, y - 4), (x + 10, y - 8), (x + 10, y + 8), (x + 4, y + 4)],
        fill=color,
    )


def draw_speaker_right(draw: ImageDraw.ImageDraw, pos: tuple[int, int], color: tuple):
    x, y = pos
    draw.rounded_rectangle((x, y - 4, x + 4, y + 4), radius=1, fill=color)
    draw.polygon(
        [(x + 4, y - 4), (x + 10, y - 8), (x + 10, y + 8), (x + 4, y + 4)],
        fill=color,
    )
    draw.arc(
        (x + 8, y - 6, x + 16, y + 6),
        start=-60,
        end=60,
        fill=color,
        width=2,
    )
    draw.arc(
        (x + 11, y - 10, x + 22, y + 10),
        start=-60,
        end=60,
        fill=color,
        width=2,
    )


def draw_player_controls(draw: ImageDraw.ImageDraw, cx: int, cy: int):
    # Rewind << (two touching triangles pointing left)
    rw_x = cx - 120
    tri_w = 18
    tri_h = 16
    draw.polygon(
        [(rw_x, cy), (rw_x + tri_w, cy - tri_h), (rw_x + tri_w, cy + tri_h)],
        fill=(255, 255, 255, 255),
    )
    draw.polygon(
        [(rw_x - tri_w, cy), (rw_x, cy - tri_h), (rw_x, cy + tri_h)],
        fill=(255, 255, 255, 255),
    )

    # Pause || (Two solid vertical rounded bars)
    bar_w = 11
    bar_gap = 12
    bar_h = 44
    top_p = cy - bar_h // 2
    bot_p = cy + bar_h // 2
    draw.rounded_rectangle(
        (cx - bar_gap // 2 - bar_w, top_p, cx - bar_gap // 2, bot_p),
        radius=4,
        fill=(255, 255, 255, 255),
    )
    draw.rounded_rectangle(
        (cx + bar_gap // 2, top_p, cx + bar_gap // 2 + bar_w, bot_p),
        radius=4,
        fill=(255, 255, 255, 255),
    )

    # Fast-Forward >> (two touching triangles pointing right)
    ff_x = cx + 120
    draw.polygon(
        [(ff_x, cy), (ff_x - tri_w, cy - tri_h), (ff_x - tri_w, cy + tri_h)],
        fill=(255, 255, 255, 255),
    )
    draw.polygon(
        [(ff_x + tri_w, cy), (ff_x, cy - tri_h), (ff_x, cy + tri_h)],
        fill=(255, 255, 255, 255),
    )


def clean_display_text(text: str) -> str:
    if not text:
        return ""
    # Filter out characters outside BMP that cause missing glyph boxes
    chars = [
        c
        for c in text
        if ord(c) <= 0x052F
        or (0x0900 <= ord(c) <= 0x097F)
        or ord(c) in (8211, 8212, 8216, 8217, 8220, 8221, 8230)
    ]
    return re.sub(r"\s+", " ", "".join(chars)).strip()


class Thumbnail:
    def __init__(self):
        bold_font_path = "anony/helpers/Raleway-Bold.ttf"
        light_font_path = "anony/helpers/Inter-Light.ttf"

        self.font_title = ImageFont.truetype(bold_font_path, 44)
        self.font_artist = ImageFont.truetype(light_font_path, 25)
        self.font_time = ImageFont.truetype(light_font_path, 20)
        self.font_quote = ImageFont.truetype(bold_font_path, 16)
        self.session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def save_thumb(self, output_path: str, url: str) -> str:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        async with self.session.get(url) as resp:
            with open(output_path, "wb") as f:
                f.write(await resp.read())
        return output_path

    async def generate(self, song: Track, size=(1280, 720)) -> str:
        try:
            os.makedirs("cache", exist_ok=True)
            temp = f"cache/temp_{song.id}.bin"
            output = f"cache/{song.id}.png"
            if os.path.exists(output):
                return output

            # 1. Download original thumbnail
            await self.save_thumb(temp, song.thumbnail)
            raw_img = Image.open(temp).convert("RGBA")

            # 2. Background: blurred & darkened
            bg = ImageOps.fit(raw_img, size, method=Image.Resampling.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(40))
            bg = ImageEnhance.Brightness(bg).enhance(0.40)

            # Dark subtle vignette overlay
            dark_overlay = Image.new("RGBA", size, (0, 0, 0, 80))
            bg = Image.alpha_composite(bg, dark_overlay)

            # 3. Album Cover (Square card with rounded corners)
            cover_size = (480, 480)
            cover_pos = (110, 120)
            cover_radius = 38

            cover = ImageOps.fit(
                raw_img,
                cover_size,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            mask = Image.new("L", cover_size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, cover_size[0], cover_size[1]),
                radius=cover_radius,
                fill=255,
            )
            cover.putalpha(mask)

            # Soft shadow for album card
            shadow_layer = Image.new("RGBA", size, (0, 0, 0, 0))
            shadow_mask = Image.new("L", cover_size, 0)
            ImageDraw.Draw(shadow_mask).rounded_rectangle(
                (0, 0, cover_size[0], cover_size[1]),
                radius=cover_radius,
                fill=220,
            )
            shadow_layer.paste(
                (0, 0, 0, 180),
                (cover_pos[0] + 6, cover_pos[1] + 10),
                shadow_mask,
            )
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(22))
            bg = Image.alpha_composite(bg, shadow_layer)

            # Paste album cover
            bg.paste(cover, cover_pos, cover)

            # 4. Transparent overlay layer for clean alpha blending
            overlay = Image.new("RGBA", size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            x_start = 710
            x_end = 1175

            # Title
            max_title_w = 345
            display_title = clean_display_text(song.title) or (song.title or "Unknown Title")
            if draw.textlength(display_title, font=self.font_title) > max_title_w:
                while (
                    len(display_title) > 3
                    and draw.textlength(display_title + "...", font=self.font_title)
                    > max_title_w
                ):
                    display_title = display_title[:-1]
                display_title += "..."
            draw.text(
                (x_start, 126),
                display_title,
                font=self.font_title,
                fill=(255, 255, 255, 255),
            )

            # Top Right Buttons: Star Outline & More (...)
            # Star button
            star_cx, star_cy = 1090, 150
            draw.ellipse(
                (star_cx - 18, star_cy - 18, star_cx + 18, star_cy + 18),
                fill=(255, 255, 255, 38),
            )
            draw_star_outline(
                draw,
                (star_cx, star_cy),
                10,
                4.5,
                (255, 255, 255, 230),
                width=2,
            )

            # More (...) button
            more_cx, more_cy = 1145, 150
            draw.ellipse(
                (more_cx - 18, more_cy - 18, more_cx + 18, more_cy + 18),
                fill=(255, 255, 255, 38),
            )
            for dx in (-6, 0, 6):
                draw.ellipse(
                    (more_cx + dx - 2, more_cy - 2, more_cx + dx + 2, more_cy + 2),
                    fill=(255, 255, 255, 240),
                )

            # Artist / Channel
            display_artist = clean_display_text(song.channel_name) or (
                song.channel_name or "Unknown Artist"
            )
            max_artist_w = 460
            if draw.textlength(display_artist, font=self.font_artist) > max_artist_w:
                while (
                    len(display_artist) > 3
                    and draw.textlength(display_artist + "...", font=self.font_artist)
                    > max_artist_w
                ):
                    display_artist = display_artist[:-1]
                display_artist += "..."
            draw.text(
                (x_start, 188),
                display_artist,
                font=self.font_artist,
                fill=(205, 205, 215, 220),
            )

            # Progress Bar
            bar_y = 250
            bar_w = x_end - x_start
            bar_h = 6
            # Track background
            draw.rounded_rectangle(
                (x_start, bar_y, x_end, bar_y + bar_h),
                radius=3,
                fill=(255, 255, 255, 60),
            )
            # Played portion (~36%)
            fill_w = int(bar_w * 0.36)
            draw.rounded_rectangle(
                (x_start, bar_y, x_start + fill_w, bar_y + bar_h),
                radius=3,
                fill=(255, 255, 255, 255),
            )

            # Timers
            draw.text(
                (x_start, bar_y + 14),
                "0:10",
                font=self.font_time,
                fill=(200, 200, 210, 210),
            )
            duration_str = song.duration or "03:00"
            dur_w = draw.textlength(duration_str, font=self.font_time)
            draw.text(
                (x_end - dur_w, bar_y + 14),
                duration_str,
                font=self.font_time,
                fill=(200, 200, 210, 210),
            )

            # Playback Controls (Vertically centered at y = 390)
            ctrl_cx = (x_start + x_end) // 2
            ctrl_cy = 390
            draw_player_controls(draw, ctrl_cx, ctrl_cy)

            # Volume Slider (at y = 515)
            vol_y = 515
            draw_speaker_left(draw, (x_start, vol_y), (200, 200, 210, 210))
            vol_bar_x1 = x_start + 24
            vol_bar_x2 = x_end - 28
            draw.rounded_rectangle(
                (vol_bar_x1, vol_y - 2, vol_bar_x2, vol_y + 3),
                radius=3,
                fill=(255, 255, 255, 60),
            )
            vol_fill = int((vol_bar_x2 - vol_bar_x1) * 0.58)
            draw.rounded_rectangle(
                (vol_bar_x1, vol_y - 2, vol_bar_x1 + vol_fill, vol_y + 3),
                radius=3,
                fill=(255, 255, 255, 255),
            )
            draw_speaker_right(draw, (x_end - 16, vol_y), (200, 200, 210, 210))

            # Bottom Action Row (at y = 615)
            bot_y = 615
            sec_w = (x_end - x_start) // 3
            draw_lyrics(
                draw,
                (x_start + sec_w // 2, bot_y),
                (200, 200, 210, 210),
                self.font_quote,
            )
            draw_airplay(
                draw,
                (x_start + sec_w + sec_w // 2, bot_y),
                (200, 200, 210, 210),
            )
            draw_queue(
                draw,
                (x_start + sec_w * 2 + sec_w // 2, bot_y),
                (200, 200, 210, 210),
            )

            # Composite and save
            bg = Image.alpha_composite(bg, overlay)
            bg.convert("RGB").save(output, "PNG")

            try:
                os.remove(temp)
            except Exception:
                pass
            return output
        except Exception as ex:
            logger.error(f"Failed to generate thumbnail: {ex}")
            return config.DEFAULT_THUMB
