import json
import logging
import os
import pathlib
import sys

os.environ.setdefault("TABLE_NAME", "test-table")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "app"))

import handler  # noqa: E402


def _formatted(msg, *args):
    assert handler.logger.handlers, "handler logger has no handlers configured"
    formatter = handler.logger.handlers[0].formatter
    record = handler.logger.makeRecord(
        handler.logger.name, logging.INFO, __file__, 0, msg, args, None,
    )
    return formatter.format(record)


def test_log_formatter_escapes_dangerous_characters():
    # A message containing characters a hand-rolled JSON template would not
    # escape: an embedded quote and a backslash.
    line = _formatted('value with a "quote" and a backslash: %s', "back\\slash")
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert "quote" in parsed["event"]


def test_log_formatter_handles_the_handler_module_own_log_line():
    # The exact shape handle() logs after writing a record: this used to be
    # a pre-serialised JSON string passed as the log message, which produced
    # nested, unescaped JSON when spliced into the formatter's own template.
    line = _formatted(
        "record written record_id=%s key=%s", "rec-123", "uploads/rec-123.json"
    )
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert "rec-123" in parsed["event"]
    assert "uploads/rec-123.json" in parsed["event"]
