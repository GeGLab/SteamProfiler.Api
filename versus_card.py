"""A shareable 1600 px comparison card. Asset loading is bounded and optional.

The logo, palette and fonts come from SteamProfiler.Front/site. Pillow supplies
font rendering, image decoding and antialiasing; fonts retain their OFL licenses.
"""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path
import threading

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import art

WIDTH, HEIGHT = 1600, 1390
ASSETS = Path(__file__).parent / "assets"
FONTS = {"sans": "Archivo.ttf", "display": "BricolageGrotesque.ttf", "mono": "IBMPlexMono.ttf"}
BRAND_MARK = ASSETS / "brand" / "steamprofiler.png"
# SteamProfiler.Front/site/style.css: bg, panel, panel-2, line, text, dim, accent.
BG = (11, 10, 14)
PANEL = (19, 18, 25)
PANEL_2 = (26, 24, 34)
LINE = (40, 38, 49)
WHITE = (238, 236, 243)
MUTED = (142, 138, 155)
LEFT = (255, 180, 84)
RIGHT = WHITE
GOLD = LEFT
EXPORT_LOCK = threading.Lock()
MAX_EXPORT_BYTES = 8 * 1024 * 1024
FRAME_MS = 80
MAX_FRAMES = 36

TEXT = {
    "pt": {"tag": "COMPARAÇÃO DE PERFIS", "title": "O próximo jogo é melhor juntos.",
           "sub": "Dois perfis. Suas bibliotecas. Novas partidas em comum.", "hours": "HORAS JOGADAS",
           "games": "JOGOS NA BIBLIOTECA", "level": "NÍVEL", "common": "jogos em comum",
           "overlap": "DA BIBLIOTECA", "shared": "Terreno em comum", "shared_sub": "Os jogos que vocês dois têm — ordenados pelas horas dos dois perfis.",
           "none": "Nenhum jogo em comum por enquanto.", "private": "Biblioteca privada ou indisponível",
           "private_sub": "A comparação usa apenas dados públicos. Algumas estatísticas não estão disponíveis.",
           "more": "+{n} jogos em comum no SteamProfiler", "public": "Dados públicos da Steam · Horas individuais por perfil"},
    "en": {"tag": "PLAYER COMPARISON", "title": "Your next game is better together.",
           "sub": "Two profiles. Your libraries. More games to share.", "hours": "HOURS PLAYED",
           "games": "GAMES IN LIBRARY", "level": "LEVEL", "common": "games in common",
           "overlap": "OF THE LIBRARY", "shared": "Common ground", "shared_sub": "Games you both own — ranked by playtime across both profiles.",
           "none": "No shared games just yet.", "private": "Private or unavailable library",
           "private_sub": "Only public data is compared. Some statistics are unavailable.",
           "more": "+{n} more shared games on SteamProfiler", "public": "Public Steam data · Individual playtime per profile"},
}


def _number(value, lang, decimals=False):
    value = _amount(value)
    result = f"{value:,.1f}" if decimals and 0 < value < 100 else f"{round(value):,}"
    return result.replace(",", "_").replace(".", ",").replace("_", ".") if lang == "pt" else result


def _hours(value, lang):
    return f"{_number(value, lang, decimals=True)} h"


def _amount(value):
    try:
        value = float(value or 0)
        return max(0, value) if math.isfinite(value) else 0
    except (TypeError, ValueError):
        return 0


@lru_cache(maxsize=72)
def _font(size, weight=400, family="sans"):
    font = ImageFont.truetype(str(ASSETS / "fonts" / FONTS[family]), size)
    try:
        axes = font.get_variation_axes()
        font.set_variation_by_axes([
            min(axis["maximum"], max(axis["minimum"], weight if b"Weight" in axis["name"] else size if b"Optical" in axis["name"] else axis["default"]))
            for axis in axes
        ])
    except OSError:
        pass  # IBM Plex Mono is a static font.
    return font


def _fit(draw, value, size, weight, width, family):
    value = " ".join(str(value or "?").split())
    font = _font(size, weight, family)
    if draw.textlength(value, font=font) <= width:
        return value
    while value and draw.textlength(value + "…", font=font) > width:
        value = value[:-1]
    return value.rstrip() + "…"


