"""Unit tests for scripts/dlq_replay.py (no Kafka needed).

Pure helpers are tested input -> output. Subcommands run against a fake
consumer that mimics the kafka-python calls the CLI makes (manual
assignment, offsets, seek, poll).
"""
from __future__ import annotations

import importlib.util
import json
import re
from collections import namedtuple
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dlq_replay.py"


def _load():
    spec = importlib.util.spec_from_file_location("dlq_replay", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dlq = _load()


# --------------------------------------------------------------------------
# 2.1 Pure helpers
# --------------------------------------------------------------------------

def test_build_replay_key_deterministic():
    a = dlq.build_replay_key("products_cdc_sink_dlq", 0, 42)
    b = dlq.build_replay_key("products_cdc_sink_dlq", 0, 42)
    assert a == b
    assert re.fullmatch(r"[0-9a-f]{32}", a)


def test_build_replay_key_distinct_by_offset():
    assert dlq.build_replay_key("products_cdc_sink_dlq", 0, 42) != dlq.build_replay_key(
        "products_cdc_sink_dlq", 0, 43
    )


def test_pick_dest_topic_sink_dlq():
    assert dlq.pick_dest_topic("products_cdc_sink_dlq") == "pg.public.products"


def test_pick_dest_topic_gx_dlq():
    assert dlq.pick_dest_topic("products_cdc_dlq") == "pg.public.products"


def test_pick_dest_topic_legacy_short_name():
    assert dlq.pick_dest_topic("products_dlq") == "pg.public.products"


def test_pick_dest_topic_refuses_debezium_connect_dlq():
    with pytest.raises(dlq.RefusedError, match="pre-Debezium bytes"):
        dlq.pick_dest_topic("debezium_connect_dlq")


def test_pick_dest_topic_refuses_unknown_naming():
    with pytest.raises(dlq.RefusedError, match="unrecognized"):
        dlq.pick_dest_topic("products_cdc_quarantine")
    with pytest.raises(dlq.RefusedError, match="unknown table"):
        dlq.pick_dest_topic("invoices_cdc_dlq")


def test_refuse_if_re_replay_raises_when_field_present():
    payload = {"_replay_source_topic": "x", "_replay_source_offset": 5, "id": 1}
    with pytest.raises(dlq.RefusedError, match="x@5"):
        dlq.refuse_if_re_replay(payload)


def test_refuse_if_re_replay_passes_when_absent():
    assert dlq.refuse_if_re_replay({"id": 1, "_error_stage": "spark_sink"}) is None


def test_strip_dlq_envelope_drops_error_fields():
    payload = {
        "id": 7,
        "name": "Widget",
        "_version": 1700000000000,
        "_deleted": 0,
        "_error_stage": "spark_sink",
        "_error_class": "SQLException",
        "_error_message": "connection refused",
    }
    out = dlq.strip_dlq_envelope(payload)
    assert not any(k.startswith("_error_") for k in out)
    assert out == {"id": 7, "name": "Widget", "_version": 1700000000000, "_deleted": 0}
    assert "_error_stage" in payload  # input not mutated


# --------------------------------------------------------------------------
# 2.2 CLI argument parsing
# --------------------------------------------------------------------------

def test_help_lists_exactly_read_only_subcommands(capsys):
    with pytest.raises(SystemExit) as exc:
        dlq.main(["--help"], consumer_factory=_no_consumer)
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "read-only diagnostic tool; replay pending in add-dlq-avro-replay" in out
    parser = dlq.build_parser()
    subparsers = next(
        a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"
    )
    assert sorted(subparsers.choices) == ["audit-log", "inspect", "list"]
    assert "replay" not in subparsers.choices


def test_module_never_references_a_producer():
    assert "KafkaProducer" not in SCRIPT.read_text()


# --------------------------------------------------------------------------
# Subcommands against a fake consumer (1.4 - 1.6)
# --------------------------------------------------------------------------

TP = namedtuple("TP", "topic partition")
Msg = namedtuple("Msg", "topic partition offset timestamp key value")


def _no_consumer(*_a, **_k):
    raise AssertionError("consumer must not be built for --help")


class FakeConsumer:
    """Single-partition topics; poll returns everything from the position."""

    def __init__(self, topics):
        self.topics = topics  # {topic: [value_bytes, ...]}
        self.pos = {}
        self.closed = False

    def partitions_for_topic(self, topic):
        return {0} if topic in self.topics else None

    def assign(self, tps):
        self.assigned = list(tps)

    def beginning_offsets(self, tps):
        return {tp: 0 for tp in tps}

    def end_offsets(self, tps):
        return {tp: len(self.topics[tp.topic]) for tp in tps}

    def seek_to_beginning(self, *tps):
        for tp in tps:
            self.pos[tp] = 0

    def seek(self, tp, offset):
        self.pos[tp] = offset

    def poll(self, timeout_ms=0):
        out = {}
        for tp in self.assigned:
            start = self.pos.get(tp, 0)
            values = self.topics[tp.topic][start:]
            if values:
                out[tp] = [
                    Msg(tp.topic, 0, start + i, 0, f"{tp.topic}".encode(), v)
                    for i, v in enumerate(values)
                ]
                self.pos[tp] = start + len(values)
        return out

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _fake_topic_partition(monkeypatch):
    monkeypatch.setattr(dlq, "_topic_partition", lambda t, p: TP(t, p))


def _sink_msg(i, message="ClickHouse timeout"):
    return json.dumps(
        {"id": i, "_version": 100 + i, "_deleted": 0,
         "_error_stage": "spark_sink", "_error_class": "SQLException",
         "_error_message": message}
    ).encode()


def _run(argv, topics):
    consumer = FakeConsumer(topics)
    code = dlq.main(argv, consumer_factory=lambda *_: consumer)
    assert consumer.closed
    return code


def test_list_prints_one_row_per_message(capsys):
    long_msg = "x" * 200
    topics = {"products_cdc_sink_dlq": [_sink_msg(0), _sink_msg(1), _sink_msg(2, long_msg)]}
    assert _run(["list", "--topic", "products_cdc_sink_dlq"], topics) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].split() == ["partition", "offset", "key", "error_stage", "error_message"]
    data = [l for l in lines[2:] if "spark_sink" in l]
    assert len(data) == 3
    assert "x" * 80 + "..." in out and "x" * 81 not in out
    assert "3 message(s) on products_cdc_sink_dlq" in out


