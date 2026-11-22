"""Reading a server-sent-event body the way a browser does: frames separated by a blank line, comments (the keep-alive) ignored."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Frame:
    id: str
    event: str
    data: dict[str, Any]


def parse_frames(body: str) -> list[Frame]:
    frames: list[Frame] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.split("\n"):
            if line and not line.startswith(":"):
                name, _, value = line.partition(":")
                fields[name] = value.removeprefix(" ")
        if "data" in fields:
            frames.append(Frame(fields.get("id", ""), fields.get("event", "message"), json.loads(fields["data"])))
    return frames
