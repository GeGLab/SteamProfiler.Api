"""POST /annoy: the Annoy chat integration (contract v1)."""
import io
import json
import unittest
from unittest.mock import patch

import api

PROFILES = {
    "76561197960287930": {"profile": {"persona": "Rabscuttle"}, "totals": {"hours": 1234.4},
                          "library": [{"appid": 440}, {"appid": 620}, {"appid": 70}]},
    "76561197960265728": {"profile": {"persona": "Ana"}, "totals": {"hours": 10},
                          "library": [{"appid": 620}]},
}
IDS = {"gabe": "76561197960287930", "ana": "76561197960265728"}


def resolve(who):
    if who not in IDS:
        raise api.Fail(404, "@err.not_found")
    return {"steamid": IDS[who]}


class AnnoyTest(unittest.TestCase):
    def call(self, body):
        raw = json.dumps(body).encode()
        handler = object.__new__(api.Handler)
        handler.path = "/annoy"
        handler.headers = {"Content-Length": str(len(raw)), "Host": "steamprofiler.org", "X-Forwarded-Proto": "https"}
        handler.rfile = io.BytesIO(raw)
        handler.wfile = io.BytesIO()
        handler.status = None
        handler.send_response = lambda status: setattr(handler, "status", status)
        handler.send_header = lambda name, value: None
        handler.end_headers = lambda: None
        handler.gate = lambda *a, **k: None
        with patch.object(api, "do_resolve", resolve), patch.object(api, "do_profile", PROFILES.__getitem__), \
                patch.object(api.blocks, "blocked", lambda sid: False):
            handler.annoy()
        return handler.status, json.loads(handler.wfile.getvalue())

    def test_profile_answers_text_and_the_card(self):
        status, body = self.call({"v": 1, "command": "steam", "text": "profile gabe", "locale": "pt-BR"})
        self.assertEqual(status, 200)
        self.assertEqual(body["text"], "Rabscuttle · 3 jogos · 1234 h jogadas\nhttps://steamprofiler.org/u/76561197960287930")
        self.assertEqual(body["images"], [{"url": "https://steamprofiler.org/api/og.png?q=76561197960287930"}])

    def test_versus_counts_games_in_common(self):
        status, body = self.call({"v": 1, "command": "steam", "text": "versus gabe ana", "locale": "en"})
        self.assertEqual(status, 200)
        self.assertEqual(body["text"], "Rabscuttle × Ana · 1 game in common\nhttps://steamprofiler.org/u/76561197960287930/vs/76561197960265728")
        self.assertEqual(body["images"], [{"url": "https://steamprofiler.org/api/versus.png?q=76561197960287930&vs=76561197960265728&lang=en"}])

    def test_errors_are_sentences(self):
        status, body = self.call({"v": 1, "command": "steam", "text": "profile ninguem", "locale": "pt-BR"})
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "Perfil Steam não encontrado: ninguem.")
        status, body = self.call({"v": 1, "command": "steam", "text": "dance", "locale": "en"})
        self.assertEqual(status, 400)
        self.assertIn("/steam profile", body["error"])


if __name__ == "__main__":
    unittest.main()
