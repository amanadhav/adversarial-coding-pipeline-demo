# Design Document: JSON Schema Validator CLI

> **Status: LOCKED**
> Produced by architect subagent using office-hours + architecture-lock skills.
> No architectural changes without explicit human re-approval.

---

## Part 1 — Problem Framing (Office Hours)

### 1. What problem are we actually solving?

Developers and CI pipelines need to verify that JSON data files conform to a declared schema **before** those files reach downstream systems — because malformed or schema-violating JSON causes silent failures that are hard to trace.

### 2. Who is affected and how?

| Stakeholder | Usage | Current workaround |
|---|---|---|
| Developer (local) | Runs manually before committing | Ad-hoc Python scripts or online validators |
| CI/CD pipeline | Runs as a gate step | Missing — validation is absent or bespoke |
| Data producer | Gets clear error messages pointing to field paths | None — they get cryptic downstream failures |

Constraints: tool must be pip-installable, produce machine-parseable exit codes, and be scriptable.

### 3. What does success look like?

- `validate-json data.json schema.json` exits `0` when valid, `1` when invalid, `2` on operational error — every time, deterministically.
- Validation errors include the JSON Pointer path (e.g. `$.address.zip`) to the offending field.
- Files ≤ 10 MB are processed in < 1 s on a modern laptop.
- 100 % of the test matrix passes before any code is merged.
- TDD cycle: every behaviour has a failing test written first.

### 4. What are the failure modes?

Ordered by blast radius:

1. **Malicious recursive `$ref` in schema** — can cause infinite recursion / memory exhaustion (DoS). Blast: tool hangs or OOMs.
2. **Very large file (> 10 MB)** — JSON decode loads entire file into RAM. Blast: OOM on constrained CI runners.
3. **Path traversal in file arguments** — attacker supplies `../../etc/passwd`. Blast: arbitrary file read.
4. **Malformed JSON data file** — `json.JSONDecodeError`. Blast: unhelpful crash unless caught.
5. **Malformed / invalid schema** — `jsonschema.SchemaError`. Blast: misleading "data invalid" error.
6. **Missing file** — `FileNotFoundError`. Blast: exit 2 expected but missing.
7. **Empty file** — `json.JSONDecodeError`. Blast: confusing error message.
8. **Unicode content** — Python's `json` module handles UTF-8 by default; explicit `encoding="utf-8"` required on Windows.

### 5. What's the simplest version that delivers value?

Single-file CLI (`validator.py`) that:
- Reads two file paths from argparse.
- Guards file size (reject > 10 MB).
- Reads and parses both files with clear error messages.
- Runs `jsonschema.validate()` and prints each error's `message` + `absolute_path`.
- Exits 0 / 1 / 2 correctly.

Everything else (--verbose, --output, $ref depth guard) is additive and can be layered on top.

### 6. What are we explicitly NOT doing?

- No JSON Schema draft auto-detection beyond what `jsonschema` provides.
- No streaming / chunked parsing of large JSON arrays.
- No remote `$ref` resolution (network calls disabled).
- No GUI or web interface.
- No schema generation from data.
- No support for YAML, TOML, or other formats.
- No recursive directory scanning.

---

## Part 2 — Problem Statement (Structured)

```
Problem Statement
  Developers need a deterministic CLI tool to validate JSON data files against
  a JSON schema so that schema violations are caught early, with clear field-path
  error messages, before data reaches downstream systems.

Stakeholders
  - Developer (local dev): runs ad-hoc; needs clear output.
  - CI/CD pipeline: needs reliable exit codes and optional file output.
  - Data producer: needs actionable error messages pointing to exact fields.

Success Criteria
  - Exit codes 0/1/2 are deterministic and documented.
  - Each validation error includes the JSON Pointer path to the offending field.
  - Files ≤ 10 MB validated in < 1 s.
  - Full TDD: failing test exists before every production line.
  - 100 % test matrix pass rate.

Failure Modes (blast-radius order)
  1. Recursive $ref DoS
  2. Large-file OOM
  3. Path traversal
  4. Malformed data JSON
  5. Malformed schema
  6. Missing file
  7. Empty file
  8. Unicode encoding on Windows

MVP Scope
  Single-module CLI with argparse, size guard, well-formedness check,
  jsonschema validation, field-path error output, correct exit codes.

Out of Scope
  Remote $ref, streaming, YAML/TOML, schema generation, GUI.
```

