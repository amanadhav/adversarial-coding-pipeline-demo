# Review Report: JSON Schema Validator CLI

**Reviewer:** reviewer subagent  
**Date:** review cycle 1  
**Phases:** spec-compliance → adversarial-review → qa-verification

---

## Phase 1 — Spec Compliance

### Module Existence

| Check | Result |
|---|---|
| `security.py` exists | ✅ PASS |
| `loader.py` exists | ✅ PASS |
| `validator.py` exists | ✅ PASS |
| `cli.py` exists | ✅ PASS |

### Exit Codes

| Check | Result | Evidence |
|---|---|---|
| Exit 0 on valid | ✅ PASS | `cli.py:112` — `sys.exit(0 if result.valid else 1)` |
| Exit 1 on invalid | ✅ PASS | same expression |
| Exit 2 on operational error | ✅ PASS | `cli.py:77, 84, 91, 95, 102, 105` |

### Error Table Coverage (Part 5 of design doc)

| # | Failure | Implemented | Notes |
|---|---|---|---|
| 1 | Recursive `$ref` DoS | ⚠️ PARTIAL | Remote refs blocked, but `{"$ref":"#"}` self-ref causes `RecursionError` → exits 1, not 2. See P1 finding. |
| 2 | File > 10 MB | ✅ PASS | `loader.py:42–45`, `DEFAULT_MAX_BYTES = 10 * 1024 * 1024` |
| 3 | Path traversal | ⚠️ PARTIAL | `..` in literal path is caught. `file://` ref bypass exists. See P1/P2 findings. |
| 4 | Malformed data JSON | ✅ PASS | `loader.py:56–57`, `JSONParseError` |
| 5 | Malformed schema | ✅ PASS | `validator.py:52`, `check_schema()` → `SchemaError` |
| 6 | Missing file | ✅ PASS | `loader.py:38–39`, `LoadError` |
| 7 | Empty file | ✅ PASS | `loader.py:56–57`, `JSONParseError` |
| 8 | Unicode error | ✅ PASS | `loader.py:50–51`, `encoding="utf-8"`, `UnicodeDecodeError` caught |
| 9 | Data fails schema | ✅ PASS | `validator.py:55–63`, `iter_errors()` → `ValidationResult` |

### Security Guards

| Check | Result | Evidence |
|---|---|---|
| Path traversal guard before file I/O | ✅ PASS | `cli.py:69–73` calls `check_path()` on both args before `load_json()` |
| Size guard uses `MAX_BYTES` | ✅ PASS | `loader.py:24` `DEFAULT_MAX_BYTES = 10 * 1024 * 1024`; used at `loader.py:41` |
| Remote `$ref` blocked (http/https/ftp) | ✅ PASS | `validator.py:29–35` handlers for `http`, `https`, `ftp` |
| Remote `$ref` blocked (`file://`) | ❌ FAIL | `file` scheme NOT in handlers. A `$ref` to `"file:///path/to/local.json"` resolves successfully. |

### Task 10 Refactor: `_format_result()` helper

| Check | Result | Evidence |
|---|---|---|
| `_format_result()` extracted | ✅ PASS | `cli.py:36–54` |

### CLI Flags

| Check | Result | Evidence |
|---|---|---|
| `--verbose` flag | ✅ PASS | `cli.py:24–28`, `_format_result()` uses `verbose` param |
| `--output` flag | ✅ PASS | `cli.py:29–32`, `_write_output()` at `cli.py:57–65` |

### Design Doc Deviations (from impl-report)

| Deviation | Acceptable? |
|---|---|
| `pyproject.toml` build backend: `setuptools.build_meta` (not `backends.legacy:build`) | ✅ Yes — design doc had invalid value |
| `test_oversized_file_raises_size_error` `max_bytes=1` instead of `10` | ✅ Yes — design doc had a bug |
| `_format_result()` extracted during Task 8 not as post-hoc refactor | ✅ Yes — functionally equivalent |
| 5 extra CLI tests to hit coverage target | ✅ Yes — additive only |
| `JSON_VALIDATOR_MAX_BYTES` env var not implemented | ⚠️ SPEC GAP — design doc Part 7 states: "configurable via env var `JSON_VALIDATOR_MAX_BYTES`". Neither `loader.py` nor `cli.py` reads this env var. |

