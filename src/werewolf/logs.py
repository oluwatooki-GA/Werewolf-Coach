"""Log lines as JSON, one object per line, so a log service can read and search them."""

import json
import logging
from datetime import UTC, datetime

# what a call may attach with `extra=`; anything else a record carries is Python's own bookkeeping
FIELDS = ("play_id", "game_id", "seed", "status", "cost", "reason")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        body: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[
                :-3
            ]
            + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in FIELDS:
            if hasattr(record, field):
                body[field] = getattr(record, field)
        if record.exc_info:
            body["error"] = self.formatException(record.exc_info)
        return json.dumps(body, default=str)  # a Decimal or a path becomes text, never a crash


def setup_logging(level: int = logging.INFO) -> None:
    """Send every log line, ours and uvicorn's, to stderr as JSON. Safe to call twice."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h.formatter, JsonFormatter)]
    root.addHandler(handler)
    root.setLevel(level)
