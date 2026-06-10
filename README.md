# Adversarial Coding Pipeline Demo

A multi-agent pipeline that builds a production-quality JSON validator using four
specialized subagents — Architect, Coder, Reviewer, and a deterministic Safety Gate —
built on the [DDT Agent Pipeline Forge](https://github.com/chandich/ddt-pipeline-forge)
(used with permission from Chandi Cumaranatunge, ASU Enterprise Technology).

## How it works

```
Feature Request
      │
      ▼
 ORCHESTRATOR
      │
      ├──▶ ARCHITECT  ──  plans the design, produces a locked doc,
      │                   waits for human approval before any code is written
      │
      ├──▶ CODER  ──  strict TDD: writes failing tests first,
      │               then implements against the locked design
      │
      ├──▶ REVIEWER  ──  3-phase adversarial review:
      │      │              1. spec compliance
      │      │              2. attacker mindset (edge cases, races, injections)
      │      │              3. QA verification
      │      │
      │      ├── CHANGES_REQUIRED ──▶ back to CODER (max 3 cycles)
      │      └── APPROVED
      │                │
      ▼                ▼
 DETERMINISTIC SAFETY GATE  ──  pure Python, no LLM, no bypass
      │
      ├── Exit 2  ──  BLOCKED (P1 violations found)
      └── Exit 0  ──  DELIVER
```

The key distinction: the Reviewer *reasons* about security. The Safety Gate *enforces* it.
Both layers are necessary — the reviewer catches design flaws and logic bugs; the gate
catches hardcoded secrets, destructive commands, and PII patterns deterministically,
regardless of what the model concluded.

> The agent proposes. Deterministic policy disposes.

This is the same philosophy as the Ethics Logic Gate in [AllVoice](https://github.com/amana/allvoice)
(a voice-controlled browser agent built at the Kiro Spark Challenge), extended from a
single-agent pipeline to a full multi-agent system.

## What the pipeline built

A pip-installable CLI tool — `validate-json` — that validates JSON data files against a
JSON Schema, with correct exit codes, field-path error messages, and hardened security.

```bash
cd json-validator
pip install -e ".[dev]"

validate-json data.json schema.json         # exits 0 (valid), 1 (invalid), 2 (error)
validate-json data.json schema.json --verbose
validate-json data.json schema.json --output results.txt
```

See [`json-validator/README.md`](json-validator/README.md) for full usage docs.

## What the adversarial review caught

The Reviewer found 5 issues the initial implementation missed:

| Severity | Finding | Fix Applied |
|----------|---------|-------------|
| P1 | Arbitrary local file read via `file://` URI in JSON Schema `$ref` | Added `file` scheme to `RefResolver` block list |
| P1 | `RecursionError` on self-referencing `$ref` produced exit code 1, not 2 | Caught `RecursionError` → `sys.exit(2)` |
| P2 | TOCTOU race in file size guard | Single `open()` + `seek()` eliminates the race |
| P2 | UNC path bypass on Windows (`\\server\share` has no `..` components) | Added `//` prefix check in `check_path()` |
| P2 | `JSON_VALIDATOR_MAX_BYTES` env var not implemented | `os.environ.get()` with 10 MB default |

## What the safety gate enforces

`safety_gate.py` scans generated code before delivery. No AI involved — pure regex,
deterministic, no dependencies beyond the standard library.

| Category | Pattern |
|----------|---------|
| Credentials | `api_key`, `secret_key`, `password`, `token` assigned to string literals |
| AWS keys | `AKIA...` access key ID format |
| Destructive commands | `rm -rf /`, fork bomb |
| Destructive SQL | `DROP TABLE`, `DROP DATABASE` |
| Unsafe execution | `eval(`, `exec(` |
| Shell injection | `shell=True` |
| TLS disabled | `verify=False` |
| PII | SSN patterns (`\d{3}-\d{2}-\d{4}`) |

P1 violations block delivery (exit 2). P2 violations are logged but do not block.

```bash
# Scan any code file through the gate
cat some_file.py | python safety_gate.py
```

## Results

| Component | Tests | Coverage | Outcome |
|-----------|-------|----------|---------|
| `json-validator` | 37 / 37 | 99% | APPROVED after 1 review cycle |
| `safety_gate` | 14 / 14 | 100% | Pure Python, no external deps |

## Pipeline artifacts

All three pipeline artifacts are preserved in `.pipeline/`:

- [`design-doc.md`](.pipeline/design-doc.md) — architect's locked design, produced before any code was written
- [`impl-report.md`](.pipeline/impl-report.md) — coder's TDD report (every test written RED first, then GREEN)
- [`review-report.md`](.pipeline/review-report.md) — full adversarial review with all findings and fix verification

## Project structure

```
acp-demo/
├── safety_gate.py          # deterministic enforcement layer
├── test_safety_gate.py     # 14 tests for the gate
├── .pipeline/
│   ├── design-doc.md
│   ├── impl-report.md
│   └── review-report.md
└── json-validator/         # the artifact the pipeline produced
    ├── pyproject.toml
    ├── src/json_validator/
    │   ├── cli.py          # argparse entry point
    │   ├── loader.py       # file I/O, size guard, JSON parse
    │   ├── validator.py    # jsonschema validation, error formatting
    │   └── security.py     # path-traversal check, $ref resolver
    └── tests/              # 37 tests, 99% coverage
```