### Phase 1 Verdict: **SPEC_GAPS**

Two gaps require attention:
1. `file://` `$ref` URIs are not blocked (security requirement in design Part 7, failure mode #1 in Part 5).
2. `JSON_VALIDATOR_MAX_BYTES` env var is not implemented (design Part 7).

---

## Phase 2 — Adversarial Review

### Adversarial Findings

---

**[P1] `file://` URI in `$ref` is not blocked — arbitrary local file read**  
File: `src/json_validator/validator.py:29–35`  
Attack: Attacker supplies a schema with `{"$ref": "file:///etc/passwd"}` or `{"$ref": "file:///C:/Windows/System32/config/SAM"}`. The `_make_local_only_resolver` only blocks `http`, `https`, and `ftp`. The `file` scheme has no handler, so `jsonschema.RefResolver` falls through to Python's `urllib.request.urlopen`, which successfully reads local files and loads them as schemas.  
Evidence: Verified manually — `validate('test', {"$ref": "file:///path/to/local.json"})` resolves the file and validates against it. Exit code is 0 (not 2).  
Impact: Any local file the process user can read is opened, its contents parsed as JSON, and used as a schema. This is an arbitrary file read primitive for any user who can pass a schema file to the CLI. In a CI pipeline context, secrets files, SSH keys in JSON format, or sensitive configs can be exfiltrated.  
Fix: Add `"file"` to the handlers dict in `_make_local_only_resolver`:
```python
handlers = {
    "http": _raise_on_remote,
    "https": _raise_on_remote,
    "ftp": _raise_on_remote,
    "file": _raise_on_remote,   # ADD THIS
}
```

---

**[P1] Self-referencing `$ref` (`{"$ref": "#"}`) causes unhandled `RecursionError` — wrong exit code**  
File: `src/json_validator/cli.py:97–105`, `src/json_validator/validator.py:55`  
Attack: Attacker supplies a schema containing `{"$ref": "#"}` (or any cycle that resolves locally). `validator.py`'s `for err in validator.iter_errors(data)` recurses infinitely until Python's default recursion limit (1000) is hit.  
Evidence: Verified — CLI exits with code **1** (via the Python interpreter printing an unhandled `RecursionError` traceback to stderr and calling `sys.exit(1)` implicitly). Spec requires exit code **2** for operational errors.  
Impact: (1) Wrong exit code signals "invalid data" to CI pipelines instead of "operational error", causing incorrect behaviour. (2) Full Python traceback is dumped to stderr — information leakage. (3) Potential DoS if invoked repeatedly.  
Fix: Catch `RecursionError` in `cli.py`'s validate block:
```python
except RecursionError:
    print("error: Schema contains a recursive $ref cycle", file=sys.stderr)
    sys.exit(2)
```

---

**[P2] TOCTOU race condition in size guard**  
File: `src/json_validator/loader.py:37–45`  
Attack: `os.path.getsize(path)` is called, then `open(path)` is called separately. Between these two calls, an attacker with write access to the same filesystem location can replace the file with a much larger one. The oversized file will then be fully read into memory.  
Risk: Memory exhaustion on constrained CI runners — the exact DoS scenario the size guard was designed to prevent.  
Fix: Open the file first, seek to end to get size, then seek back:
```python
try:
    with open(path, encoding="utf-8") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        if size > max_bytes:
            raise SizeError(...)
        fh.seek(0)
        content = fh.read()
except FileNotFoundError:
    raise LoadError(...)
```
This is atomic with respect to the file being replaced after the size check.

---

**[P2] UNC paths not blocked on Windows**  
File: `src/json_validator/security.py:16–20`  
Attack: On Windows, `\\server\share\file.json` (UNC path) has no `..` components but accesses network shares. `check_path` passes it without error.  
Evidence: Verified — `check_path(r"\\server\share\file.json")` raises no exception.  
Risk: Network file access from CI agents to attacker-controlled SMB shares. Potential for NTLM credential capture (Responder-style attacks) or reading files from internal network locations.  
Fix: Detect UNC paths explicitly:
```python
if path.startswith("\\\\") or path.startswith("//"):
    raise PathError(f"Disallowed path (UNC/network path): {path!r}")
```

---

**[P2] `JSON_VALIDATOR_MAX_BYTES` env var not implemented**  
File: `src/json_validator/loader.py:24`  
Risk: Design doc (Part 7) explicitly states the 10 MB limit is "configurable via env var `JSON_VALIDATOR_MAX_BYTES`". This is not implemented. Any operator needing to lower the limit for constrained environments (e.g., 1 MB for a serverless runner) cannot do so without modifying source.  
Fix:
```python
import os
DEFAULT_MAX_BYTES = int(os.environ.get("JSON_VALIDATOR_MAX_BYTES", 10 * 1024 * 1024))
```

---

**[P3] URL-encoded path traversal not decoded**  
File: `src/json_validator/security.py`  
Risk: `check_path("%2e%2e%2f%2e%2e%2fetc%2fpasswd")` passes without error. The path does not contain literal `..`, so the guard misses it. However, `open()` on CPython does not automatically URL-decode paths, so the file open would fail with `FileNotFoundError` — this is a contained risk, not exploitable in isolation.  
Suggestion: Add URL-decode normalisation before the `..` check:
```python
import urllib.parse
path = urllib.parse.unquote(path)
```

---

**[P3] `RefResolver` deprecation — functional risk on library upgrade**  
File: `src/json_validator/validator.py:34`  
Risk: `jsonschema.RefResolver` is deprecated as of v4.18.0. The `handlers=` mechanism that powers the remote-ref block will not exist in the successor `referencing` library. When `jsonschema` eventually removes `RefResolver` (it's already raising `DeprecationWarning`), the entire security barrier disappears silently.  
Suggestion: Pin `jsonschema==4.23.0` (already done in `pyproject.toml`) and add a comment noting migration to `referencing.Registry` is required before any version upgrade.

---

**[P3] `stdin` as `-` not supported but error message is unhelpful**  
File: `src/json_validator/cli.py` / `src/json_validator/loader.py`  
Risk: Passing `-` as a file path gives `error: File not found: '-'` rather than a clear message like `stdin input is not supported`. Users familiar with UNIX convention of `-` for stdin will be confused.  
Suggestion: Add an explicit check in `check_path` or `load_json` for the value `"-"` and emit a clear "stdin is not supported" message.

---

**[P3] `--output` path has no parent-directory existence check before writing**  
File: `src/json_validator/cli.py:57–65`  
Risk: Design doc (Part 7) says "check that the parent directory exists and is writable before writing." The current implementation just `open(output_path, "w")` and catches `OSError`. This is functionally fine (OSError will be caught), but the error message will be the raw `OSError` string, not a user-friendly one.  
Suggestion: Pre-validate parent dir: `os.path.isdir(os.path.dirname(output_path))` for a better error message.

---

## Phase 3 — QA Verification

### Test Suite Results

```
33 passed, 0 failed, 9 warnings in 8.27s
```

**All 33 tests pass.**

### Coverage

```
Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
src\json_validator\__init__.py        0      0   100%
src\json_validator\cli.py            73      3    96%   103-105
src\json_validator\loader.py         25      1    96%   61
src\json_validator\security.py        9      0   100%
src\json_validator\validator.py      27      0   100%
---------------------------------------------------------------
TOTAL                               134      4    97%
```

Coverage target was ≥ 90%. Achieved **97%**. ✅

**Uncovered lines:**
- `cli.py:103–105` — `RefResolutionError` handler. This branch is genuinely hard to reach via subprocess because `SchemaError` takes priority in the error chain. The self-ref `RecursionError` bug (P1) means this path is never reached for the one schema that would naturally trigger it. Not blocking.
- `loader.py:61` — second `FileNotFoundError` guard after `getsize`. Unreachable (belt-and-suspenders). Acceptable.

### Design Doc Test Matrix Coverage

| Test ID | Description | Status |
|---|---|---|
| S-01 | `check_path` traversal `../../etc/passwd` → `PathError` | ✅ PASS |
| S-02 | `check_path` safe path → no exception | ✅ PASS |
| L-01 | `load_json` file > max → `SizeError` | ✅ PASS |
| L-02 | `load_json` missing file → `LoadError` | ✅ PASS |
| L-03 | `load_json` `{}` → returns `{}` | ✅ PASS |
| L-04 | `load_json` empty file → `JSONParseError` | ✅ PASS |
| L-05 | `load_json` Unicode content → returns dict | ✅ PASS |
| L-06 | `load_json` bad JSON → `JSONParseError` | ✅ PASS |
| V-01 | `validate` valid data → `valid=True, errors=[]` | ✅ PASS |
| V-02 | `validate` invalid data → `valid=False, errors non-empty` | ✅ PASS |
| V-03 | `validate` bad schema → `SchemaError` | ✅ PASS |
| V-04 | `validate` remote `$ref` → `RefResolutionError` | ✅ PASS (http/https blocked) |
| V-05 | `validate` 10-level nested schema → returns result | ✅ PASS |
| C-01 | CLI valid pair → stdout "VALID", exit 0 | ✅ PASS |
| C-02 | CLI invalid pair → stdout "INVALID" + errors, exit 1 | ✅ PASS |
| C-03 | CLI missing data file → stderr message, exit 2 | ✅ PASS |
| C-04 | CLI `--output` valid → file written, exit 0 | ✅ PASS |
| C-05 | CLI `--verbose` → extra info in output | ✅ PASS |
| C-06 | CLI `--output /nonexistent/path/out.txt` → stderr, exit 2 | ✅ PASS |

### Smoke Tests

| Test | Result |
|---|---|
| Valid pair: `exit 0`, stdout `VALID` | ✅ PASS |
| Invalid pair: `exit 1`, stdout `INVALID\n  - $.age: ...\n  - $: 'name' is a required property` | ✅ PASS |
| `--verbose` valid: `exit 0`, includes `data:`, `schema:`, `No validation errors found.` | ✅ PASS |
| `--output result.txt`: `exit 0`, file exists, contains `VALID` | ✅ PASS |

### Edge Cases from Design Doc

| Edge Case | Covered in Tests? |
|---|---|
| Malicious recursive `$ref` (remote) | ✅ `test_remote_ref_raises_ref_resolution_error` |
| Malicious recursive `$ref` (local self-ref) | ❌ NOT TESTED — discovered as P1 bug above |
| Large file > 10 MB | ✅ `test_oversized_file_raises_size_error` |
| Path traversal | ✅ `test_traversal_dotdot_rejected`, `test_path_traversal_exits_2` |
| `file://` `$ref` bypass | ❌ NOT TESTED — discovered as P1 bug above |
| UNC path bypass | ❌ NOT TESTED — P2 finding |
| Unicode content | ✅ `test_unicode_content_loaded_correctly` |
| Unicode decode error | ✅ `test_unicode_decode_error_raises_load_error` |

---

## Final Assessment

### CHANGES_REQUIRED

The implementation is high quality, well-structured, and passes all 33 tests at 97% coverage. The TDD discipline is evident. However, two P1 security defects require fixes before approval:

**Must fix (P1):**
1. Add `"file"` scheme to `_make_local_only_resolver` handlers — prevents arbitrary local file read via `$ref`.
2. Catch `RecursionError` in `cli.py` validate block — ensures self-referencing schemas produce exit code 2, not an unhandled crash with exit code 1.

**Should fix (P2):**
3. Implement `JSON_VALIDATOR_MAX_BYTES` env var in `loader.py` — specified in design doc Part 7.
4. Block UNC paths in `check_path` — closes Windows-specific network path vector.
5. Address TOCTOU in `loader.py` size guard — open file first, then measure size.

**Suggestions (P3):** URL-encoded path normalisation, deprecation migration note, stdin error message improvement, `--output` parent-dir pre-check.

Re-review required after P1 fixes.


---

# Re-Review: Cycle 2

**Reviewer:** reviewer subagent (re-review)  
**Date:** review cycle 2  
**Scope:** Verification of P1/P2/P3 fixes from cycle 1

---

## Fix Verification

### P1-FIX-1 — `file` scheme added to `_make_local_only_resolver` handlers in `validator.py`

**PASS**

Evidence:
- `validator.py` lines 30–35: `handlers` dict now contains `"file": _raise_on_remote` alongside `http`, `https`, `ftp`.
- Comment present: `# block local file reads via $ref`
- Test `test_file_ref_raises_ref_resolution_error` in `test_validator.py` exercises the fix and passes.

```python
handlers = {
    "http": _raise_on_remote,
    "https": _raise_on_remote,
    "ftp": _raise_on_remote,
    "file": _raise_on_remote,   # block local file reads via $ref
}
```

---

### P1-FIX-2 — `RecursionError` caught in `cli.py` validate block with `sys.exit(2)`

**PASS**

Evidence:
- `cli.py` lines 94–99 contain:
```python
except RecursionError:
    print("error: Schema contains a recursive $ref cycle", file=sys.stderr)
    sys.exit(2)
```
- Test `test_self_ref_schema_exits_2` in `test_cli.py` passes: schema `{"$ref": "#"}` → exit code 2. ✅

---

### P2-FIX-3 — `JSON_VALIDATOR_MAX_BYTES` env var implemented in `loader.py`

**PASS**

Evidence:
- `loader.py` line 6:
```python
DEFAULT_MAX_BYTES = int(os.environ.get("JSON_VALIDATOR_MAX_BYTES", 10 * 1024 * 1024))  # 10 MB default
```
- `import os` is present at the top of the module.
- The default (10 MB) is unchanged; operators can override via the env var before import.

---

### P2-FIX-4 — UNC path detection added to `security.py` `check_path()`

**PASS**

Evidence:
- `security.py` lines 14–16:
```python
normalised_fwd = path.replace("\\", "/")
if normalised_fwd.startswith("//"):
    raise PathError(f"Disallowed path (network path): {path!r}")
```
- Correctly normalises Windows `\\server\share` → `//server/share` before the prefix check, so both forms are caught.
- Two new tests pass:
  - `test_unc_path_rejected` — `r"\\server\share\file.json"` → `PathError` ✅
  - `test_unix_double_slash_rejected` — `"//server/share/file.json"` → `PathError` ✅

---

### P2-FIX-5 — TOCTOU race fixed in `loader.py` — single open + seek replaces `getsize` + `open`

**PASS**

Evidence:
- `loader.py` uses a single `with open(path, ...) as fh:` block. Inside:
  1. `fh.seek(0, 2)` — seek to end
  2. `size = fh.tell()` — get file size
  3. Size guard: `if size > max_bytes: raise SizeError(...)`
  4. `fh.seek(0)` — seek back
  5. `content = fh.read()` — read content
- No separate `os.path.getsize()` call exists anywhere in the file.
- Comment: `# Measure size atomically with the open — eliminates TOCTOU race`
- `loader.py` coverage improved to **100%** (the previously unreachable belt-and-suspenders `FileNotFoundError` guard at old line 61 no longer exists).

---

### P3-FIX-6 — `RefResolver` deprecation comment added in `validator.py`

**PASS**

Evidence:
- `validator.py` lines 36–37:
```python
# NOTE: jsonschema.RefResolver is deprecated since v4.18.0.
# Migrate to referencing.Registry before upgrading jsonschema past v4.x.
```
- Comment is accurate and actionable. `jsonschema` is pinned in `pyproject.toml`.

---

## Test Results

```
37 passed, 0 failed, 11 warnings in 7.43s
```

All 37 tests pass. 4 new tests were added since cycle 1 (covering the UNC path, `file://` ref, and self-ref schema fixes).

### Full Test List (37)

| Module | Tests |
|---|---|
| `test_cli.py` | 14 tests — all PASSED |
| `test_loader.py` | 7 tests — all PASSED |
| `test_security.py` | 6 tests — all PASSED |
| `test_validator.py` | 10 tests — all PASSED |

---

## Coverage

```
Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
src\json_validator\__init__.py        0      0   100%
src\json_validator\cli.py            76      2    97%   104-105
src\json_validator\loader.py         24      0   100%
src\json_validator\security.py       12      0   100%
src\json_validator\validator.py      27      0   100%
---------------------------------------------------------------
TOTAL                               139      2    99%
```

Coverage target was ≥ 90%. Achieved **99%**. ✅

**Remaining uncovered lines:**
- `cli.py:104–105` — the `RecursionError` handler body (`print(...)` and `sys.exit(2)` lines). The handler is exercised via subprocess in `test_self_ref_schema_exits_2`, but coverage instrumentation does not capture subprocess execution. The handler is correctly placed and tested behaviourally. Not blocking.

---

## Warnings

11 `DeprecationWarning`s from `jsonschema` regarding `RefResolver` and `RefResolutionError`. These are expected, acknowledged by P3-FIX-6's comment, and pinned by `pyproject.toml`. Not blocking.

---

## Fix Summary Table

| ID | Finding | Severity | Status | Evidence |
|---|---|---|---|---|
| P1-FIX-1 | `file` scheme blocked in `_make_local_only_resolver` | P1 | ✅ PASS | `validator.py:34`, `test_file_ref_raises_ref_resolution_error` passes |
| P1-FIX-2 | `RecursionError` → exit 2 in `cli.py` | P1 | ✅ PASS | `cli.py:94–99`, `test_self_ref_schema_exits_2` passes |
| P2-FIX-3 | `JSON_VALIDATOR_MAX_BYTES` env var in `loader.py` | P2 | ✅ PASS | `loader.py:6`, `os.environ.get()` present |
| P2-FIX-4 | UNC path detection in `security.py` | P2 | ✅ PASS | `security.py:14–16`, 2 new tests pass |
| P2-FIX-5 | TOCTOU race eliminated in `loader.py` | P2 | ✅ PASS | Single `open()`+seek pattern, 100% loader coverage |
| P3-FIX-6 | `RefResolver` deprecation comment in `validator.py` | P3 | ✅ PASS | `validator.py:36–37` |

---

## Remaining Open Items (from cycle 1, not required for approval)

These P3 suggestions were not required to be fixed in this cycle and remain open:

| ID | Description | Status |
|---|---|---|
| P3-a | URL-encoded path traversal (`%2e%2e`) not decoded in `check_path` | OPEN (low exploitability — `open()` does not URL-decode) |
| P3-b | `stdin` as `-` gives unhelpful "File not found" error | OPEN |
| P3-c | `--output` parent-dir existence not pre-validated (raw `OSError`) | OPEN |

---

## Final Assessment

### ✅ APPROVED

All 6 required fixes from cycle 1 are correctly implemented and verified. The two P1 security defects (arbitrary local file read via `file://` `$ref` and wrong exit code on recursive schema) are resolved. All P2 hardening items (env var config, UNC path blocking, TOCTOU fix) are in place. The P3 deprecation note is documented.

- **37 / 37 tests pass**
- **99% coverage** (target ≥ 90%)
- **No regressions** from cycle 1 baseline (was 33 tests / 97%)
- Code is clean, well-commented, and matches the design document

The implementation is approved for merge.
