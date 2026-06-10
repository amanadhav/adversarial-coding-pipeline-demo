"""CLI entry point for the JSON Schema validator."""
from __future__ import annotations

import argparse
import sys
from typing import Optional

import jsonschema

from json_validator.loader import LoadError, load_json
from json_validator.security import PathError, check_path
from json_validator.validator import ValidationResult, validate


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


def _format_result(
    result: ValidationResult,
    verbose: bool,
    data_path: str,
    schema_path: str,
) -> str:
    """Format a ValidationResult into a human-readable string."""
    lines = []
    if result.valid:
        lines.append("VALID")
        if verbose:
            lines.append(f"  data:   {data_path}")
            lines.append(f"  schema: {schema_path}")
            lines.append("  No validation errors found.")
    else:
        lines.append("INVALID")
        if verbose:
            lines.append(f"  data:   {data_path}")
            lines.append(f"  schema: {schema_path}")
            lines.append(f"  {len(result.errors)} error(s) found:")
        for err in result.errors:
            lines.append(f"  - {err['path']}: {err['message']}")
    return "\n".join(lines) + "\n"


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
    except RecursionError:
        print("error: Schema contains a recursive $ref cycle", file=sys.stderr)
        sys.exit(2)

    # --- Build and emit output ---
    output_text = _format_result(result, args.verbose, args.data, args.schema)
    print(output_text, end="")
    _write_output(output_text, args.output)

    sys.exit(0 if result.valid else 1)


if __name__ == "__main__":
    main()
