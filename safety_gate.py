"""
Deterministic safety gate for multi-agent coding pipelines.

The LLM is never the security boundary. This pure function is.
Scans generated code BEFORE delivery. No AI. No model. No bypass.

Extends the DDT Adversarial Coding Pipeline with a deterministic
enforcement layer — the same philosophy as AllVoice's Ethics Logic Gate.
"""
import re
import sys
import json

DANGEROUS_PATTERNS = [
    # Destructive commands
    (r"rm\s+-rf\s+[/~\\]", "P1", "destructive filesystem command"),
    (r"DROP\s+(TABLE|DATABASE)", "P1", "destructive SQL"),
    (r":()\s*\{\s*:\|:&\s*\};:", "P1", "fork bomb"),
    # Hardcoded credentials
    (r"(api[_-]?key|secret[_-]?key|password|token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{8,}['\"]",
     "P1", "hardcoded credential"),
    (r"AKIA[0-9A-Z]{16}", "P1", "AWS access key ID"),
    # PII patterns
    (r"\b\d{3}-\d{2}-\d{4}\b", "P2", "SSN pattern"),
    # Unsafe execution
    (r"\beval\s*\(", "P2", "dynamic code execution via eval"),
    (r"\bexec\s*\(", "P2", "dynamic code execution via exec"),
    (r"shell\s*=\s*True", "P2", "shell injection surface"),
    (r"verify\s*=\s*False", "P2", "TLS verification disabled"),
]

def scan(code: str) -> list[dict]:
    """Scan code for dangerous patterns. Returns list of findings."""
    findings = []
    for pattern, severity, description in DANGEROUS_PATTERNS:
        for match in re.finditer(pattern, code, re.IGNORECASE):
            line = code[:match.start()].count("\n") + 1
            findings.append({
                "severity": severity,
                "line": line,
                "issue": description,
                "match": match.group(0)[:50]  # truncate for safety
            })
    return findings

def main():
    """
    Read code from stdin, scan it, print findings as JSON.
    Exit 2 (block) if any P1 violations found.
    Exit 0 (pass) if clean or only P2/P3 findings.
    """
    code = sys.stdin.read()
    findings = scan(code)
    p1s = [f for f in findings if f["severity"] == "P1"]

    result = {
        "blocked": bool(p1s),
        "p1_count": len(p1s),
        "p2_count": len([f for f in findings if f["severity"] == "P2"]),
        "findings": findings
    }

    print(json.dumps(result, indent=2))

    if p1s:
        print(
            f"\nSAFETY GATE BLOCKED: {len(p1s)} P1 violation(s) found.",
            file=sys.stderr
        )
        sys.exit(2)  # Same convention as the pipeline's hook scripts

if __name__ == "__main__":
    main()