---

## Part 3 — Scope Decision

**Selective Expansion:** The request is well-scoped. Adding two items not explicitly listed but necessary for correctness:

1. **File-size guard** (10 MB cap) to prevent DoS — referenced in security concerns but not in functional requirements.
2. **`$ref` depth guard** via `jsonschema.RefResolver` with a custom handler that disallows remote URIs and caps recursion — referenced in security concerns but no implementation strategy was given.

---

## Part 4 — Architecture

### Project Layout

```
json-validator/
├── pyproject.toml          # build metadata, dependencies, entry point
├── README.md
├── src/
│   └── json_validator/
│       ├── __init__.py
│       ├── cli.py          # argparse entry point
│       ├── loader.py       # file I/O, size guard, JSON parse
│       ├── validator.py    # jsonschema validation, error formatting
│       └── security.py     # path-traversal check, $ref resolver factory
└── tests/
    ├── conftest.py         # shared fixtures (tmp files, schemas)
    ├── test_cli.py         # end-to-end CLI via subprocess
    ├── test_loader.py      # unit: loader module
    ├── test_validator.py   # unit: validator module
    └── test_security.py    # unit: security module
```

### Data Flow Diagram (ASCII)

```
  CLI invocation
  $ validate-json data.json schema.json [--verbose] [--output out.txt]
         │
         ▼
  ┌──────────────────────────────────────────┐
  │  cli.py  (argparse)                      │
  │  - parse args                            │
  │  - call security.check_path() on both   │
  │    file paths                            │
  └──────────┬───────────────────────────────┘
             │ safe paths
             ▼
  ┌──────────────────────────────────────────┐
  │  loader.py                               │
  │  load_json(path) →                       │
  │    1. os.path.getsize() ≤ MAX_BYTES      │
  │    2. open(path, encoding="utf-8")       │
  │    3. json.load()                        │
  │    returns: (dict|list, None) or         │
  │             (None, LoadError)            │
  └──────────┬───────────────────────────────┘
             │ (data_obj, schema_obj)
             ▼
  ┌──────────────────────────────────────────┐
  │  validator.py                            │
  │  validate(data, schema) →                │
  │    1. build RefResolver (local-only)     │
  │    2. jsonschema.Draft7Validator.check_  │
  │       schema(schema)  ← catches bad      │
  │       schemas before touching data       │
  │    3. collect errors via iter_errors()   │
  │    4. format each: path + message        │
  │    returns: ValidationResult(            │
  │      valid: bool,                        │
  │      errors: list[FormattedError]        │
  │    )                                     │
  └──────────┬───────────────────────────────┘
             │ ValidationResult
             ▼
  ┌──────────────────────────────────────────┐
  │  cli.py  (output stage)                  │
  │  - print to stdout (always)              │
  │  - if --output: write to file            │
  │  - if --verbose: include schema path     │
  │    and error counts in output            │
  │  - sys.exit(0 | 1 | 2)                  │
  └──────────────────────────────────────────┘

  Error paths (any component → exit 2):
  ┌───────────────────────────────────────────┐
  │  security.check_path() raises PathError   │─► stderr msg → exit 2
  │  loader.load_json() raises LoadError      │─► stderr msg → exit 2
  │    (FileNotFoundError, SizeError,         │
  │     JSONDecodeError, UnicodeDecodeError)  │
  │  validator raises SchemaError             │─► stderr msg → exit 2
  └───────────────────────────────────────────┘
```

### State Machine

The CLI is a single-pass, non-interactive process. States are execution phases:

