# Adversarial Coding Pipeline Demo

A multi-agent adversarial coding pipeline that caught 2 P1 security
defects the initial implementation missed, extended with a deterministic
safety gate that enforces what no LLM reviewer can guarantee.

## Architecture

\\\
Feature Request
      |
      v
ORCHESTRATOR
      |
      +---> ARCHITECT (plans, locked design doc, human approval gate)
      |
      +---> CODER (TDD: red-green-refactor, implements against design)
      |
      +---> REVIEWER (3-phase adversarial: spec compliance ->
      |               attacker mindset -> QA verification)
      |         |
      |         +-- CHANGES_REQUIRED --> back to CODER (max 3 cycles)
      |         |
      |         +-- APPROVED
      |                  |
      |                  v
      +---> DETERMINISTIC SAFETY GATE (pure Python, no LLM, no bypass)
                         |
                    Exit 2 = BLOCKED
                    Exit 0 = DELIVER
\\\

## The core principle

The LLM reviewer reasons about security. The safety gate enforces it.
These are different layers and both are necessary: the reviewer catches
architectural flaws and logic bugs; the gate catches secrets, destructive
commands, and PII patterns deterministically, regardless of what the
model decided.

The agent proposes. Deterministic policy disposes.

This is the same philosophy as the Ethics Logic Gate in AllVoice
(a voice-controlled browser agent I built at the Kiro Spark Challenge)
- extended from a single-agent pipeline to a multi-agent system.

## What the adversarial review caught

| Severity | Finding | Fix Applied |
|----------|---------|-------------|
| P1 | Arbitrary local file read via file:// URI in JSON Schema \ | Added file scheme to RefResolver block list |
| P1 | RecursionError on self-referencing \ produced exit code 1 not 2 | Caught RecursionError -> sys.exit(2) |
| P2 | TOCTOU race in file size guard | Single open()+seek() eliminates the race |
| P2 | UNC path bypass on Windows (\\server\share has no .. components) | Added // prefix check in check_path() |
| P2 | JSON_VALIDATOR_MAX_BYTES env var not implemented | os.environ.get() with 10MB default |

## What the safety gate catches

- Hardcoded credentials (API keys, passwords, tokens)
- AWS access key IDs (AKIA... pattern)
- Destructive filesystem commands (rm -rf /)
- Destructive SQL (DROP TABLE, DROP DATABASE)
- Unsafe dynamic execution (eval, exec)
- Shell injection surfaces (shell=True)
- TLS verification disabled (verify=False)
- SSN patterns in code

## Results

- json-validator: 37/37 tests, 99% coverage, APPROVED after 1 review cycle
- safety_gate: 14/14 tests, pure Python, deterministic, no external dependencies

## Pipeline artifacts

- .pipeline/design-doc.md - architect's locked design before any code was written
- .pipeline/impl-report.md - coder's TDD implementation report (33 tests RED first)
- .pipeline/review-report.md - full adversarial review with P1/P2/P3 findings and fix verification

## Built with

DDT Agent Pipeline Forge, used with explicit permission from its author
Chandi Cumaranatunge (ASU Enterprise Technology). The safety gate is my
own addition - the ACP's adversarial reviewer uses LLM reasoning to find
security issues; the gate uses deterministic code to enforce them.
Different layer, different guarantee.
