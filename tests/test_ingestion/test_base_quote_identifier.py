"""Tests for src.ingestion.base.quote_identifier.

Kept in a separate file from ``test_base.py`` so the existing
``TestValidateIdentifier`` block is not churned.
"""

import pytest
from src.core.exceptions import SqlValidationError
from src.ingestion.base import quote_identifier


class TestQuoteIdentifier:
    def test_wraps_simple_name(self) -> None:
        assert quote_identifier("orders") == '"orders"'

    def test_allows_spaces(self) -> None:
        assert quote_identifier("My Column") == '"My Column"'

    def test_escapes_embedded_double_quote(self) -> None:
        assert quote_identifier('weird"name') == '"weird""name"'

    def test_allows_unicode(self) -> None:
        assert quote_identifier("rég ion") == '"rég ion"'

    def test_allows_punctuation(self) -> None:
        assert quote_identifier("order-id.v2") == '"order-id.v2"'

    def test_rejects_empty(self) -> None:
        with pytest.raises(SqlValidationError):
            quote_identifier("")

    def test_rejects_overlong(self) -> None:
        with pytest.raises(SqlValidationError):
            quote_identifier("a" * 200)

    def test_rejects_null_byte(self) -> None:
        with pytest.raises(SqlValidationError):
            quote_identifier("bad\x00name")

    def test_rejects_newline(self) -> None:
        with pytest.raises(SqlValidationError):
            quote_identifier("bad\nname")