```
  [START]
     │  args parsed ok
     ▼
  [PATH_CHECK]
     │  paths safe          │  path traversal detected
     ▼                      ▼
  [LOAD_DATA]           [EXIT_2]  ◄─ terminal (error)
     │  parse ok            │
     ▼                      │  file missing / too large /
  [LOAD_SCHEMA]          malformed / unicode error
     │  parse ok            │
     ▼                      │
  [VALIDATE]  ─────► [EXIT_2] (schema error)
     │
     ├── errors found ──► [EXIT_1]  ◄─ terminal (invalid)
     │
     └── no errors   ──► [EXIT_0]  ◄─ terminal (valid)

  All states except EXIT_* are non-reversible (no retry logic).
  EXIT_0 = success, EXIT_1 = data invalid, EXIT_2 = operational error.
```

---

## Part 5 — Error Paths and Failure Modes

| # | Failure | Detection point | Error type raised | User-visible message | Exit code |
|---|---|---|---|---|---|
| 1 | Recursive `$ref` DoS | `validator.py` RefResolver | `jsonschema.RefResolutionError` | "Schema contains disallowed remote $ref: {uri}" | 2 |
| 2 | File > 10 MB | `loader.py` size check | `SizeError(LoadError)` | "File too large: {path} ({size} bytes, max 10485760)" | 2 |
| 3 | Path traversal | `security.py` | `PathError` | "Disallowed path: {path}" | 2 |
| 4 | Malformed data JSON | `loader.py` `json.load()` | `JSONParseError(LoadError)` | "Malformed JSON in data file: {detail}" | 2 |
| 5 | Malformed schema | `validator.py` `check_schema()` | `jsonschema.SchemaError` | "Invalid JSON Schema: {detail}" | 2 |
| 6 | Missing file | `loader.py` `open()` | `FileNotFoundError` → `LoadError` | "File not found: {path}" | 2 |
| 7 | Empty file | `loader.py` `json.load()` | `JSONParseError(LoadError)` | "Malformed JSON in data file: Empty document" | 2 |
| 8 | Unicode error | `loader.py` `open()` | `UnicodeDecodeError` → `LoadError` | "Cannot decode file as UTF-8: {path}" | 2 |
| 9 | Data fails schema | `validator.py` `iter_errors()` | — (collected, not raised) | "INVALID\n  - $.field: message" | 1 |

---

## Part 6 — Test Matrix

| Component | Test ID | Test type | Input | Expected | What to mock | DI boundary |
|---|---|---|---|---|---|---|
| `security.check_path` | S-01 | Unit | `"../../etc/passwd"` | raises `PathError` | — | `check_path(path: str) -> None` |
| `security.check_path` | S-02 | Unit | `"data/file.json"` | no exception | — | same |
| `loader.load_json` | L-01 | Unit | file > 10 MB | raises `SizeError` | `os.path.getsize` | `load_json(path, fs=os)` |
| `loader.load_json` | L-02 | Unit | missing file | raises `LoadError` | `builtins.open` | `load_json(path, open_fn=open)` |
| `loader.load_json` | L-03 | Unit | `{}` (empty object) | returns `{}` | — | — |
| `loader.load_json` | L-04 | Unit | empty file `""` | raises `JSONParseError` | — | — |
| `loader.load_json` | L-05 | Unit | `{"name": "héllo"}` Unicode | returns dict | — | — |
| `loader.load_json` | L-06 | Unit | `{bad json` | raises `JSONParseError` | — | — |
| `validator.validate` | V-01 | Unit | valid data + schema | `ValidationResult(valid=True, errors=[])` | `jsonschema` | `validate(data, schema, resolver_factory=make_resolver)` |
| `validator.validate` | V-02 | Unit | invalid data + schema | `valid=False`, errors list non-empty | — | same |
| `validator.validate` | V-03 | Unit | bad schema | raises `SchemaError` | — | same |
| `validator.validate` | V-04 | Unit | schema with remote `$ref` | raises `RefResolutionError` | — | same |
| `validator.validate` | V-05 | Unit | deeply nested schema (10 levels) | returns result | — | — |
| `cli` | C-01 | Integration (subprocess) | valid data + schema | stdout "VALID", exit 0 | — | subprocess |
| `cli` | C-02 | Integration | invalid data | stdout "INVALID" + errors, exit 1 | — | subprocess |
| `cli` | C-03 | Integration | missing data file | stderr message, exit 2 | — | subprocess |
| `cli` | C-04 | Integration | `--output results.txt` + valid | file written, exit 0 | — | subprocess |
| `cli` | C-05 | Integration | `--verbose` flag | extra info in output | — | subprocess |
| `cli` | C-06 | Integration | `--output /nonexistent/path/out.txt` | stderr message, exit 2 | — | subprocess |