def _text(draw, value, xy, size=24, weight=400, colour=WHITE, width=None, family=None):
    family = family or ("display" if size >= 34 else "sans")
    if width is not None:
        value = _fit(draw, value, size, weight, width, family)
    draw.text(xy, str(value), font=_font(size, weight, family), fill=colour, anchor="lt")


def _image(body, size):
    if not body:
        return None
    try:
        with Image.open(BytesIO(body)) as source:
            if source.width * source.height > 24_000_000:
                return None
            return ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def comparison(first, second):
    """Shared ownership, with missing/private libraries kept distinct from empty ones."""
    libraries = [profile.get("library") for profile in (first, second)]
    available = [isinstance(library, list) for library in libraries]
    maps = [{str(game["appid"]): game for game in (profile.get("unplayed") or []) + (library or []) if isinstance(game, dict) and game.get("appid")} for profile, library in zip((first, second), libraries)]
    shared = set(maps[0]) & set(maps[1])
    games = []
    for appid in shared:
        a, b = maps[0][appid], maps[1][appid]
        games.append({"appid": appid, "name": a.get("name") or b.get("name") or appid,
                      "left": _amount(a.get("hours")), "right": _amount(b.get("hours"))})
    # Prioritize games both have played before the high-hour game only one has opened.
    games.sort(key=lambda game: (min(game["left"], game["right"]) > 0, game["left"] + game["right"], game["name"]), reverse=True)
    return {"available": available, "libraries": maps, "games": games, "common": len(shared)}


def load_assets(first, second, games):
    tasks = {}
    for index, profile in enumerate((first, second)):
        url = (profile.get("profile") or {}).get("avatar")
        if url:
            tasks[f"avatar:{index}"] = (art.avatar, url)
        items = (profile.get("profile") or {}).get("items") or {}
        background = items.get("background") or items.get("mini") or {}
        if background.get("image_large"):
            tasks[f"background:{index}"] = (art.profile_media, background["image_large"])
        for kind in ("avatar", "frame"):
            item = items.get(kind) or {}
            url = item.get("image_small") or item.get("image_large")
            if url:
                tasks[f"{kind}-motion:{index}"] = (art.profile_media, url)
    for game in games[:6]:
        if str(game["appid"]).isdigit():
            tasks[f"game:{game['appid']}"] = (art.thumb, int(game["appid"]))
    results = {}
    # Optional Steam assets share strict host/byte/time limits. Failures never
    # fail the card, and the pool bounds simultaneous CDN connections.
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {key: pool.submit(function, argument) for key, (function, argument) in tasks.items()}
        for key, future in futures.items():
            try:
                results[key] = future.result()
            except Exception:
                results[key] = None
    return results


