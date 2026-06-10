import json
import subprocess
import sys
import os
import pytest


def run_cli(*args, cwd=None):
    """Run the CLI as a subprocess and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "-m", "json_validator.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd or os.getcwd(),
    )
    return result.returncode, result.stdout, result.stderr


@pytest.fixture
def valid_pair(tmp_path):
    data = tmp_path / "data.json"
    schema = tmp_path / "schema.json"
    data.write_text(json.dumps({"name": "Alice", "age": 30}), encoding="utf-8")
    schema.write_text(json.dumps({
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name"],
    }), encoding="utf-8")
    return str(data), str(schema)


@pytest.fixture
def invalid_pair(tmp_path):
    data = tmp_path / "data.json"
    schema = tmp_path / "schema.json"
    data.write_text(json.dumps({"age": "not-an-int"}), encoding="utf-8")
    schema.write_text(json.dumps({
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name"],
    }), encoding="utf-8")
    return str(data), str(schema)


class TestCliExitCodes:
    def test_valid_exits_0(self, valid_pair):
        code, out, _ = run_cli(*valid_pair)
        assert code == 0
        assert "VALID" in out

    def test_invalid_exits_1(self, invalid_pair):
        code, out, _ = run_cli(*invalid_pair)
        assert code == 1
        assert "INVALID" in out

    def test_missing_data_file_exits_2(self, valid_pair, tmp_path):
        _, schema = valid_pair
        code, _, err = run_cli(str(tmp_path / "nope.json"), schema)
        assert code == 2
        assert "File not found" in err or "error" in err.lower()

    def test_missing_schema_file_exits_2(self, valid_pair, tmp_path):
        data, _ = valid_pair
        code, _, err = run_cli(data, str(tmp_path / "nope.json"))
        assert code == 2

    def test_malformed_data_exits_2(self, tmp_path, valid_pair):
        _, schema = valid_pair
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid}", encoding="utf-8")
        code, _, err = run_cli(str(bad), schema)
        assert code == 2

    def test_verbose_flag_includes_extra_info(self, valid_pair):
        code, out, _ = run_cli(*valid_pair, "--verbose")
        assert code == 0
        assert "VALID" in out

    def test_output_flag_writes_file(self, valid_pair, tmp_path):
        out_file = str(tmp_path / "result.txt")
        code, _, _ = run_cli(*valid_pair, "--output", out_file)
        assert code == 0
        assert os.path.exists(out_file)
        content = open(out_file, encoding="utf-8").read()
        assert "VALID" in content

    def test_invalid_errors_show_field_paths(self, invalid_pair):
        code, out, _ = run_cli(*invalid_pair)
        assert code == 1
        assert "$" in out  # JSON path present in output

    def test_verbose_shows_paths_for_valid(self, valid_pair):
        code, out, _ = run_cli(*valid_pair, "--verbose")
        assert code == 0
        assert "data:" in out
        assert "schema:" in out
        assert "No validation errors found" in out

    def test_verbose_shows_error_count_for_invalid(self, invalid_pair):
        code, out, _ = run_cli(*invalid_pair, "--verbose")
        assert code == 1
        assert "error(s) found" in out

    def test_path_traversal_exits_2(self, tmp_path):
        # Passing a path with .. should be caught by security check
        bad_path = str(tmp_path / ".." / "etc" / "passwd")
        code, _, err = run_cli(bad_path, str(tmp_path / "schema.json"))
        assert code == 2

    def test_bad_schema_exits_2(self, tmp_path):
        data = tmp_path / "data.json"
        schema = tmp_path / "schema.json"
        data.write_text('{"key": "val"}', encoding="utf-8")
        schema.write_text('{"type": "not-a-real-type"}', encoding="utf-8")
        code, _, err = run_cli(str(data), str(schema))
        assert code == 2

    def test_output_bad_path_exits_2(self, valid_pair):
        code, _, err = run_cli(*valid_pair, "--output", "/nonexistent/dir/out.txt")
        assert code == 2

    def test_self_ref_schema_exits_2(self, tmp_path):
        data = tmp_path / "data.json"
        schema = tmp_path / "schema.json"
        data.write_text('{"key": "val"}', encoding="utf-8")
        schema.write_text('{"$ref": "#"}', encoding="utf-8")
        code, _, err = run_cli(str(data), str(schema))
        assert code == 2
