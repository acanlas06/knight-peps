#!/usr/bin/env python3
"""Local dev server for the Knight Labs storefront.

Serves the static site (same behavior as `python -m http.server`) and adds a
small JSON auth API used by account.html:

    POST /api/signup  {"email": "...", "password": "..."}
    POST /api/signin  {"email": "...", "password": "..."}

Accounts are stored locally in accounts.json (gitignored), one record per
email, as a PBKDF2-HMAC-SHA256 hash with a random per-account salt. Plaintext
passwords are never written to disk.

Usage:
    python server.py [port]

Then open http://127.0.0.1:8123/ (or the port you passed).
"""
import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import smtplib
import sys
import threading
import time
from email.message import EmailMessage

ROOT = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(ROOT, "accounts.json")
OUTBOX_DIR = os.path.join(ROOT, "outbox")
PBKDF2_ITERATIONS = 260000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 6
MAX_BODY_BYTES = 10_000

# Password reset tokens
RESET_TOKEN_BYTES = 32
RESET_TOKEN_TTL_SECONDS = 3600  # 1 hour
RESET_MIN_INTERVAL_SECONDS = 60  # throttle repeat requests per account

# Mail delivery.
#
# Credentials are read from smtp-config.json (gitignored) if present, and any
# KL_SMTP_* environment variable overrides the file. With no configuration at
# all, messages are written to ./outbox and the reset link is printed to the
# console — the sane default for local development.
#
# Copy smtp-config.example.json to smtp-config.json and fill it in. The file is
# gitignored so the app password never reaches the repository.
SMTP_CONFIG_FILE = os.path.join(ROOT, "smtp-config.json")


def load_mail_config():
    file_config = {}
    if os.path.exists(SMTP_CONFIG_FILE):
        try:
            with open(SMTP_CONFIG_FILE, "r", encoding="utf-8") as handle:
                raw = handle.read().strip()
            # An empty placeholder file just means "not configured yet".
            loaded = json.loads(raw) if raw else {}
            if isinstance(loaded, dict):
                # Ignore commentary keys so the example file can document itself.
                file_config = {k: v for k, v in loaded.items() if not k.startswith("_")}
            else:
                print(f"[mail] {SMTP_CONFIG_FILE} must contain a JSON object — ignoring", flush=True)
        except json.JSONDecodeError as exc:
            print(f"[mail] Could not parse smtp-config.json ({exc}) — ignoring", flush=True)

    def pick(key, default=""):
        # Environment wins over the file, file wins over the default.
        env = os.environ.get("KL_SMTP_" + key.upper())
        if env not in (None, ""):
            return env
        value = file_config.get(key)
        return default if value in (None, "") else value

    tls = str(pick("tls", "1")).strip().lower() not in ("0", "false", "no", "off")
    try:
        port = int(pick("port", "587"))
    except (TypeError, ValueError):
        port = 587

    return {
        "host": str(pick("host")).strip(),
        "port": port,
        "user": str(pick("user")).strip(),
        "password": str(pick("password")),
        "from": str(pick("from", "no-reply@knightlabs.example")).strip(),
        "tls": tls,
    }


MAIL = load_mail_config()
# Gmail (and most providers) reject a From: that isn't the authenticated user.
if MAIL["host"] and MAIL["user"] and MAIL["from"] == "no-reply@knightlabs.example":
    MAIL["from"] = MAIL["user"]

_lock = threading.Lock()


def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return {}
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_accounts(accounts):
    tmp_path = ACCOUNTS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2)
    os.replace(tmp_path, ACCOUNTS_FILE)


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt, digest


def verify_password(password, salt_hex, hash_hex):
    salt = bytes.fromhex(salt_hex)
    _, digest = hash_password(password, salt)
    return hmac.compare_digest(digest.hex(), hash_hex)


