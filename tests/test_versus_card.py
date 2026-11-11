import io
import unittest
from unittest.mock import patch

from PIL import Image

import api
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
        render.assert_called_once_with(A, B, "pt")

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
