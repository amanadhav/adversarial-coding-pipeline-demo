# json-validator

A deterministic CLI tool to validate JSON data files against a JSON Schema.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```bash
validate-json data.json schema.json
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | Data is valid — conforms to the schema |
| `1`  | Data is **invalid** — one or more schema violations found |
| `2`  | Operational error — missing file, malformed JSON, bad schema, etc. |

### Options

```
positional arguments:
  data           Path to the JSON data file
  schema         Path to the JSON schema file

options:
  --verbose      Print extra details: file paths and error counts
  --output FILE  Write results to FILE in addition to stdout
```

## Examples

**Validate a config file:**

```bash
validate-json config.json config-schema.json
# VALID
echo $?  # 0
```

**See validation errors with field paths:**

```bash
validate-json bad-data.json schema.json
# INVALID
#   - $.age: 'not-an-int' is not of type 'integer'
#   - $: 'name' is a required property
echo $?  # 1
```

**Verbose output:**

```bash
validate-json data.json schema.json --verbose
# VALID
#   data:   data.json
#   schema: schema.json
#   No validation errors found.
```

**Write results to a file (for CI):**

```bash
validate-json data.json schema.json --output results.txt
cat results.txt
# VALID
```

## Security

- Files > 10 MB are rejected (configurable via `JSON_VALIDATOR_MAX_BYTES` env var).
- Path traversal sequences (`..`) in file arguments are rejected.
- Remote `$ref` URIs in schemas are blocked — only local schemas are allowed.

## Development

```bash
# Run tests
pytest -v

# Run tests with coverage
pytest --cov=json_validator --cov-report=term-missing -v
```

## Project structure

```
json-validator/
├── pyproject.toml
├── README.md
├── src/
│   └── json_validator/
│       ├── __init__.py
│       ├── cli.py        # argparse entry point
│       ├── loader.py     # file I/O, size guard, JSON parse
│       ├── validator.py  # jsonschema validation, error formatting
│       └── security.py  # path-traversal check, $ref resolver
└── tests/
    ├── conftest.py
    ├── test_cli.py
    ├── test_loader.py
    ├── test_validator.py
    └── test_security.py
```
