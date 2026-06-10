import pytest
import jsonschema
from json_validator.validator import validate, ValidationResult


SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
    },
    "required": ["name"],
}


class TestValidate:
    def test_valid_data_returns_valid_result(self):
        result = validate({"name": "Alice", "age": 30}, SIMPLE_SCHEMA)
        assert isinstance(result, ValidationResult)
        assert result.valid is True
        assert result.errors == []

    def test_invalid_data_returns_invalid_result(self):
        result = validate({"age": "not-an-int"}, SIMPLE_SCHEMA)
        assert result.valid is False
        assert len(result.errors) >= 1

    def test_error_includes_field_path(self):
        result = validate({"name": "Alice", "age": "bad"}, SIMPLE_SCHEMA)
        assert result.valid is False
        paths = [e["path"] for e in result.errors]
        assert any("age" in p for p in paths)

    def test_missing_required_field(self):
        result = validate({"age": 30}, SIMPLE_SCHEMA)
        assert result.valid is False
        assert any("name" in e["message"] for e in result.errors)

    def test_bad_schema_raises_schema_error(self):
        bad_schema = {"type": "not-a-real-type"}
        with pytest.raises(jsonschema.SchemaError):
            validate({"key": "val"}, bad_schema)

    def test_remote_ref_raises_ref_resolution_error(self):
        schema_with_remote_ref = {
            "$ref": "https://example.com/remote-schema.json"
        }
        with pytest.raises(Exception):
            validate({"key": "val"}, schema_with_remote_ref)

    def test_file_ref_raises_ref_resolution_error(self):
        schema_with_file_ref = {"$ref": "file:///etc/passwd"}
        with pytest.raises(Exception):
            validate({"key": "val"}, schema_with_file_ref)

    def test_deeply_nested_schema(self):
        # Build a 10-level deep schema
        schema = {"type": "object"}
        current = schema
        for i in range(10):
            prop = {"type": "object", "properties": {}}
            current["properties"] = {f"level{i}": prop}
            current = prop
        result = validate({}, schema)
        assert isinstance(result, ValidationResult)

    def test_array_data_valid(self):
        array_schema = {"type": "array", "items": {"type": "integer"}}
        result = validate([1, 2, 3], array_schema)
        assert result.valid is True

    def test_array_data_invalid(self):
        array_schema = {"type": "array", "items": {"type": "integer"}}
        result = validate([1, "two", 3], array_schema)
        assert result.valid is False
