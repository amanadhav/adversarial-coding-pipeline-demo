# Adversarial Coding Pipeline Demo

A production-quality Python CLI built by running a multi-agent adversarial
coding pipeline. The pipeline (architect → TDD coder → 3-phase adversarial
reviewer) caught 2 P1 security defects and 3 P2 issues the initial
implementation missed, all resolved in 1 review cycle.

## What the pipeline caught

| Severity | Finding | Fix |
|----------|---------|-----|
| P1 | Arbitrary local file read via file:// URI in JSON Schema \ | Added file scheme to RefResolver block list |
| P1 | RecursionError on self-referencing \ produced wrong exit code (1 not 2) | Caught RecursionError → sys.exit(2) |
| P2 | TOCTOU race in file size guard | Single open()+seek() instead of getsize()+open() |
| P2 | UNC path bypass on Windows | Added // prefix check before traversal check |
| P2 | JSON_VALIDATOR_MAX_BYTES env var missing | os.environ.get() with 10MB default |

## Result
37/37 tests passing, 99% coverage, APPROVED after 1 review cycle.

## Pipeline artifacts
- .pipeline/design-doc.md — architect's locked design before any code was written
- .pipeline/impl-report.md — coder's TDD implementation report
- .pipeline/review-report.md — full adversarial review with P1/P2/P3 findings

## Built with
DDT Agent Pipeline Forge (used with explicit permission from author
Chandi Cumaranatunge, ASU Enterprise Technology).
Safety gate extension: coming next.
