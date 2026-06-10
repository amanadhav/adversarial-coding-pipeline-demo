"""Tests for the deterministic safety gate."""
import pytest
from safety_gate import scan

# P1 tests - must block
def test_blocks_rm_rf_root():
    assert any(f["severity"] == "P1" for f in scan("os.system('rm -rf /')"))

def test_blocks_rm_rf_home():
    assert any(f["severity"] == "P1" for f in scan("subprocess.run('rm -rf ~', shell=True)"))

def test_blocks_drop_table():
    assert any(f["severity"] == "P1" for f in scan("cursor.execute('DROP TABLE users')"))

def test_blocks_hardcoded_api_key():
    assert any("credential" in f["issue"] for f in scan('api_key = "sk_live_abc12345xyz"'))

def test_blocks_hardcoded_password():
    assert any("credential" in f["issue"] for f in scan('password = "supersecret123"'))

def test_blocks_aws_access_key():
    assert any("AWS" in f["issue"] for f in scan('key = "AKIAIOSFODNN7EXAMPLE"'))

# P2 tests - warn but don't block
def test_flags_eval():
    findings = scan("result = eval(user_input)")
    assert any(f["issue"] == "dynamic code execution via eval" for f in findings)

def test_flags_shell_true():
    findings = scan("subprocess.run(cmd, shell=True)")
    assert any("shell injection" in f["issue"] for f in findings)

def test_flags_tls_disabled():
    findings = scan("requests.get(url, verify=False)")
    assert any("TLS" in f["issue"] for f in findings)

# Clean code passes
def test_clean_function_passes():
    assert scan("def add(a, b):\n    return a + b") == []

def test_clean_class_passes():
    code = """
class Calculator:
    def multiply(self, x, y):
        return x * y
"""
    assert scan(code) == []

# Line number accuracy
def test_line_numbers_correct():
    findings = scan("x = 1\npassword = 'supersecret123abc'")
    assert findings[0]["line"] == 2

# Multiple violations detected
def test_multiple_violations_all_found():
    code = 'api_key = "sk_live_abc123xyz"\nresult = eval(user_input)'
    findings = scan(code)
    assert len(findings) >= 2

# P1 violations block, P2 do not (in terms of exit behavior)
def test_p1_present_in_blocked_result():
    findings = scan('secret_key = "mysecretkey123456"')
    p1s = [f for f in findings if f["severity"] == "P1"]
    assert len(p1s) > 0