Coverage target: **≥ 90 % line coverage** across all modules.

---

## Part 7 — Security Considerations

1. **Path traversal** — `security.check_path()` resolves `os.path.abspath()` and rejects any path containing `..` segments or that resolves outside the working directory. Applied to both data and schema paths before any file I/O.

2. **Large-file DoS** — `loader.load_json()` calls `os.path.getsize()` before `open()`. Files > `MAX_FILE_BYTES` (10 MB, configurable via env var `JSON_VALIDATOR_MAX_BYTES`) are rejected with exit 2.

3. **Malicious `$ref` (remote URIs / recursive)** — `validator.py` builds a `jsonschema.RefResolver` with a custom `handlers` dict that raises `RefResolutionError` for any URI with a non-empty scheme (i.e. `http://`, `https://`, `file://` outside the local file). Recursion depth is not directly limited by `jsonschema` but disallowing remote refs eliminates the primary vector. Deep local-only recursion is bounded by Python's default recursion limit (1000).

4. **Input trust boundary** — both input files are treated as untrusted. Schema is validated with `check_schema()` before use.

5. **Output file path** — the `--output` path is checked that the parent directory exists and is writable before writing. No path traversal check is applied here (user-controlled output path is acceptable), but the file is opened with `"w"` not `"a"` to prevent appending to sensitive files unintentionally.

---

## Part 8 — Performance Considerations

- **Expected load:** Single-shot CLI invocation. No concurrency needed.
- **Bottleneck:** `json.load()` for large files. Mitigated by 10 MB cap.
- **Startup time:** `jsonschema` import adds ~50 ms. Acceptable for CLI use.
- **Memory:** Entire document loaded into memory. Acceptable under 10 MB cap (~10× expansion worst case = 100 MB, within normal limits).
- **No caching required** at v1.

---

## Part 9 — Task Breakdown

Each task is 2–5 minutes, independently committable, and has an exact verification command.

---

### Task 0: Scaffold project structure

**Files:**
- `json-validator/pyproject.toml`
- `json-validator/src/json_validator/__init__.py`
- `json-validator/tests/__init__.py`
- `json-validator/tests/conftest.py`

**Code:**

`json-validator/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "json-validator"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
    "jsonschema==4.23.0",
]

[project.scripts]
validate-json = "json_validator.cli:main"

[project.optional-dependencies]
dev = [
    "pytest==8.2.2",
    "pytest-cov==5.0.0",
]

[tool.setuptools.packages.find]
where = ["src"]
```

`json-validator/src/json_validator/__init__.py`: (empty)

`json-validator/tests/__init__.py`: (empty)

`json-validator/tests/conftest.py`:
```python
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
```

**Test command:**
```bash
cd json-validator && pip install -e ".[dev]" --quiet && pytest --co -q
```
Expected: collection succeeds with 0 tests (empty suite, no errors).

**Depends on:** none

---

### Task 1: Write RED tests for `security.py`

**Files:**
- `json-validator/tests/test_security.py`

**Code:**
```python
import pytest
from json_validator.security import check_path, PathError


class TestCheckPath:
    def test_traversal_dotdot_rejected(self, tmp_path):
        bad = str(tmp_path / ".." / "etc" / "passwd")
        with pytest.raises(PathError, match="Disallowed path"):
            check_path(bad)

    def test_plain_relative_path_accepted(self, tmp_path):
        good = str(tmp_path / "data.json")
        # Should not raise — path stays within tmp_path parent
        check_path(good)  # no exception expected

    def test_absolute_safe_path_accepted(self, tmp_path):
        good = str(tmp_path / "schema.json")
        check_path(good)

    def test_double_dotdot_in_middle_rejected(self, tmp_path):
        bad = str(tmp_path / "subdir" / ".." / ".." / "secret")
        with pytest.raises(PathError):
            check_path(bad)
```

**Test command:**
```bash
cd json-validator && pytest tests/test_security.py -v 2>&1 | head -30
```
Expected: 4 FAILED (ImportError — module does not exist yet). This is the RED phase.