def _canvas(first, second, locale, assets):
    lang = "pt" if str(locale).lower().startswith("pt") else "en"
    words = TEXT[lang]
    data = comparison(first, second)
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    for index, x in enumerate((0, 800)):
        background = _image(assets.get(f"background:{index}"), (800, 760))
        if background:
            background = background.filter(ImageFilter.GaussianBlur(18))
            fade = Image.new("L", (1, 760))
            fade.putdata([round(42 * (1 - y / 759) ** 1.4) for y in range(760)])
            canvas.paste(background, (x, 0), fade.resize((800, 760)))
    draw = ImageDraw.Draw(canvas)
    for x in range(64, WIDTH, 48):
        for y in range(28, 172, 48):
            draw.ellipse((x, y, x + 2, y + 2), fill=LINE)
    with Image.open(BRAND_MARK) as mark:
        canvas.paste(mark.convert("RGB").resize((48, 48), Image.Resampling.LANCZOS), (64, 44))
    _text(draw, "steamprofiler", (128, 58), 25, 600, family="mono")
    end = 128 + draw.textlength("steamprofiler", font=_font(25, 600, "mono"))
    _text(draw, ".org", (end, 58), 25, 400, MUTED, family="mono")
    _text(draw, words["tag"], (1160, 60), 17, 600, MUTED, width=365, family="mono")
    _text(draw, words["title"], (64, 111), 48, 730, width=1465)
    _text(draw, words["sub"], (66, 174), 24, 400, MUTED)

    names = []
    for index, (profile, accent, x) in enumerate(((first, LEFT, 64), (second, RIGHT, 828))):
        info = profile.get("profile") or {}
        name = str(info.get("persona") or "Player")
        names.append(name)
        draw.rounded_rectangle((x, 237, x + 708, 535), radius=26, fill=PANEL, outline=LINE, width=1)
        background = _image(assets.get(f"background:{index}"), (706, 296))
        if background:
            shade = Image.new("L", (1, 296))
            shade.putdata([round(108 - 78 * y / 295) for y in range(296)])
            panel = Image.new("RGB", background.size, PANEL)
            panel.paste(background, (0, 0), shade.resize(background.size))
            mask = Image.new("L", background.size)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 705, 295), radius=25, fill=255)
            canvas.paste(panel, (x + 1, 238), mask)
        draw.rounded_rectangle((x + 26, 264, x + 32, 338), radius=3, fill=accent)
        draw.rounded_rectangle((x + 52, 265, x + 148, 361), radius=24, fill=accent)
        _text(draw, name[:1].upper(), (x + 82, 292), 42, 700, BG)
        _text(draw, name, (x + 174, 277), 32, 720, width=488)
        level = info.get("level")
        subtitle = f"{words['level']} {level}" if level is not None else "STEAM PLAYER"
        _text(draw, subtitle, (x + 176, 326), 18, 600, accent, family="mono")
        draw.line((x + 52, 390, x + 656, 390), fill=LINE, width=1)
        available = data["available"][index]
        total_hours = (profile.get("totals") or {}).get("hours")
        owned = len(data["libraries"][index])
        _text(draw, _number(total_hours, lang) if available else "—", (x + 52, 415), 48, 700, accent)
        _text(draw, words["hours"], (x + 54, 481), 16, 500, MUTED, family="mono")
        _text(draw, _number(owned, lang) if available else "—", (x + 396, 415), 48, 700)
        _text(draw, words["games"], (x + 398, 481), 16, 500, MUTED, family="mono")
    draw.ellipse((768, 344, 832, 408), fill=BG, outline=LINE, width=2)
    _text(draw, "VS", (783, 367), 19, 750, MUTED)

    # Ownership overlap is measured separately against each person's library;
    # there is no invented compatibility score or winner for owning more games.
    draw.rounded_rectangle((64, 562, 1536, 750), radius=25, fill=PANEL_2, outline=LINE, width=1)
    draw.ellipse((105, 613, 166, 674), outline=LEFT, width=5)
    draw.ellipse((141, 613, 202, 674), outline=RIGHT, width=5)
    public = all(data["available"])
    _text(draw, str(data["common"]) if public else "—", (232, 587), 76, 700, GOLD)
    _text(draw, words["common"], (234, 679), 23, 550)
    for index, (name, accent) in enumerate(zip(names, (LEFT, RIGHT))):
        x = 650 + index * 426
        owned = len(data["libraries"][index])
        percent = round(100 * data["common"] / owned) if owned and public else 0
        _text(draw, name, (x, 603), 21, 600, width=326)
        _text(draw, f"{percent}% {words['overlap']}" if public else "—", (x, 645), 16, 550, MUTED)
        draw.rounded_rectangle((x, 685, x + 358, 696), radius=5, fill=LINE)
        if percent:
            draw.rounded_rectangle((x, 685, x + max(11, 358 * percent / 100), 696), radius=5, fill=accent)
    _text(draw, words["shared"], (64, 800), 34, 700)
    _text(draw, words["shared_sub"] if public else words["private_sub"], (66, 851), 22, 400, MUTED, width=1460)
    if not data["games"]:
        draw.rounded_rectangle((64, 911, 1536, 1221), radius=24, outline=LINE, width=1, fill=PANEL)
        _text(draw, words["none"] if public else words["private"], (112, 1047), 32, 600, MUTED, width=1360)
    for index, game in enumerate(data["games"][:6]):
        x, y = 64 + (index % 2) * 764, 908 + (index // 2) * 126
        draw.rounded_rectangle((x, y, x + 708, y + 110), radius=18, fill=PANEL, outline=LINE, width=1)
        capsule = _image(assets.get(f"game:{game['appid']}"), (116, 82))
        if capsule:
            mask = Image.new("L", (116, 82), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 115, 81), radius=10, fill=255)
            canvas.paste(capsule, (x + 14, y + 14), mask)
        else:
            draw.rounded_rectangle((x + 14, y + 14, x + 130, y + 96), radius=10, fill=PANEL_2)
            _text(draw, f"{index + 1:02}", (x + 50, y + 41), 24, 650, MUTED)
        _text(draw, game["name"], (x + 151, y + 19), 23, 650, width=530)
        _text(draw, _hours(game["left"], lang), (x + 153, y + 58), 21, 650, LEFT)
        right = _hours(game["right"], lang)
        _text(draw, right, (x + 680 - draw.textlength(right, font=_font(21, 650)), y + 58), 21, 650, RIGHT)
        total = game["left"] + game["right"]
        draw.rounded_rectangle((x + 153, y + 91, x + 681, y + 96), radius=2, fill=LINE)
        if total:
            middle = x + 153 + 528 * game["left"] / total
            if game["left"]:
                draw.line((x + 154, y + 94, middle, y + 94), fill=LEFT, width=5)
            if game["right"]:
                draw.line((middle, y + 94, x + 680, y + 94), fill=RIGHT, width=5)
    if data["common"] > 6:
        _text(draw, words["more"].format(n=data["common"] - 6), (66, 1306), 20, 500, MUTED)
    draw.line((64, 1345, 1536, 1345), fill=LINE)
    _text(draw, "steamprofiler.org", (64, 1364), 17, 600, WHITE, family="mono")
    _text(draw, words["public"], (580, 1364), 17, 400, MUTED, width=950)
    return canvas


