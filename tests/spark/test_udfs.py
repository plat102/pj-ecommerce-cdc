"""Unit tests for pure-function UDF bodies.

These test the underlying Python functions (not the Spark UDF wrappers), so
they don't need a SparkSession — startup cost stays with the transformer
tests where it earns its keep.
"""
from decimal import Decimal

from src.utils.udfs import (
    decode_decimal,
    hash_pii,
    tokenize_name,
)


# --- decode_decimal ---------------------------------------------------------

def _encode(dec: Decimal, scale: int = 2) -> bytes:
    unscaled = int(dec.scaleb(scale))
    n_bytes = max(1, (unscaled.bit_length() + 8) // 8)
    return unscaled.to_bytes(n_bytes, byteorder="big", signed=True)


def test_decode_decimal_round_trip_positive():
    encoded = _encode(Decimal("19.99"))
    assert decode_decimal(encoded, scale=2) == Decimal("19.99")


def test_decode_decimal_round_trip_negative():
    encoded = _encode(Decimal("-3.50"))
    assert decode_decimal(encoded, scale=2) == Decimal("-3.50")


def test_decode_decimal_none_returns_none():
    assert decode_decimal(None) is None


# --- hash_pii ---------------------------------------------------------------

def test_hash_pii_is_deterministic():
    assert hash_pii("alice@example.com") == hash_pii("alice@example.com")


def test_hash_pii_differs_by_input():
    assert hash_pii("alice@example.com") != hash_pii("bob@example.com")


def test_hash_pii_none_returns_none():
    assert hash_pii(None) is None


# --- tokenize_name ----------------------------------------------------------

def test_tokenize_name_preserves_initial():
    token = tokenize_name("Jane Doe")
    assert token is not None
    assert token.startswith("J.")
    assert len(token) == len("J.") + 6  # `X.` + 6-hex


def test_tokenize_name_uppercases_initial():
    token = tokenize_name("alice")
    assert token is not None and token.startswith("A.")


def test_tokenize_name_none_or_empty_returns_none():
    assert tokenize_name(None) is None
    assert tokenize_name("   ") is None