def test_list_handles_non_json_value(capsys):
    topics = {"debezium_connect_dlq": [b"\x00\x01binary"]}
    assert _run(["list", "--topic", "debezium_connect_dlq"], topics) == 0
    assert "unknown" in capsys.readouterr().out


def test_list_missing_topic_exits_2(capsys):
    assert _run(["list", "--topic", "nope_dlq"], {}) == 2
    assert "topic not found" in capsys.readouterr().err


def test_inspect_prints_full_json(capsys):
    topics = {"products_cdc_sink_dlq": [_sink_msg(0), _sink_msg(1)]}
    assert _run(["inspect", "--topic", "products_cdc_sink_dlq", "--offset", "1"], topics) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == 1
    assert payload["_error_stage"] == "spark_sink"


def test_inspect_offset_out_of_range_exits_1(capsys):
    topics = {"products_cdc_sink_dlq": [_sink_msg(0)]}
    assert _run(["inspect", "--topic", "products_cdc_sink_dlq", "--offset", "5"], topics) == 1
    assert "no message" in capsys.readouterr().err


def test_audit_log_json_empty_topic(capsys):
    assert _run(["audit-log", "--format", "json"], {"dlq_replay_log": []}) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_audit_log_table_empty_topic(capsys):
    assert _run(["audit-log", "--format", "table"], {"dlq_replay_log": []}) == 0
    assert "no records" in capsys.readouterr().out


def test_audit_log_json_and_table_with_records(capsys):
    recs = [
        json.dumps({"batch_id": "b1", "source_topic": "products_cdc_sink_dlq", "count": 3}).encode(),
        json.dumps({"batch_id": "b2", "source_topic": "orders_cdc_dlq", "count": 1, "note": "x"}).encode(),
    ]
    assert _run(["audit-log", "--format", "json"], {"dlq_replay_log": recs}) == 0
    assert [r["batch_id"] for r in json.loads(capsys.readouterr().out)] == ["b1", "b2"]

    assert _run(["audit-log", "--format", "table"], {"dlq_replay_log": recs}) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["batch_id", "source_topic", "count", "note"]
    assert len(lines) == 4


def test_unreachable_broker_exits_2(capsys):
    def boom(*_a):
        raise ConnectionError("no brokers")

    assert dlq.main(["list", "--topic", "products_cdc_sink_dlq"], consumer_factory=boom) == 2
    assert "cannot connect to Kafka" in capsys.readouterr().err