def _sequence(body, size):
    """Decode small timed portraits; bound both source work and retained pixels."""
    if not body or len(body) > art.MAX_MEDIA_BYTES:
        return []
    try:
        with Image.open(BytesIO(body)) as source:
            count = getattr(source, "n_frames", 1)
            pixels = source.width * source.height
            if pixels > 4_000_000 or pixels * count > 32_000_000 or count > 240:
                return []
            start = 1 if source.info.get("default_image") else 0
            frames, elapsed = [], 0
            for index in range(start, count):
                source.seek(index)
                duration = min(1000, max(20, float(source.info.get("duration", 100))))
                frame = ImageOps.fit(source.convert("RGBA"), size, method=Image.Resampling.LANCZOS)
                elapsed += duration
                frames.append((elapsed, frame))
                if elapsed >= MAX_FRAMES * FRAME_MS:
                    break
            return frames
    except (OSError, ValueError, EOFError, Image.DecompressionBombError):
        return []


def _portraits(assets):
    portraits = []
    for index, x in enumerate((64, 828)):
        avatar = _sequence(assets.get(f"avatar-motion:{index}"), (96, 96))
        avatar = avatar or _sequence(assets.get(f"avatar:{index}"), (96, 96))
        if avatar:
            mask = Image.new("L", (96, 96))
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 95, 95), radius=24, fill=255)
            for _, frame in avatar:
                frame.putalpha(Image.composite(frame.getchannel("A"), Image.new("L", frame.size), mask))
            portraits.append(((x + 52, 265), avatar))
        frame = _sequence(assets.get(f"frame-motion:{index}"), (128, 128))
        if frame:
            portraits.append(((x + 36, 249), frame))
    return portraits


def _at_time(canvas, portraits, time_ms):
    result = canvas.copy()
    for position, frames in portraits:
        moment = time_ms % frames[-1][0]
        image = next(frame for end, frame in frames if moment < end)
        result.paste(image, position, image)
    return result


def render(first, second, locale="pt-BR", assets=None, animated=False):
    assets = load_assets(first, second, comparison(first, second)["games"]) if assets is None else assets
    canvas = _canvas(first, second, locale, assets)
    portraits = _portraits(assets)
    poster = _at_time(canvas, portraits, 0)
    output = BytesIO()
    if not animated:
        poster.save(output, format="PNG", optimize=True)
        return output.getvalue()
    duration = max((frames[-1][0] for _, frames in portraits if len(frames) > 1), default=0)
    count = min(MAX_FRAMES, math.ceil(duration / FRAME_MS))
    frames = [_at_time(canvas, portraits, index * FRAME_MS) for index in range(1, count)]
    poster.save(output, format="WEBP", save_all=bool(frames), append_images=frames,
                duration=FRAME_MS, loop=0, quality=88, method=2)
    if output.tell() > MAX_EXPORT_BYTES:
        output = BytesIO()
        poster.save(output, format="WEBP", quality=85, method=2)
    return output.getvalue()