def hash_token(token):
    """Only the digest is stored, so a leaked accounts.json can't be replayed."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset_token(email):
    """Issue a single-use reset token. Returns (token, error_code)."""
    token = secrets.token_urlsafe(RESET_TOKEN_BYTES)
    now = time.time()
    with _lock:
        accounts = load_accounts()
        record = accounts.get(email)
        if not record:
            return None, "no_account"
        previous = record.get("reset")
        if previous and not previous.get("used"):
            issued_at = float(previous.get("issued_at", 0))
            if now - issued_at < RESET_MIN_INTERVAL_SECONDS:
                return None, "throttled"
        record["reset"] = {
            "token_hash": hash_token(token),
            "issued_at": now,
            "expires_at": now + RESET_TOKEN_TTL_SECONDS,
            "used": False,
        }
        accounts[email] = record
        save_accounts(accounts)
    return token, None


def consume_reset_token(token, new_password):
    """Validate a token and rotate the password. Returns an error code or None."""
    digest = hash_token(token)
    now = time.time()
    with _lock:
        accounts = load_accounts()
        target_email = None
        for email, record in accounts.items():
            reset = record.get("reset") or {}
            stored = reset.get("token_hash")
            if stored and hmac.compare_digest(stored, digest):
                target_email = email
                break
        if target_email is None:
            return "invalid_token"

        record = accounts[target_email]
        reset = record["reset"]
        if reset.get("used"):
            return "token_used"
        if now > float(reset.get("expires_at", 0)):
            return "token_expired"

        salt, password_digest = hash_password(new_password)
        record["salt"] = salt.hex()
        record["hash"] = password_digest.hex()
        record["iterations"] = PBKDF2_ITERATIONS
        # Burn the token so the link cannot be reused.
        record["reset"] = {"used": True, "used_at": now}
        accounts[target_email] = record
        save_accounts(accounts)
    return None


def find_reset_email(token):
    """Return the account email a token belongs to if it is still usable."""
    digest = hash_token(token)
    now = time.time()
    with _lock:
        accounts = load_accounts()
    for email, record in accounts.items():
        reset = record.get("reset") or {}
        stored = reset.get("token_hash")
        if not stored or not hmac.compare_digest(stored, digest):
            continue
        if reset.get("used"):
            return None, "token_used"
        if now > float(reset.get("expires_at", 0)):
            return None, "token_expired"
        return email, None
    return None, "invalid_token"


def build_reset_email(to_email, link):
    message = EmailMessage()
    message["Subject"] = "Reset your Knight Labs password"
    message["From"] = MAIL["from"]
    message["To"] = to_email
    minutes = RESET_TOKEN_TTL_SECONDS // 60
    message.set_content(
        "We received a request to reset the password for your Knight Labs account.\n\n"
        "Open this link to choose a new password:\n"
        f"{link}\n\n"
        f"The link expires in {minutes} minutes and can only be used once.\n"
        "If you did not request a password reset, you can ignore this email — "
        "your current password remains unchanged.\n\n"
        "— Knight Labs\n"
    )
    message.add_alternative(
        "<html><body style=\"font-family:Arial,Helvetica,sans-serif;color:#11100b\">"
        "<h2 style=\"letter-spacing:-.02em\">Reset your password</h2>"
        "<p>We received a request to reset the password for your Knight Labs account.</p>"
        f'<p><a href="{link}" style="display:inline-block;background:#d4af37;color:#080604;'
        'padding:12px 22px;border-radius:8px;font-weight:700;text-decoration:none">'
        "Choose a new password</a></p>"
        f"<p style=\"color:#716958;font-size:13px\">The link expires in {minutes} minutes "
        "and can only be used once. If you did not request this, you can ignore this "
        "email — your current password remains unchanged.</p>"
        "</body></html>",
        subtype="html",
    )
    return message


def send_email(message, link):
    """Deliver via SMTP when configured, otherwise write to ./outbox."""
    if MAIL["host"]:
        try:
            with smtplib.SMTP(MAIL["host"], MAIL["port"], timeout=20) as smtp:
                smtp.ehlo()
                if MAIL["tls"]:
                    smtp.starttls()
                    smtp.ehlo()
                if MAIL["user"] and MAIL["password"]:
                    smtp.login(MAIL["user"], MAIL["password"])
                smtp.send_message(message)
            print(f"[mail] sent password reset to {message['To']} via {MAIL['host']}", flush=True)
            return "smtp"
        except smtplib.SMTPAuthenticationError as exc:
            print(f"[mail] SMTP login rejected: {exc.smtp_code} {exc.smtp_error!r}", flush=True)
            print("[mail] For Gmail this must be a 16-character App Password, not the\n"
                  "       account password, and 2-Step Verification must be enabled.", flush=True)
            print("[mail] falling back to ./outbox", flush=True)
        except Exception as exc:  # noqa: BLE001 - surface any delivery failure
            print(f"[mail] SMTP delivery failed ({exc.__class__.__name__}: {exc})", flush=True)
            print("[mail] falling back to ./outbox", flush=True)

    os.makedirs(OUTBOX_DIR, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", message["To"])
    stamp = int(time.time())
    path = os.path.join(OUTBOX_DIR, f"{stamp}-{safe}.eml")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(message.as_string())
    # The .eml body is quoted-printable, which mangles the token for copy-paste,
    # so drop the raw link beside it as plain text.
    link_path = os.path.join(OUTBOX_DIR, f"{stamp}-{safe}.link.txt")
    with open(link_path, "w", encoding="utf-8") as handle:
        handle.write(link + "\n")

    banner = "=" * 72
    # flush=True matters: stdout is block-buffered when the server is launched
    # with its output redirected, which would otherwise hide the link.
    print(
        f"\n{banner}\n"
        "[mail] SMTP is not configured, so no email was actually sent.\n"
        f"[mail] Saved: {path}\n"
        f"[mail] Password reset link for {message['To']}:\n\n"
        f"    {link}\n\n"
        f"{banner}\n",
        flush=True,
    )
    return "outbox"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY_BYTES:
            return None
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/api/signup":
            self._handle_signup()
        elif self.path == "/api/signin":
            self._handle_signin()
        elif self.path == "/api/request-password-reset":
            self._handle_request_password_reset()
        elif self.path == "/api/validate-reset":
            self._handle_validate_reset()
        elif self.path == "/api/reset-password":
            self._handle_reset_password()
        else:
            self._send_json(404, {"ok": False, "code": "not_found"})

    def _base_url(self):
        configured = os.environ.get("KL_BASE_URL", "").rstrip("/")
        if configured:
            return configured
        host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_address[1]}"
        return f"http://{host}"

    def _handle_request_password_reset(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        email = str(data.get("email", "")).strip().lower()
        if not EMAIL_RE.match(email):
            return self._send_json(400, {"ok": False, "code": "invalid_input"})

        token, error = create_reset_token(email)
        if error == "throttled":
            return self._send_json(429, {"ok": False, "code": "throttled"})
        if error == "no_account":
            # Do not disclose whether an account exists for this address.
            print(f"[mail] reset requested for unknown address {email} — nothing sent", flush=True)
            return self._send_json(200, {"ok": True, "code": "sent",
                                         "delivery": "smtp" if MAIL["host"] else "outbox"})

        link = f"{self._base_url()}/reset-password.html?token={token}"
        delivery = send_email(build_reset_email(email, link), link)
        # Tell the client how it actually went out so the UI can be honest.
        self._send_json(200, {"ok": True, "code": "sent", "delivery": delivery})

    def _handle_validate_reset(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        token = str(data.get("token", "")).strip()
        if not token:
            return self._send_json(400, {"ok": False, "code": "invalid_token"})
        email, error = find_reset_email(token)
        if error:
            return self._send_json(200, {"ok": False, "code": error})
        self._send_json(200, {"ok": True, "code": "valid", "email": email})

    def _handle_reset_password(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        token = str(data.get("token", "")).strip()
        password = str(data.get("password", ""))
        if not token:
            return self._send_json(400, {"ok": False, "code": "invalid_token"})
        if len(password) < MIN_PASSWORD_LENGTH:
            return self._send_json(400, {"ok": False, "code": "weak_password"})

        error = consume_reset_token(token, password)
        if error:
            return self._send_json(200, {"ok": False, "code": error})
        self._send_json(200, {"ok": True, "code": "password_updated"})

    def _handle_signup(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not EMAIL_RE.match(email) or len(password) < MIN_PASSWORD_LENGTH:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        with _lock:
            accounts = load_accounts()
            if email in accounts:
                return self._send_json(409, {"ok": False, "code": "email_exists"})
            salt, digest = hash_password(password)
            accounts[email] = {
                "salt": salt.hex(),
                "hash": digest.hex(),
                "iterations": PBKDF2_ITERATIONS,
            }
            save_accounts(accounts)
        self._send_json(200, {"ok": True, "code": "created"})

    def _handle_signin(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        with _lock:
            accounts = load_accounts()
        record = accounts.get(email)
        if not record:
            return self._send_json(200, {"ok": False, "code": "no_account"})
        if not verify_password(password, record["salt"], record["hash"]):
            return self._send_json(200, {"ok": False, "code": "bad_password"})
        self._send_json(200, {"ok": True, "code": "success"})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Knight Labs dev server running at http://127.0.0.1:{port}/")
    if MAIL["host"]:
        print(f"Mail: sending via {MAIL['host']}:{MAIL['port']} as {MAIL['from']}")
    else:
        print("Mail: SMTP not configured — reset links print here and save to ./outbox")
        print("      To send real email, copy smtp-config.example.json to smtp-config.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
