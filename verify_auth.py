#!/usr/bin/env python3
"""Verifies the /api/signup and /api/signin endpoints in server.py.

Requires a running instance of server.py (stdlib only, no dependencies):

    python server.py 8123
    python verify_auth.py [base_url]

Exercises: signup, sign-in with an unrecognized email, sign-in with the
right email but wrong password, and a successful sign-in. Exits non-zero
if any check fails.
"""
import json
import secrets
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8123"


def post_json(base_url, path, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            data = json.loads(e.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
    return status, data


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" ({detail})" if detail and not condition else ""))
    return condition


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    email = f"verify-{secrets.token_hex(6)}@example.com"
    password = "correct-horse-battery"
    wrong_password = "wrong-password"
    ok = True

    try:
        urllib.request.urlopen(base_url + "/", timeout=5)
    except urllib.error.URLError as e:
        print(f"Could not reach {base_url} — start it first with: python server.py")
        print(f"  ({e})")
        sys.exit(2)

    status, data = post_json(base_url, "/api/signup", {"email": email, "password": password})
    ok &= check("signup succeeds for a new account", status == 200 and data.get("ok") is True, f"status={status} data={data}")

    status, data = post_json(base_url, "/api/signin", {"email": "nobody-" + secrets.token_hex(4) + "@example.com", "password": password})
    ok &= check("signin rejects an unrecognized email", data.get("ok") is False and data.get("code") == "no_account", f"status={status} data={data}")

    status, data = post_json(base_url, "/api/signin", {"email": email, "password": wrong_password})
    ok &= check("signin rejects the wrong password", data.get("ok") is False and data.get("code") == "bad_password", f"status={status} data={data}")

    status, data = post_json(base_url, "/api/signin", {"email": email, "password": password})
    ok &= check("signin succeeds with the right email and password", status == 200 and data.get("ok") is True and data.get("code") == "success", f"status={status} data={data}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
