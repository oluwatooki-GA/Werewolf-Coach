"""Log lines are one JSON object each, so a log service can read them."""

import io
import json
import logging
from decimal import Decimal

from werewolf.logs import JsonFormatter, setup_logging


def logger_into(stream: io.StringIO) -> logging.Logger:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("test.logs")
    log.handlers = [handler]
    log.propagate = False
    log.setLevel(logging.INFO)
    return log


def lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_a_line_is_json_with_the_time_level_logger_and_message() -> None:
    out = io.StringIO()
    logger_into(out).info("play started")
    (line,) = lines(out)
    assert line["message"] == "play started" and line["level"] == "INFO"
    assert line["logger"] == "test.logs" and str(line["time"]).endswith("Z")


def test_extra_fields_ride_along_and_odd_values_do_not_break_the_line() -> None:
    out = io.StringIO()
    logger_into(out).info("done", extra={"play_id": "abc", "cost": Decimal("0.12"), "seed": 5})
    (line,) = lines(out)
    assert (line["play_id"], line["seed"]) == ("abc", 5)
    assert line["cost"] == "0.12"  # not a JSON type, so written as text rather than failing


def test_a_message_with_new_lines_is_still_one_line() -> None:
    out = io.StringIO()
    logger_into(out).info("first\nsecond")
    assert len(out.getvalue().splitlines()) == 1
    assert lines(out)[0]["message"] == "first\nsecond"


def test_an_error_carries_its_traceback_in_the_same_line() -> None:
    out = io.StringIO()
    log = logger_into(out)
    try:
        raise RuntimeError("the database is full")
    except RuntimeError:
        log.exception("could not save")
    (line,) = lines(out)
    assert "RuntimeError: the database is full" in str(line["error"])


def test_setup_sends_every_log_line_to_stderr_as_json_and_can_be_repeated() -> None:
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        setup_logging()
        setup_logging()  # a second call must not double every line
        ours = [h for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
        assert len(ours) == 1
    finally:
        root.handlers = before