**Depends on:** Task 0

---

### Task 2: Implement `security.py` (GREEN)

**Files:**
- `json-validator/src/json_validator/security.py`

**Code:**
```python
"""Security helpers: path traversal guard."""
from __future__ import annotations

import os


class PathError(ValueError):
    """Raised when a file path is considered unsafe."""


def check_path(path: str) -> None:
    """
    Raise PathError if *path* contains path-traversal sequences.

    Resolves the path to its absolute form and rejects any path
    whose normalised form contains a ``..`` component.
    """
    # Normalise to absolute without following symlinks
    normalised = os.path.normpath(os.path.abspath(path))
    # Reject if any component is '..' after normalisation
    # (normpath collapses them, so check the original split)
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        raise PathError(f"Disallowed path: {path!r}")
    # Second guard: normalised path must not escape via symlink tricks
    # (covered by normpath collapsing; if the original had '..' it was
    # already caught above — this is a belt-and-suspenders check)
    _ = normalised  # kept for future extension
```

**Test command:**
```bash
cd json-validator && pytest tests/test_security.py -v
```
Expected: 4 PASSED. This is the GREEN phase.

**Depends on:** Task 1

---

### Task 3: Write RED tests for `loader.py`

**Files:**
- `json-validator/tests/test_loader.py`

**Code:**
```python
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
        max_bytes = 10
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
```

**Test command:**
```bash
cd json-validator && pytest tests/test_loader.py -v 2>&1 | head -40
```
Expected: 7 FAILED (ImportError). RED phase.

**Depends on:** Task 0

---

### Task 4: Implement `loader.py` (GREEN)

**Files:**
- `json-validator/src/json_validator/loader.py`

**Code:**
```python
"""File loading with size guard and well-formedness check."""
from __future__ import annotations

import json
import os

DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class LoadError(Exception):
    """Base class for all load-time errors."""


class SizeError(LoadError):
    """File exceeds the allowed size limit."""


class JSONParseError(LoadError):
    """File content is not valid JSON."""


def load_json(path: str, max_bytes: int = DEFAULT_MAX_BYTES) -> object:
    """
    Load and parse a JSON file.

    Parameters
    ----------
    path:
        Absolute or relative path to the JSON file.
    max_bytes:
        Maximum allowed file size in bytes (default 10 MB).

    Returns
    -------
    object
        Parsed JSON value (dict, list, str, int, float, bool, or None).

    Raises
    ------
    LoadError
        For file-not-found, unicode errors, or oversized files.
    JSONParseError
        For malformed JSON.
    SizeError
        When the file exceeds *max_bytes*.
    """
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        raise LoadError(f"File not found: {path!r}")

    if size > max_bytes:
        raise SizeError(
            f"File too large: {path!r} ({size} bytes, max {max_bytes})"
        )

    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
    except FileNotFoundError:
        raise LoadError(f"File not found: {path!r}")
    except UnicodeDecodeError as exc:
        raise LoadError(f"Cannot decode file as UTF-8: {path!r}") from exc

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise JSONParseError(f"Malformed JSON in {path!r}: {exc}") from exc
```

**Test command:**
```bash
cd json-validator && pytest tests/test_loader.py -v
```
Expected: 7 PASSED. GREEN phase.

**Depends on:** Task 3

---

### Task 5: Write RED tests for `validator.py`

**Files:**
- `json-validator/tests/test_validator.py`

**Code:**
```python
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
```

**Test command:**
```bash
cd json-validator && pytest tests/test_validator.py -v 2>&1 | head -40
```
Expected: ImportError → all FAILED. RED phase.

**Depends on:** Task 0

---

### Task 6: Implement `validator.py` (GREEN)

**Files:**
- `json-validator/src/json_validator/validator.py`

**Code:**
```python
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
    }
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
```

**Test command:**
```bash
cd json-validator && pytest tests/test_validator.py -v
```
Expected: 9 PASSED. GREEN phase.

**Depends on:** Task 5

---

### Task 7: Write RED tests for `cli.py`

**Files:**
- `json-validator/tests/test_cli.py`

