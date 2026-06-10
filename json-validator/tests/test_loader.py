import os
import pytest
from unittest.mock import patch
from json_validator.loader import load_json, LoadError, SizeError, JSONParseError


class TestLoadJson:
    def test_valid_json_returns_dict(self, tmp_json):
        path = tmp_json("data.json", {"key": "value"})
        result = load_json(path)
        assert result == {"key": "value"}

    def test_missing_file_raises_load_error(self, tmp_path):
        with pytest.raises(LoadError, match="File not found"):
            load_json(str(tmp_path / "nonexistent.json"))

    def test_malformed_json_raises_json_parse_error(self, tmp_text):
        path = tmp_text("bad.json", "{bad json")
        with pytest.raises(JSONParseError, match="Malformed JSON"):
            load_json(path)

    def test_empty_file_raises_json_parse_error(self, tmp_text):
        path = tmp_text("empty.json", "")
        with pytest.raises(JSONParseError, match="Malformed JSON"):
            load_json(path)

    def test_oversized_file_raises_size_error(self, tmp_text):
        path = tmp_text("big.json", "{}")
        max_bytes = 1  # {} is 2 bytes, so 2 > 1 triggers the guard
        with pytest.raises(SizeError, match="File too large"):
            load_json(path, max_bytes=max_bytes)

    def test_unicode_content_loaded_correctly(self, tmp_text):
        path = tmp_text("unicode.json", '{"name": "héllo wörld"}')
        result = load_json(path)
        assert result["name"] == "héllo wörld"

    def test_unicode_decode_error_raises_load_error(self, tmp_path):
        p = tmp_path / "latin.json"
        p.write_bytes(b'{"name": "\xff\xfe"}')
        with pytest.raises(LoadError, match="Cannot decode"):
            load_json(str(p))
