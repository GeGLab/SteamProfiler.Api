"""A shareable 1600 px comparison card. Asset loading is bounded and optional.

The PNG is independent of the chat app's theme. Pillow supplies Unicode font
rendering, image decoding and antialiasing; Inter travels with its OFL license.
"""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

import art

WIDTH, HEIGHT = 1600, 1390
FONT = Path(__file__).parent / "assets" / "fonts" / "Inter.ttf"
BG = (10, 16, 29)
PANEL = (19, 28, 46)
LINE = (43, 55, 77)
WHITE = (244, 247, 255)
MUTED = (152, 166, 189)
LEFT = (177, 160, 255)
RIGHT = (80, 225, 204)
GOLD = (246, 211, 139)

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
def _font(size, weight=400):
    font = ImageFont.truetype(str(FONT), size)
    font.set_variation_by_axes([32, weight])
    return font


def _fit(draw, value, size, weight, width):
    value = " ".join(str(value or "?").split())
    font = _font(size, weight)
    if draw.textlength(value, font=font) <= width:
        return value
    while value and draw.textlength(value + "…", font=font) > width:
        value = value[:-1]
    return value.rstrip() + "…"


def _text(draw, value, xy, size=24, weight=400, colour=WHITE, width=None):
    if width is not None:
        value = _fit(draw, value, size, weight, width)
    draw.text(xy, str(value), font=_font(size, weight), fill=colour, anchor="lt")


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
    for game in games[:6]:
        if str(game["appid"]).isdigit():
            tasks[f"game:{game['appid']}"] = (art.thumb, int(game["appid"]))
    results = {}
    # At most two avatars and six cached Steam capsules, with art.py's host
    # allowlists, byte limits and timeouts. Asset failures never fail the card.
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {key: pool.submit(function, argument) for key, (function, argument) in tasks.items()}
        for key, future in futures.items():
            try:
                results[key] = future.result()
            except Exception:
                results[key] = None
    return results


def render(first, second, locale="pt-BR", assets=None):
    lang = "pt" if str(locale).lower().startswith("pt") else "en"
    words = TEXT[lang]
    data = comparison(first, second)
    assets = load_assets(first, second, data["games"]) if assets is None else assets
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(canvas)
    # Quiet blue-violet atmosphere, with no dependency on a community's palette.
    for y in range(HEIGHT):
        t = y / HEIGHT
        colour = tuple(round(a * (1 - t) + b * t) for a, b in zip((18, 25, 48), BG))
        draw.line((0, y, WIDTH, y), fill=colour)
    for x in range(64, WIDTH, 48):
        for y in range(28, 172, 48):
            draw.ellipse((x, y, x + 2, y + 2), fill=(47, 56, 81))
    draw.rounded_rectangle((64, 51, 96, 83), radius=10, fill=LEFT)
    draw.line((73, 69, 80, 62, 88, 70), fill=BG, width=3)
    draw.ellipse((83, 58, 91, 66), outline=BG, width=2)
    _text(draw, "STEAMPROFILER", (110, 56), 22, 750)
    _text(draw, words["tag"], (1160, 60), 17, 650, MUTED, width=365)
    _text(draw, words["title"], (64, 111), 48, 730, width=1465)
    _text(draw, words["sub"], (66, 174), 24, 400, MUTED)

    names = []
    for index, (profile, accent, x) in enumerate(((first, LEFT, 64), (second, RIGHT, 828))):
        info = profile.get("profile") or {}
        name = str(info.get("persona") or "Player")
        names.append(name)
        draw.rounded_rectangle((x, 237, x + 708, 535), radius=26, fill=PANEL, outline=LINE, width=1)
        draw.rounded_rectangle((x + 26, 264, x + 32, 338), radius=3, fill=accent)
        avatar = _image(assets.get(f"avatar:{index}"), (96, 96))
        mask = Image.new("L", (96, 96), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 95, 95), radius=24, fill=255)
        if avatar:
            canvas.paste(avatar, (x + 52, 265), mask)
        else:
            draw.rounded_rectangle((x + 52, 265, x + 148, 361), radius=24, fill=accent)
            _text(draw, name[:1].upper(), (x + 82, 292), 42, 700, BG)
        _text(draw, name, (x + 174, 277), 32, 720, width=488)
        level = info.get("level")
        subtitle = f"{words['level']} {level}" if level is not None else "STEAM PLAYER"
        _text(draw, subtitle, (x + 176, 326), 18, 600, accent)
        draw.line((x + 52, 390, x + 656, 390), fill=LINE, width=1)
        available = data["available"][index]
        total_hours = (profile.get("totals") or {}).get("hours")
        owned = len(data["libraries"][index])
        _text(draw, _number(total_hours, lang) if available else "—", (x + 52, 415), 48, 700, accent)
        _text(draw, words["hours"], (x + 54, 481), 16, 600, MUTED)
        _text(draw, _number(owned, lang) if available else "—", (x + 396, 415), 48, 700)
        _text(draw, words["games"], (x + 398, 481), 16, 600, MUTED)
    draw.ellipse((768, 344, 832, 408), fill=BG, outline=LINE, width=2)
    _text(draw, "VS", (783, 367), 19, 750, MUTED)

    # Ownership overlap is measured separately against each person's library;
    # there is no invented compatibility score or winner for owning more games.
    draw.rounded_rectangle((64, 562, 1536, 750), radius=25, fill=(24, 35, 53), outline=(48, 65, 83), width=1)
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
            draw.rounded_rectangle((x + 14, y + 14, x + 130, y + 96), radius=10, fill=(32, 45, 69))
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
    _text(draw, "steamprofiler.org", (64, 1364), 17, 650, WHITE)
    _text(draw, words["public"], (580, 1364), 17, 400, MUTED, width=950)
    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()