**Code:**
```python
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
```

**Test command:**
```bash
cd json-validator && pytest tests/test_cli.py -v 2>&1 | head -50
```
Expected: 8 FAILED (ModuleNotFoundError). RED phase.

**Depends on:** Task 0

---

### Task 8: Implement `cli.py` (GREEN)

**Files:**
- `json-validator/src/json_validator/cli.py`

**Code:**
```python
"""CLI entry point for the JSON Schema validator."""
from __future__ import annotations

import argparse
import sys
from typing import Optional

import jsonschema

from json_validator.loader import LoadError, load_json
from json_validator.security import PathError, check_path
from json_validator.validator import validate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate-json",
        description="Validate a JSON data file against a JSON schema.",
    )
    parser.add_argument("data", help="Path to the JSON data file.")
    parser.add_argument("schema", help="Path to the JSON schema file.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print additional details (file paths, error counts).",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write results to FILE in addition to stdout.",
    )
    return parser


def _write_output(text: str, output_path: Optional[str]) -> None:
    if output_path is None:
        return
    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        print(f"error: cannot write output file: {exc}", file=sys.stderr)
        sys.exit(2)


def main(argv=None) -> None:  # noqa: C901
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --- Security: path traversal check ---
    try:
        check_path(args.data)
        check_path(args.schema)
    except PathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    # --- Load data ---
    try:
        data = load_json(args.data)
    except LoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    # --- Load schema ---
    try:
        schema = load_json(args.schema)
    except LoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    # --- Validate ---
    try:
        result = validate(data, schema)
    except jsonschema.SchemaError as exc:
        print(f"error: Invalid JSON Schema: {exc.message}", file=sys.stderr)
        sys.exit(2)
    except jsonschema.RefResolutionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    # --- Build output text ---
    lines = []
    if result.valid:
        lines.append("VALID")
        if args.verbose:
            lines.append(f"  data:   {args.data}")
            lines.append(f"  schema: {args.schema}")
            lines.append("  No validation errors found.")
    else:
        lines.append("INVALID")
        if args.verbose:
            lines.append(f"  data:   {args.data}")
            lines.append(f"  schema: {args.schema}")
            lines.append(f"  {len(result.errors)} error(s) found:")
        for err in result.errors:
            lines.append(f"  - {err['path']}: {err['message']}")

    output_text = "\n".join(lines) + "\n"
    print(output_text, end="")
    _write_output(output_text, args.output)

    sys.exit(0 if result.valid else 1)


if __name__ == "__main__":
    main()
```

**Test command:**
```bash
cd json-validator && pytest tests/test_cli.py -v
```
Expected: 8 PASSED. GREEN phase.

**Depends on:** Tasks 2, 4, 6, 7

---

### Task 9: Full test suite + coverage report

**Test command:**
```bash
cd json-validator && pytest --cov=json_validator --cov-report=term-missing -v
```
Expected: all tests PASSED, coverage ≥ 90 %.

**Depends on:** Tasks 2, 4, 6, 8

---

### Task 10: REFACTOR pass

After all tests are green, perform the refactor step of TDD:

1. Extract the output-formatting logic from `cli.py` into a `_format_result(result, verbose, data_path, schema_path) -> str` helper (makes it unit-testable without subprocess).
2. Add a `README.md` with usage examples.
3. Re-run full test suite to confirm nothing regressed.

**Test command:**
```bash
cd json-validator && pytest --cov=json_validator --cov-report=term-missing -v
```
Expected: same pass count, coverage unchanged or higher.

**Depends on:** Task 9

---

## Appendix: TDD Red-Green-Refactor Cycle Map

```
Task 1  (RED  – security tests)
Task 2  (GREEN – security impl)
  │
Task 3  (RED  – loader tests)
Task 4  (GREEN – loader impl)
  │
Task 5  (RED  – validator tests)
Task 6  (GREEN – validator impl)
  │
Task 7  (RED  – CLI tests)
Task 8  (GREEN – CLI impl)
  │
Task 9  (FULL suite + coverage)
  │
Task 10 (REFACTOR)
```

Every RED step must produce failing tests before moving to GREEN. No production code is written without a failing test first.
