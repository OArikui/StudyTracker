from __future__ import annotations
from dataclasses import dataclass
from urllib.request import Request, urlopen
import json


@dataclass
class ManicTimeConfig:
    document_mode: str = "material"  # material / material_position
    server_url: str = ""


class ManicTimeAdapter:
    """
    Integration boundary for ManicTime.

    The Windows client itself records the foreground application and window title.
    This adapter therefore controls only the application's descriptive title and
    optional Server API connectivity. It never generates fake keyboard/mouse input.
    """

    def __init__(self, config: ManicTimeConfig):
        self.config = config

    def window_title(self, material, position):
        if self.config.document_mode == "material_position" and position:
            return f"{material} — {position} — Study Tracker"
        return f"{material} — Study Tracker"

    def test_server(self, token=""):
        if not self.config.server_url:
            raise ValueError("ManicTime Server URLが未設定です。")
        req = Request(self.config.server_url.rstrip("/") + "/api")
        req.add_header("Accept", "application/vnd.manictime.v3+json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urlopen(req, timeout=5) as res:
            return json.loads(res.read().decode("utf-8"))
