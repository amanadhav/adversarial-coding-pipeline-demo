"""JSON Schema validation with security-hardened RefResolver."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import jsonschema
import jsonschema.validators


@dataclass
class ValidationResult:
    valid: bool
    errors: List[dict] = field(default_factory=list)


def _make_local_only_resolver(schema: object) -> jsonschema.RefResolver:
    """
    Build a RefResolver that rejects all remote URI schemes.

    This prevents DoS via malicious schemas that reference external
    resources or define deeply recursive remote $ref chains.
    """
    def _raise_on_remote(uri: str):
        raise jsonschema.RefResolutionError(
            f"Schema contains disallowed remote $ref: {uri!r}"
        )

    handlers = {
        "http": _raise_on_remote,
        "https": _raise_on_remote,
        "ftp": _raise_on_remote,
        "file": _raise_on_remote,   # block local file reads via $ref
    }
    # NOTE: jsonschema.RefResolver is deprecated since v4.18.0.
    # Migrate to referencing.Registry before upgrading jsonschema past v4.x.
    return jsonschema.RefResolver.from_schema(schema, handlers=handlers)


def validate(data: object, schema: object) -> ValidationResult:
    """
    Validate *data* against *schema*.

    Parameters
    ----------
    data:
        Parsed JSON data (any JSON-compatible Python object).
    schema:
        Parsed JSON Schema (dict).

    Returns
    -------
    ValidationResult
        .valid is True iff no errors were found.
        .errors is a list of dicts with 'path' and 'message' keys.

    Raises
    ------
    jsonschema.SchemaError
        If *schema* is not a valid JSON Schema.
    jsonschema.RefResolutionError
        If *schema* contains disallowed remote $ref URIs.
    """
    validator_cls = jsonschema.Draft7Validator

    # Validate the schema itself first — raises SchemaError if bad.
    validator_cls.check_schema(schema)

    resolver = _make_local_only_resolver(schema)
    validator = validator_cls(schema, resolver=resolver)

    errors = []
    for err in validator.iter_errors(data):
        path_parts = list(err.absolute_path)
        if path_parts:
            path_str = "$." + ".".join(str(p) for p in path_parts)
        else:
            path_str = "$"
        errors.append({"path": path_str, "message": err.message})

    return ValidationResult(valid=len(errors) == 0, errors=errors)
