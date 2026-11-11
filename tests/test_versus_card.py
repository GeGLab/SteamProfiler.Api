import io
import unittest
from unittest.mock import patch

from PIL import Image

import api
import art
import versus_card

A = {"profile": {"persona": "Gordziilla · A", "level": 24}, "totals": {"hours": 15000},
     "library": [{"appid": 730, "name": "Counter-Strike 2", "hours": 100},
                 {"appid": 570, "name": "Dota 2", "hours": 500}],
     "unplayed": [{"appid": 620, "name": "Portal 2"}]}
B = {"profile": {"persona": "Ana <&> / Very long name " * 8}, "totals": {"hours": 900},
     "library": [{"appid": 730, "name": "Counter-Strike 2", "hours": 50},
                 {"appid": 570, "name": "Dota 2", "hours": 0},
                 {"appid": 620, "name": "Portal 2", "hours": 10}]}


class VersusCardTest(unittest.TestCase):
    @staticmethod
    def animation():
        output = io.BytesIO()
        Image.new("RGBA", (32, 32), "red").save(
            output, format="PNG", save_all=True,
            append_images=[Image.new("RGBA", (32, 32), "blue")],
            duration=[80, 160], loop=0)
        return output.getvalue()

    def test_animation_preserves_timing_and_changes_avatar_without_changing_brand(self):
        content = versus_card.render(A, B, assets={"avatar-motion:0": self.animation()}, animated=True)
        with Image.open(io.BytesIO(content)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertTrue(image.is_animated)
            self.assertEqual(image.size, (1600, 1390))
            image.seek(0)
            first = image.convert("RGB")
            image.seek(1)
            second = image.convert("RGB")
            self.assertGreater(first.getpixel((150, 310))[0], 200)
            self.assertGreater(second.getpixel((150, 310))[2], 200)
            self.assertEqual(first.getpixel((76, 68)), second.getpixel((76, 68)))
        sequence = versus_card._sequence(self.animation(), (96, 96))
        self.assertEqual([end for end, _ in sequence], [80, 240])
        self.assertLess(len(content), versus_card.MAX_EXPORT_BYTES)

    def test_background_and_transparent_frame_are_composited_and_bad_motion_falls_back(self):
        background = io.BytesIO()
        Image.new("RGB", (64, 64), "red").save(background, format="PNG")
        frame = io.BytesIO()
        Image.new("RGBA", (128, 128), (0, 0, 0, 0)).save(frame, format="PNG")
        assets = {"background:0": background.getvalue(), "avatar-motion:0": b"broken",
                  "avatar:0": self.animation(), "frame-motion:0": frame.getvalue()}
        with Image.open(io.BytesIO(versus_card.render(A, B, assets=assets))) as image:
            red, green, _ = image.getpixel((600, 300))
            self.assertGreater(red, green + 50)
            self.assertGreater(image.getpixel((150, 310))[0], 200)
        still = versus_card.render(A, B, assets={}, animated=True)
        with Image.open(io.BytesIO(still)) as image:
            self.assertEqual(getattr(image, "n_frames", 1), 1)

    def test_oversized_source_and_non_steam_media_are_rejected(self):
        output = io.BytesIO()
        Image.new("RGB", (2100, 2000)).save(output, format="PNG")
        self.assertEqual(versus_card._sequence(output.getvalue(), (96, 96)), [])
        with patch.object(art.urllib.request, "build_opener") as opener:
            for url in ("https://example.com/a.gif", "http://cdn.cloudflare.steamstatic.com/a.gif",
                        "https://user@cdn.cloudflare.steamstatic.com/a.gif",
                        "https://cdn.cloudflare.steamstatic.com:8443/a.gif"):
                self.assertIsNone(art.profile_media(url))
            opener.assert_not_called()

    def test_ownership_includes_unplayed_and_prioritizes_games_both_have_played(self):
        data = versus_card.comparison(A, B)
        self.assertEqual(data["common"], 3)
        self.assertEqual(data["games"][0]["appid"], "730")
        self.assertEqual(len(data["libraries"][0]), 3)
        self.assertEqual(next(g for g in data["games"] if g["appid"] == "620")["left"], 0)

    def test_png_is_shareable_large_and_handles_long_unicode_names_without_upstream_images(self):
        for locale in ("pt-BR", "en", "es"):
            content = versus_card.render(A, B, locale, assets={})
            with Image.open(io.BytesIO(content)) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (1600, 1390))
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.getpixel((0, 800)), (11, 10, 14))
                self.assertEqual(image.getpixel((76, 68)), (255, 180, 84))
            self.assertLess(len(content), 8 * 1024 * 1024)

    def test_private_empty_and_bad_optional_images_still_draw(self):
        for profile in ({"profile": {"persona": "Private"}}, {"library": [], "profile": {}}, {"library": [{"appid": 1, "hours": float("nan")}]}):
            content = versus_card.render(A, profile, assets={"avatar:0": b"not an image"})
            self.assertTrue(content.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(versus_card.comparison(A, {})["available"], [True, False])

    @staticmethod
    def handler():
        handler = object.__new__(api.Handler)
        handler.path = "/versus.png?q=alice&vs=bob&lang=pt-BR"
        handler.headers = {}
        handler.wfile = io.BytesIO()
        handler.status = None
        handler.sent_headers = {}
        handler.send_response = lambda status: setattr(handler, "status", status)
        handler.send_header = lambda name, value: handler.sent_headers.__setitem__(name, value)
        handler.end_headers = lambda: None
        handler.gate = lambda *args, **kwargs: None
        return handler

    def test_public_png_endpoint_draws_both_profiles_and_localizes(self):
        handler = self.handler()
        with patch.object(api, "do_resolve", side_effect=[{"steamid": "1"}, {"steamid": "2"}]), \
                patch.object(api, "do_profile", side_effect=[A, B]), \
                patch.object(api.blocks, "blocked", return_value=False), \
                patch.object(api, "cached", side_effect=lambda key, ttl, build: build()), \
                patch.object(api.versus_card, "render", return_value=b"png") as render:
            handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.sent_headers["Content-Type"], "image/png")
        render.assert_called_once_with(A, B, "pt", animated=False)

    def test_webp_encoding_does_not_hold_the_profile_cache_lock_and_returns_correct_type(self):
        handler = self.handler()
        handler.path = handler.path.replace(".png", ".webp")

        def encode(*args, **kwargs):
            self.assertTrue(api._lock.acquire(blocking=False))
            api._lock.release()
            return b"webp"

        with patch.object(api, "do_resolve", side_effect=[{"steamid": "1"}, {"steamid": "2"}]), \
                patch.object(api, "do_profile", side_effect=[A, B]), \
                patch.object(api.blocks, "blocked", return_value=False), \
                patch.object(api, "_cache", {}), \
                patch.object(api.versus_card, "render", side_effect=encode) as render:
            handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.sent_headers["Content-Type"], "image/webp")
        self.assertEqual(handler.wfile.getvalue(), b"webp")
        render.assert_called_once_with(A, B, "pt", animated=True)

    def test_blocked_profile_withdraws_the_card_before_rendering(self):
        handler = self.handler()
        with patch.object(api, "do_resolve", side_effect=[{"steamid": "1"}, {"steamid": "2"}]), \
                patch.object(api, "do_profile", return_value=A), \
                patch.object(api.blocks, "blocked", side_effect=[False, True]), \
                patch.object(api.versus_card, "render") as render:
            handler.do_GET()
        self.assertEqual(handler.status, 404)
        render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
