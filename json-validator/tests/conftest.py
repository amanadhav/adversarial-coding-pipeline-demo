import json
import pytest


@pytest.fixture
def tmp_json(tmp_path):
    """Return a factory that writes a dict as JSON to a tmp file."""
    def _write(name: str, content) -> str:
        p = tmp_path / name
        p.write_text(json.dumps(content), encoding="utf-8")
        return str(p)
    return _write


@pytest.fixture
def tmp_text(tmp_path):
    """Return a factory that writes raw text to a tmp file."""
    def _write(name: str, text: str) -> str:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        return str(p)
    return _write
