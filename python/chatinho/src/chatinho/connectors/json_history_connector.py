"""JsonlHistoryConnector: a ready-to-use HistoryConnector."""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Union

from .base import HistoryConnector

if TYPE_CHECKING:
    from ..chat_app import ChatMessage


class JsonlHistoryConnector(HistoryConnector):
    """Persists messages as JSON Lines (one JSON object per line) to a file.

    A minimal, dependency-free reference implementation — swap it for a
    database-backed connector if you need concurrent access or queries.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self._path = Path(path)

    def load(self) -> List["ChatMessage"]:
        from ..chat_app import ChatMessage  # local import: chat_app -> connectors is the one-way edge

        if not self._path.exists():
            return []
        messages = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                messages.append(
                    ChatMessage(
                        id=data["id"],
                        text=data["text"],
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        is_command=data["is_command"],
                        reply_to=data.get("reply_to"),
                        is_sent_by_me=data["is_sent_by_me"],
                    )
                )
        return messages

    def save(self, message: "ChatMessage") -> None:
        record = {
            "id": message.id,
            "text": message.text,
            "timestamp": message.timestamp.isoformat(),
            "is_command": message.is_command,
            "reply_to": message.reply_to,
            "is_sent_by_me": message.is_sent_by_me,
        }
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
