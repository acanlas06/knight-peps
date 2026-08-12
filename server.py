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
from html import escape as html_escape

ROOT = os.path.dirname(os.path.abspath(__file__))

# Where live data lives. In production this points outside the git checkout
# (KL_DATA_DIR=/var/lib/knight-labs) so a deploy never touches customer data
# and a stray `git clean` cannot delete orders. Defaults to the repo for local
# development, which is what you want when hacking on it.
DATA_DIR = os.environ.get("KL_DATA_DIR", "").strip() or ROOT
if DATA_DIR != ROOT:
    os.makedirs(DATA_DIR, exist_ok=True)

# Interface to bind. Behind Caddy this stays on loopback so the Python server
# is never exposed directly to the internet.
BIND_HOST = os.environ.get("KL_BIND_HOST", "127.0.0.1").strip() or "127.0.0.1"

ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
INVENTORY_FILE = os.path.join(DATA_DIR, "inventory.json")
ANALYTICS_FILE = os.path.join(DATA_DIR, "analytics.json")
AFFILIATES_FILE = os.path.join(DATA_DIR, "affiliates.json")
OUTBOX_DIR = os.path.join(DATA_DIR, "outbox")
PBKDF2_ITERATIONS = 260000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 6
MAX_BODY_BYTES = 10_000

# Password reset tokens
RESET_TOKEN_BYTES = 32
RESET_TOKEN_TTL_SECONDS = 3600  # 1 hour
RESET_MIN_INTERVAL_SECONDS = 60  # throttle repeat requests per account

# Orders
ORDER_TOKEN_BYTES = 32   # order numbers are guessable, so the token guards access
MAX_ORDER_ITEMS = 60
MAX_ORDER_BODY_BYTES = 60_000

# Affiliate / promo codes.
#
# Codes live in affiliates.json so they can be managed from the admin page
# without a deploy. This map only seeds that file the first time it is needed,
# so the two codes that predate the admin UI are not lost.
#
# Discounts are always computed server-side from this store. The browser is
# never sent the list of codes: it asks /api/validate-affiliate about one code
# at a time, so unpublished codes cannot be discovered by reading page source.
AFFILIATE_SEED = {
    "AC": {"label": "AC Affiliate", "type": "percent", "value": 15.0, "active": True},
    "TGOMEZ": {"label": "TGomez Affiliate", "type": "percent", "value": 15.0, "active": True},
}
AFFILIATE_TYPES = ("percent", "amount")
MAX_AFFILIATE_CODES = 200

# Order lifecycle. Order matters — the dashboard renders them in this sequence.
# Fulfilment and payment. Local options depend on the address, and cash on the
# fulfilment being local, so the two selects cannot be set independently. The
# browser disables the invalid combinations; these are the authoritative checks.
FULFILMENT_METHODS = ["FedEx 3-7 days", "Local delivery", "Local pickup"]
LOCAL_FULFILMENT = ("Local delivery", "Local pickup")
LOCAL_FULFILMENT_CITY = "orlando"
# Delivery charges, keyed by fulfilment method. Pickup costs the customer
# nothing because there is nothing to move.
SHIPPING_FEES = {
    "FedEx 3-7 days": (10.0, "Shipping"),
    "Local delivery": (5.0, "Gas fee"),
    "Local pickup": (0.0, "Pickup"),
}

PAYMENT_METHODS = ["Zelle after confirmation", "Cash on pickup/delivery"]
CASH_PAYMENT = "Cash on pickup/delivery"

ORDER_STATUSES = ["Unpaid", "Paid", "On its way", "Delivered"]
DEFAULT_ORDER_STATUS = "Unpaid"
# Cancelled sits outside the pipeline: it is terminal, excluded from revenue,
# and reachable only through the dedicated cancel endpoint.
CANCELLED_STATUS = "Cancelled"
ALL_STATUSES = ORDER_STATUSES + [CANCELLED_STATUS]

# Admin access. Emails listed in admin-config.json get the admin dashboard on
# sign-in. Passwords are never stored here — admins register through the normal
# signup form, so their credentials live in accounts.json like any other user.
ADMIN_CONFIG_FILE = os.environ.get("KL_ADMIN_CONFIG", "").strip() or os.path.join(DATA_DIR, "admin-config.json")
ADMIN_SESSION_BYTES = 32
ADMIN_SESSION_TTL_SECONDS = 8 * 3600
_admin_sessions = {}  # token_hash -> {"email":..., "expires_at":...}


def admin_emails():
    """Read the admin allowlist fresh each time so edits need no restart."""
    if not os.path.exists(ADMIN_CONFIG_FILE):
        return set()
    try:
        with open(ADMIN_CONFIG_FILE, "r", encoding="utf-8") as handle:
            raw = handle.read().strip()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[admin] Could not read admin-config.json ({exc}) — no admins active", flush=True)
        return set()
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = data.get("admins") or data.get("emails") or []
    else:
        entries = []
    return {str(e).strip().lower() for e in entries if str(e).strip()}


def is_admin(email):
    return bool(email) and email.strip().lower() in admin_emails()


def create_admin_session(email):
    token = secrets.token_urlsafe(ADMIN_SESSION_BYTES)
    now = time.time()
    with _lock:
        # Opportunistically drop expired sessions.
        for key in [k for k, v in _admin_sessions.items() if v["expires_at"] < now]:
            _admin_sessions.pop(key, None)
        _admin_sessions[hash_token(token)] = {
            "email": email,
            "expires_at": now + ADMIN_SESSION_TTL_SECONDS,
        }
    return token


def admin_session_email(token):
    """Return the admin email for a valid session token, else None."""
    if not token:
        return None
    digest = hash_token(str(token))
    now = time.time()
    with _lock:
        session = _admin_sessions.get(digest)
        if not session:
            return None
        if session["expires_at"] < now:
            _admin_sessions.pop(digest, None)
            return None
        email = session["email"]
    # Revoked immediately if the email is removed from the allowlist.
    return email if is_admin(email) else None

# Mail delivery.
#
# Credentials are read from smtp-config.json (gitignored) if present, and any
# KL_SMTP_* environment variable overrides the file. With no configuration at
# all, messages are written to ./outbox and the reset link is printed to the
# console — the sane default for local development.
#
# Copy smtp-config.example.json to smtp-config.json and fill it in. The file is
# gitignored so the app password never reaches the repository.
SMTP_CONFIG_FILE = os.environ.get("KL_SMTP_CONFIG", "").strip() or os.path.join(DATA_DIR, "smtp-config.json")


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
        "from": str(pick("from", "no-reply@knightpeps.com")).strip(),
        "tls": tls,
    }


MAIL = load_mail_config()
# Gmail (and most providers) reject a From: that isn't the authenticated user.
if MAIL["host"] and MAIL["user"] and MAIL["from"] == "no-reply@knightpeps.com":
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


def load_orders():
    if not os.path.exists(ORDERS_FILE):
        return {}
    with open(ORDERS_FILE, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def save_orders(orders):
    tmp_path = ORDERS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(orders, handle, indent=2)
    os.replace(tmp_path, ORDERS_FILE)


def clean_text(value, limit=200):
    """Orders are shown back to the user and emailed, so keep fields tidy."""
    return str(value if value is not None else "").strip()[:limit]


def normalise_affiliate_code(value):
    return re.sub(r"[^A-Z0-9_-]", "", clean_text(value, 40).upper())


def normalise_affiliate_rule(raw):
    """Coerce a stored or submitted rule into a known shape, or None."""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("type") or "percent").strip().lower()
    if kind not in AFFILIATE_TYPES:
        return None
    try:
        # "percent" is the legacy field name; accept it so pre-existing
        # affiliates.json files written before the type switch still load.
        value = float(raw.get("value", raw.get("percent", 0)) or 0)
    except (TypeError, ValueError):
        return None
    if kind == "percent" and not (0 < value < 100):
        return None
    if kind == "amount" and value <= 0:
        return None
    return {
        "label": clean_text(raw.get("label") or "", 80),
        "type": kind,
        "value": round(value, 2),
        "active": bool(raw.get("active", True)),
    }


def load_affiliates():
    """Read the code store, seeding it from AFFILIATE_SEED on first use."""
    if not os.path.exists(AFFILIATES_FILE):
        seeded = {c: dict(r) for c, r in AFFILIATE_SEED.items()}
        save_affiliates(seeded)
        return seeded
    try:
        with open(AFFILIATES_FILE, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        # A malformed file must not silently grant or deny every discount
        # without saying so in the log.
        print(f"[affiliates] Could not read affiliates.json ({exc})", flush=True)
        return {}
    codes = raw.get("codes") if isinstance(raw, dict) else None
    if not isinstance(codes, dict):
        return {}
    out = {}
    for code, rule in codes.items():
        code = normalise_affiliate_code(code)
        clean = normalise_affiliate_rule(rule)
        if code and clean:
            out[code] = clean
    return out


def save_affiliates(codes):
    payload = {"codes": codes}
    tmp = AFFILIATES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(tmp, AFFILIATES_FILE)


def affiliate_discount_for(code, subtotal):
    """Resolve a code to (rule, discount, error). The single source of truth
    for what a code is worth — the browser's figure is never trusted."""
    code = normalise_affiliate_code(code)
    if not code:
        return None, 0.0, None
    rule = load_affiliates().get(code)
    if not rule or not rule.get("active"):
        return None, 0.0, "invalid_affiliate_code"
    subtotal = max(0.0, float(subtotal or 0))
    if rule["type"] == "percent":
        discount = round(subtotal * rule["value"] / 100, 2)
    else:
        # A fixed amount can never exceed the subtotal, so a total can never
        # go negative and a small order cannot become a refund.
        discount = round(min(rule["value"], subtotal), 2)
    return {
        "code": code,
        "label": clean_text(rule.get("label") or code, 80),
        "type": rule["type"],
        "value": rule["value"],
        # Kept for the existing dashboard and stored orders, which read
        # "percent". Zero for fixed-amount codes.
        "percent": rule["value"] if rule["type"] == "percent" else 0,
    }, discount, None


def sanitise_order(payload):
    """Validate and normalise a submitted order. Returns (order, error_code)."""
    email = clean_text(payload.get("email"), 254).lower()
    if not EMAIL_RE.match(email):
        return None, "invalid_email"

    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return None, "empty_cart"
    if len(raw_items) > MAX_ORDER_ITEMS:
        return None, "too_many_items"

    items = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            return None, "invalid_items"
        try:
            qty = int(entry.get("qty") or 0)
            unit = float(entry.get("unitPrice") or 0)
        except (TypeError, ValueError):
            return None, "invalid_items"
        if qty < 1:
            return None, "invalid_items"
        items.append({
            "slug": clean_text(entry.get("slug"), 80),
            "name": clean_text(entry.get("name"), 120),
            "size": clean_text(entry.get("size"), 60),
            "qty": qty,
            "unitPrice": round(unit, 2),
            # Recomputed rather than trusted, so the email and the stored
            # record always agree with the unit price and quantity.
            "lineTotal": round(unit * qty, 2),
        })

    subtotal = round(sum(i["lineTotal"] for i in items), 2)
    item_count = sum(i["qty"] for i in items)

    # Fulfilment is arranged by phone, so a contactable number is required.
    # Counting digits rather than pattern-matching keeps (407) 555-0123,
    # 407-555-0123 and +1 407 555 0123 all valid.
    phone = clean_text(payload.get("phone"), 60)
    if len(re.sub(r"\D", "", phone)) < 10:
        return None, "invalid_phone"

    shipping_method = clean_text(payload.get("shippingMethod"), 80)
    payment_method = clean_text(payload.get("paymentPreference"), 80)
    if shipping_method not in FULFILMENT_METHODS:
        return None, "invalid_shipping_method"
    if payment_method not in PAYMENT_METHODS:
        return None, "invalid_payment_method"

    affiliate, discount_amount, affiliate_error = affiliate_discount_for(
        payload.get("affiliateCode"), subtotal)
    if affiliate_error:
        return None, affiliate_error

    shipping_fee, shipping_fee_label = SHIPPING_FEES.get(shipping_method, (0.0, ""))
    # The discount comes off the goods, then the delivery charge is added, so a
    # large fixed-amount code cannot also wipe out the shipping.
    total = round(max(0.0, subtotal - discount_amount) + shipping_fee, 2)

    address_in = payload.get("shippingAddress")
    address = None
    if isinstance(address_in, dict):
        address = {k: clean_text(address_in.get(k), 120) for k in
                   ("name", "street", "city", "state", "zip", "country")}

    city = (address or {}).get("city", "")
    if shipping_method in LOCAL_FULFILMENT and city.strip().lower() != LOCAL_FULFILMENT_CITY:
        return None, "local_requires_orlando"
    if payment_method == CASH_PAYMENT and shipping_method not in LOCAL_FULFILMENT:
        return None, "cash_requires_local"

    return {
        "email": email,
        "customerName": clean_text(payload.get("name"), 120),
        "phone": phone,
        "shippingMethod": shipping_method,
        "paymentPreference": payment_method,
        "shippingAddress": address,
        "items": items,
        "itemCount": item_count,
        "subtotal": subtotal,
        "discountAmount": discount_amount,
        "affiliate": affiliate,
        "shippingFee": shipping_fee,
        "shippingFeeLabel": shipping_fee_label,
        "total": total,
        "status": DEFAULT_ORDER_STATUS,
        "placedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "statusHistory": [{
            "status": DEFAULT_ORDER_STATUS,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }],
    }, None


def set_order_status(number, status, actor):
    """Update an order's status. Returns (order, error_code)."""
    number = clean_text(number, 40)
    status = clean_text(status, 40)
    if status not in ORDER_STATUSES:
        return None, "invalid_status"
    with _lock:
        orders = load_orders()
        record = orders.get(number)
        if not record:
            return None, "not_found"
        # A cancelled order must be restored before it can move again.
        if record.get("status") == CANCELLED_STATUS:
            return None, "order_cancelled"
        record["status"] = status
        history = record.get("statusHistory")
        if not isinstance(history, list):
            history = []
        history.append({
            "status": status,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "by": actor,
        })
        record["statusHistory"] = history
        orders[number] = record
        save_orders(orders)
    return {k: v for k, v in record.items() if k != "token_hash"}, None


# Inventory — one stock count per vial size, keyed "slug|size".
#
# Counts may go negative: that is a deliberate signal that you have oversold,
# rather than silently hiding the shortfall behind a zero. Orders are never
# blocked by stock.
PRODUCT_SLUGS = [
    "retatrutide", "tirzepatide", "semaglutide", "bpc-157", "tb500",
    "bpc-157-tb500-blend", "cjc-1295-without-dac-ipamorelin", "ipamorelin",
    "cjc-1295-without-dac-mod-grf-1-29", "tesamorelin",
    "nad", "glutathione", "epithalon",
    "semax", "selank", "ghk-cu", "bac-water",
]
PRODUCT_NAMES = {
    "retatrutide": "Retatrutide", "tirzepatide": "Tirzepatide",
    "semaglutide": "Semaglutide", "bpc-157": "BPC-157", "tb500": "TB500",
    "bpc-157-tb500-blend": "BPC-157 + TB500 Blend",
    "cjc-1295-without-dac-ipamorelin": "CJC-1295 without DAC + Ipamorelin",
    "ipamorelin": "Ipamorelin",
    "cjc-1295-without-dac-mod-grf-1-29": "CJC-1295 without DAC / Mod GRF 1-29",
    "nad": "NAD+", "glutathione": "Glutathione", "epithalon": "Epithalon",
    "semax": "Semax", "selank": "Selank", "ghk-cu": "GHK-CU",
    "tesamorelin": "Tesamorelin", "bac-water": "BAC Water",
}
# Only the sizes a customer can actually buy — the data-size values on the
# product page selector, which match KL_PRICES exactly. Category-page chips
# advertise extra sizes that are not purchasable; those are excluded.
PRODUCT_SIZES = {
    "retatrutide": ["10mg", "20mg", "30mg"],
    "tirzepatide": ["10mg", "20mg", "30mg"],
    "semaglutide": ["5mg", "10mg"],
    "bpc-157": ["10mg"],
    "tb500": ["10mg"],
    "bpc-157-tb500-blend": ["5mg + 5mg", "10mg + 10mg"],
    "cjc-1295-without-dac-ipamorelin": ["5mg + 5mg", "10mg + 10mg"],
    "ipamorelin": ["5mg", "10mg"],
    "cjc-1295-without-dac-mod-grf-1-29": ["2mg", "5mg"],
    "nad": ["500mg"],
    "glutathione": ["600mg", "1200mg"],
    "epithalon": ["10mg", "50mg"],
    "semax": ["10mg"],
    "selank": ["10mg"],
    "ghk-cu": ["50mg"],
    "tesamorelin": ["2mg", "5mg", "10mg", "20mg"],
    "bac-water": ["3ml", "10ml"],
}



def stock_key(slug, size):
    return "%s|%s" % (str(slug or "").strip(), str(size or "").strip())


def load_inventory():
    if not os.path.exists(INVENTORY_FILE):
        return {}
    try:
        with open(INVENTORY_FILE, "r", encoding="utf-8") as handle:
            raw = handle.read().strip()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    valid = {stock_key(slug, size) for slug, sizes in PRODUCT_SIZES.items() for size in sizes}
    stock, legacy = {}, []
    for key, value in data.items():
        key = str(key)
        try:
            amount = int(value)
        except (TypeError, ValueError):
            continue
        if key in valid:
            stock[key] = amount
        elif "|" not in key:
            # Pre-per-size entry. Ignored rather than guessed at, since one
            # product-level number cannot be split across sizes safely.
            legacy.append("%s=%s" % (key, amount))
    if legacy:
        print("[stock] Ignoring per-product entries from the old format: %s. "
              "Re-enter these per size in the admin Products tab."
              % ", ".join(sorted(legacy)), flush=True)
    return stock


def save_inventory(stock):
    tmp_path = INVENTORY_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(stock, handle, indent=2, sort_keys=True)
    os.replace(tmp_path, INVENTORY_FILE)


def units_sold_by_key():
    """Units shipped out per slug|size, ignoring cancelled orders."""
    sold = {}
    with _lock:
        orders = load_orders()
    for record in orders.values():
        if record.get("status") == CANCELLED_STATUS:
            continue
        for item in record.get("items") or []:
            slug = item.get("slug")
            if not slug:
                continue
            key = stock_key(slug, item.get("size"))
            try:
                sold[key] = sold.get(key, 0) + int(item.get("qty") or 0)
            except (TypeError, ValueError):
                continue
    return sold


def public_stock():
    """Stock for the storefront, keyed slug|size. Sizes with no entry are
    untracked and treated as available, so inventory is opt-in per size."""
    return dict(load_inventory())


def set_stock(slug, size, quantity):
    slug = clean_text(slug, 80)
    size = clean_text(size, 60)
    if slug not in PRODUCT_SIZES:
        return None, "unknown_product"
    if size not in PRODUCT_SIZES[slug]:
        return None, "unknown_size"
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return None, "invalid_quantity"
    if quantity < -100000 or quantity > 1000000:
        return None, "invalid_quantity"
    with _lock:
        stock = load_inventory()
        stock[stock_key(slug, size)] = quantity
        save_inventory(stock)
    return quantity, None


def adjust_stock_for_items(items, sign):
    """Apply an order's quantities to stock. sign -1 deducts, +1 restores.
    Only products that already have a stock entry are touched — untracked
    products stay untracked rather than springing into existence at a negative."""
    with _lock:
        stock = load_inventory()
        touched = False
        for item in items or []:
            key = stock_key(item.get("slug"), item.get("size"))
            if key not in stock:
                continue
            try:
                qty = int(item.get("qty") or 0)
            except (TypeError, ValueError):
                continue
            stock[key] = stock[key] + sign * qty
            touched = True
        if touched:
            save_inventory(stock)
        return dict(stock)


def admin_inventory():
    stock = load_inventory()
    sold = units_sold_by_key()
    products = []
    for slug in PRODUCT_SLUGS:
        variants = []
        for size in PRODUCT_SIZES.get(slug, []):
            key = stock_key(slug, size)
            tracked = key in stock
            remaining = stock.get(key)
            variants.append({
                "slug": slug,
                "size": size,
                "key": key,
                "tracked": tracked,
                "stock": remaining,
                "unitsSold": sold.get(key, 0),
                "soldOut": tracked and remaining <= 0,
                "oversold": tracked and remaining < 0,
            })
        tracked_variants = [v for v in variants if v["tracked"]]
        products.append({
            "slug": slug,
            "name": PRODUCT_NAMES.get(slug, slug),
            "variants": variants,
            "unitsSold": sum(v["unitsSold"] for v in variants),
            # A product only reads sold out when every size is tracked and gone.
            "soldOut": bool(tracked_variants)
                       and len(tracked_variants) == len(variants)
                       and all(v["soldOut"] for v in variants),
            "anyOversold": any(v["oversold"] for v in variants),
        })
    return products


# Site analytics.
#
# Deliberately minimal and anonymous: a random visitor id and session id
# generated in the browser, page paths, and timestamps. No IP addresses, no
# names, no emails, nothing that identifies a person. Browsers sending
# Do Not Track are skipped client-side.
ANALYTICS_RETENTION_DAYS = 90
ANALYTICS_MAX_SESSIONS_PER_DAY = 20000
SESSION_IDLE_TIMEOUT = 30 * 60      # a gap this long ends a session
MAX_SESSION_SECONDS = 4 * 3600      # cap so a forgotten tab cannot skew averages
TRACK_EVENTS = ("view", "ping", "end", "add_to_cart")


def load_analytics():
    if not os.path.exists(ANALYTICS_FILE):
        return {"days": {}}
    try:
        with open(ANALYTICS_FILE, "r", encoding="utf-8") as handle:
            raw = handle.read().strip()
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        return {"days": {}}
    if not isinstance(data, dict) or not isinstance(data.get("days"), dict):
        return {"days": {}}
    return data


def save_analytics(data):
    tmp_path = ANALYTICS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, sort_keys=True)
    os.replace(tmp_path, ANALYTICS_FILE)


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def track_event(payload):
    """Record one anonymous event. Returns an error code or None."""
    kind = clean_text(payload.get("event"), 20)
    if kind not in TRACK_EVENTS:
        return "unknown_event"
    visitor = clean_text(payload.get("visitor"), 64)
    session = clean_text(payload.get("session"), 64)
    if not visitor or not session:
        return "missing_ids"
    path = clean_text(payload.get("path"), 120) or "/"
    now = time.time()
    day = _today()

    with _lock:
        data = load_analytics()
        days = data["days"]
        bucket = days.setdefault(day, {
            "visitors": {}, "pageviews": 0, "addToCart": 0, "sessions": {},
        })
        bucket["visitors"][visitor] = bucket["visitors"].get(visitor, 0) + 1

        if kind == "add_to_cart":
            try:
                qty = max(1, int(payload.get("qty") or 1))
            except (TypeError, ValueError):
                qty = 1
            bucket["addToCart"] = bucket.get("addToCart", 0) + qty
        elif kind == "view":
            bucket["pageviews"] = bucket.get("pageviews", 0) + 1

        sessions = bucket["sessions"]
        if session not in sessions and len(sessions) >= ANALYTICS_MAX_SESSIONS_PER_DAY:
            save_analytics(data)
            return None
        record = sessions.setdefault(session, {
            "start": now, "last": now, "views": 0, "paths": [],
        })
        # A long gap means the visitor came back later; start the clock again
        # rather than counting the idle time as time on site.
        if now - record["last"] > SESSION_IDLE_TIMEOUT:
            record["start"] = now
        record["last"] = now
        if kind == "view":
            record["views"] = record.get("views", 0) + 1
            paths = record.setdefault("paths", [])
            if path not in paths and len(paths) < 40:
                paths.append(path)

        # Drop anything past the retention window.
        if len(days) > ANALYTICS_RETENTION_DAYS:
            for old in sorted(days.keys())[:-ANALYTICS_RETENTION_DAYS]:
                days.pop(old, None)
        save_analytics(data)
    return None


def analytics_summary():
    with _lock:
        data = load_analytics()
    days = data.get("days") or {}
    today = _today()

    def day_stats(names):
        visitors, pageviews, adds = set(), 0, 0
        durations = []
        for name in names:
            bucket = days.get(name) or {}
            visitors.update((bucket.get("visitors") or {}).keys())
            pageviews += int(bucket.get("pageviews") or 0)
            adds += int(bucket.get("addToCart") or 0)
            for record in (bucket.get("sessions") or {}).values():
                span = float(record.get("last", 0)) - float(record.get("start", 0))
                if span < 0:
                    span = 0
                durations.append(min(span, MAX_SESSION_SECONDS))
        avg = round(sum(durations) / len(durations)) if durations else 0
        return {
            "visitors": len(visitors),
            "pageviews": pageviews,
            "addToCart": adds,
            "sessions": len(durations),
            "avgSeconds": avg,
        }

    names = sorted(days.keys(), reverse=True)
    last7 = names[:7]
    last30 = names[:30]

    daily = []
    for name in names[:30]:
        stats = day_stats([name])
        stats["date"] = name
        daily.append(stats)

    return {
        "today": day_stats([today]),
        "last7": day_stats(last7),
        "last30": day_stats(last30),
        "daily": daily,
        "trackedDays": len(names),
        "firstDay": names[-1] if names else None,
    }


def cancel_order(number, actor, reason, confirmed):
    """Cancel an order. Deliberately refuses without an explicit confirmation
    flag, so a stray or replayed request cannot cancel anything."""
    if confirmed is not True:
        return None, "confirmation_required"
    number = clean_text(number, 40)
    reason = clean_text(reason, 300)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _lock:
        orders = load_orders()
        record = orders.get(number)
        if not record:
            return None, "not_found"
        if record.get("status") == CANCELLED_STATUS:
            return None, "already_cancelled"
        # Remember where it was so a restore can put it back.
        record["statusBeforeCancel"] = record.get("status") or DEFAULT_ORDER_STATUS
        record["status"] = CANCELLED_STATUS
        record["cancelledAt"] = now
        record["cancelledBy"] = actor
        record["cancelReason"] = reason
        history = record.get("statusHistory")
        if not isinstance(history, list):
            history = []
        history.append({"status": CANCELLED_STATUS, "at": now, "by": actor,
                        "reason": reason})
        record["statusHistory"] = history
        orders[number] = record
        save_orders(orders)
    # Cancelling puts the units back on the shelf.
    adjust_stock_for_items(record.get("items"), +1)
    return {k: v for k, v in record.items() if k != "token_hash"}, None


def restore_order(number, actor, confirmed):
    """Undo a cancellation, returning the order to where it left off."""
    if confirmed is not True:
        return None, "confirmation_required"
    number = clean_text(number, 40)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _lock:
        orders = load_orders()
        record = orders.get(number)
        if not record:
            return None, "not_found"
        if record.get("status") != CANCELLED_STATUS:
            return None, "not_cancelled"
        restored = record.get("statusBeforeCancel") or DEFAULT_ORDER_STATUS
        if restored not in ORDER_STATUSES:
            restored = DEFAULT_ORDER_STATUS
        record["status"] = restored
        for key in ("cancelledAt", "cancelledBy", "cancelReason", "statusBeforeCancel"):
            record.pop(key, None)
        history = record.get("statusHistory")
        if not isinstance(history, list):
            history = []
        history.append({"status": restored, "at": now, "by": actor,
                        "reason": "restored from cancelled"})
        record["statusHistory"] = history
        orders[number] = record
        save_orders(orders)
    # Un-cancelling takes the units back off the shelf.
    adjust_stock_for_items(record.get("items"), -1)
    return {k: v for k, v in record.items() if k != "token_hash"}, None


def all_orders_for_admin():
    """Every order, newest first, with tokens stripped."""
    with _lock:
        orders = load_orders()
    rows = []
    for number, record in orders.items():
        row = {k: v for k, v in record.items() if k != "token_hash"}
        row["orderNumber"] = row.get("orderNumber") or number
        # Legacy records predate the status field.
        if row.get("status") not in ALL_STATUSES:
            row["status"] = DEFAULT_ORDER_STATUS
        rows.append(row)
    rows.sort(key=lambda r: r.get("placedAt") or "", reverse=True)
    return rows


def admin_accounts():
    """Registered accounts with their order history.

    Built field by field on purpose. An account record holds salt, hash and
    iterations, and none of that may ever reach a browser, so this constructs a
    fresh dict rather than copying the record and deleting keys - a whitelist
    cannot be defeated by a field added later.
    """
    with _lock:
        accounts = load_accounts()
    orders = all_orders_for_admin()
    admins = {e.lower() for e in admin_emails()}

    by_email = {}
    for row in orders:
        email = str(row.get("email") or "").strip().lower()
        if email:
            by_email.setdefault(email, []).append(row)

    out = []
    # Registered accounts, plus guests who ordered without one, so the list is
    # every customer rather than only the ones who signed up.
    for email in sorted(set(accounts) | set(by_email)):
        rows = by_email.get(email, [])
        live = [r for r in rows if r.get("status") != CANCELLED_STATUS]
        cancelled = [r for r in rows if r.get("status") == CANCELLED_STATUS]
        collected = [r for r in live if r.get("status") in ("Paid", "On its way", "Delivered")]
        latest = rows[0] if rows else {}
        record = accounts.get(email) or {}
        out.append({
            "email": email,
            "hasAccount": email in accounts,
            "isAdmin": email in admins,
            "createdAt": record.get("createdAt") or "",
            "name": clean_text(latest.get("customerName"), 120),
            "phone": clean_text(latest.get("phone"), 60),
            "orderCount": len(live),
            "cancelledCount": len(cancelled),
            "ordered": round(sum(float(r.get("total") or 0) for r in live), 2),
            "collected": round(sum(float(r.get("total") or 0) for r in collected), 2),
            "lastOrderAt": latest.get("placedAt") or "",
            "orders": [{
                "orderNumber": r.get("orderNumber"),
                "placedAt": r.get("placedAt"),
                "status": r.get("status"),
                "total": r.get("total"),
                "itemCount": r.get("itemCount"),
                "shippingMethod": r.get("shippingMethod"),
                "paymentPreference": r.get("paymentPreference"),
                "affiliate": (r.get("affiliate") or {}).get("code", ""),
                "items": [{"name": i.get("name"), "size": i.get("size"),
                           "qty": i.get("qty"), "lineTotal": i.get("lineTotal")}
                          for i in (r.get("items") or [])],
                "shippingAddress": r.get("shippingAddress") or None,
            } for r in rows],
        })
    out.sort(key=lambda a: (a["lastOrderAt"] or "", a["email"]), reverse=True)
    return out


def admin_stats():
    """Metrics derivable from stored orders. Behavioural metrics are not
    tracked yet, so they are reported as unavailable rather than faked."""
    all_rows = all_orders_for_admin()
    # Cancelled orders are counted separately and never in revenue.
    rows = [r for r in all_rows if r.get("status") != CANCELLED_STATUS]
    cancelled = [r for r in all_rows if r.get("status") == CANCELLED_STATUS]

    by_status = {s: 0 for s in ALL_STATUSES}
    by_status[CANCELLED_STATUS] = len(cancelled)
    revenue_by_status = {s: 0.0 for s in ORDER_STATUSES}
    per_day = {}
    customers = set()
    units = 0
    referrals = {}

    def referral_bucket(code, label=None, percent=None):
        code = normalise_affiliate_code(code)
        if not code:
            return None
        bucket = referrals.setdefault(code, {
            "code": code,
            "label": clean_text(label or code, 80),
            "percent": round(float(percent or 0), 2),
            "orderCount": 0,
            "cancelledCount": 0,
            "unitsOrdered": 0,
            "subtotal": 0.0,
            "discountAmount": 0.0,
            "total": 0.0,
            "collectedTotal": 0.0,
            "unpaidTotal": 0.0,
            # Filled in from the code store; a code deleted after taking orders
            # keeps its sales row but is marked inactive.
            "type": "percent",
            "value": round(float(percent or 0), 2),
            "active": False,
        })
        if label and bucket["label"] == code:
            bucket["label"] = clean_text(label, 80)
        if percent and not bucket["percent"]:
            bucket["percent"] = round(float(percent), 2)
        return bucket

    # List every configured code, so a new or paused one still shows a row
    # before it has taken its first order.
    for code, rule in load_affiliates().items():
        bucket = referral_bucket(
            code, rule.get("label") or code,
            rule["value"] if rule["type"] == "percent" else 0)
        if bucket:
            bucket["type"] = rule["type"]
            bucket["value"] = rule["value"]
            bucket["active"] = bool(rule.get("active"))

    for row in rows:
        status = row.get("status", DEFAULT_ORDER_STATUS)
        total = float(row.get("total") or 0)
        by_status[status] = by_status.get(status, 0) + 1
        revenue_by_status[status] = round(revenue_by_status.get(status, 0.0) + total, 2)
        units += int(row.get("itemCount") or 0)
        affiliate = row.get("affiliate") or {}
        bucket = referral_bucket(affiliate.get("code"), affiliate.get("label"), affiliate.get("percent"))
        if bucket:
            bucket["orderCount"] += 1
            bucket["unitsOrdered"] += int(row.get("itemCount") or 0)
            bucket["subtotal"] = round(bucket["subtotal"] + float(row.get("subtotal") or 0), 2)
            bucket["discountAmount"] = round(bucket["discountAmount"] + float(row.get("discountAmount") or 0), 2)
            bucket["total"] = round(bucket["total"] + total, 2)
            if status in ("Paid", "On its way", "Delivered"):
                bucket["collectedTotal"] = round(bucket["collectedTotal"] + total, 2)
            if status == "Unpaid":
                bucket["unpaidTotal"] = round(bucket["unpaidTotal"] + total, 2)
        if row.get("email"):
            customers.add(row["email"].lower())
        day = (row.get("placedAt") or "")[:10]
        if day:
            bucket_day = per_day.setdefault(day, {"orders": 0, "revenue": 0.0, "customers": set()})
            bucket_day["orders"] += 1
            bucket_day["revenue"] = round(bucket_day["revenue"] + total, 2)
            if row.get("email"):
                bucket_day["customers"].add(row["email"].lower())

    for row in cancelled:
        affiliate = row.get("affiliate") or {}
        bucket = referral_bucket(affiliate.get("code"), affiliate.get("label"), affiliate.get("percent"))
        if bucket:
            bucket["cancelledCount"] += 1

    gross = round(sum(float(r.get("total") or 0) for r in rows), 2)
    # Money actually collected, as opposed to ordered.
    collected = round(sum(revenue_by_status.get(s, 0.0)
                          for s in ("Paid", "On its way", "Delivered")), 2)

    daily = [{"date": d,
              "orders": v["orders"],
              "revenue": v["revenue"],
              "customers": len(v["customers"])}
             for d, v in sorted(per_day.items(), reverse=True)]

    return {
        "orderCount": len(rows),
        "cancelledCount": len(cancelled),
        "cancelledValue": round(sum(float(r.get("total") or 0) for r in cancelled), 2),
        "grossRevenue": gross,
        "collectedRevenue": collected,
        "unpaidRevenue": revenue_by_status.get("Unpaid", 0.0),
        "unitsOrdered": units,
        "uniqueCustomers": len(customers),
        "averageOrderValue": round(gross / len(rows), 2) if rows else 0,
        "byStatus": by_status,
        "revenueByStatus": revenue_by_status,
        "daily": daily[:30],
        "referrals": sorted(referrals.values(), key=lambda r: (r["orderCount"] == 0, r["code"])),
        "statuses": ORDER_STATUSES,
        "cancelledStatus": CANCELLED_STATUS,
        "site": analytics_summary(),
        "unavailable": [],
    }


def create_order(payload):
    """Persist an order and return (order_number, token, order, error)."""
    order, error = sanitise_order(payload)
    if error:
        return None, None, None, error

    token = secrets.token_urlsafe(ORDER_TOKEN_BYTES)
    with _lock:
        orders = load_orders()
        # Sequential, non-colliding order numbers.
        number = "KL-%05d" % (len(orders) + 1001)
        while number in orders:
            number = "KL-%05d" % (int(number.split("-")[1]) + 1)
        order["orderNumber"] = number
        # Only the digest is stored, so orders.json cannot be used to forge links.
        record = dict(order)
        record["token_hash"] = hash_token(token)
        orders[number] = record
        save_orders(orders)
    # Stock comes down once the order is safely stored.
    adjust_stock_for_items(order["items"], -1)
    return number, token, order, None


def find_order(number, token):
    """Look up an order by number and token. Returns (order, error_code)."""
    number = clean_text(number, 40)
    token = clean_text(token, 200)
    if not number or not token:
        return None, "not_found"
    with _lock:
        orders = load_orders()
    record = orders.get(number)
    if not record:
        return None, "not_found"
    stored = record.get("token_hash") or ""
    if not stored or not hmac.compare_digest(stored, hash_token(token)):
        # Same response as a missing order, so the endpoint reveals nothing.
        return None, "not_found"
    public = {k: v for k, v in record.items() if k != "token_hash"}
    return public, None


# Zelle payment details. Must match assets/zelle.js.
ZELLE_TOKEN = "cj060824@gmail.com"
ZELLE_NAME = "Christopher"
ZELLE_LINK = ("https://enroll.zellepay.com/qr-codes?data="
              "eyJuYW1lIjoiQ0hSSVNUT1BIRVIiLCJ0b2tlbiI6ImNqMDYwODI0QGdtYWlsLmNvbSJ9")


def is_zelle(preference):
    return "zelle" in str(preference or "").lower()


def is_cash(preference):
    return "cash" in str(preference or "").lower()


def build_order_email(order, link):
    message = EmailMessage()
    message["Subject"] = "Knight Labs order " + order["orderNumber"]
    message["From"] = MAIL["from"]
    message["To"] = order["email"]

    def fmt(amount):
        return "$%s" % format(round(amount, 2), ",.2f")

    lines = ["  %s  %s  x%d  %s" % (i["name"], i["size"], i["qty"], fmt(i["lineTotal"]))
             for i in order["items"]]
    address = order.get("shippingAddress") or {}
    address_text = ""
    if address.get("street"):
        address_text = ("\nShipping to:\n  %s\n  %s\n  %s, %s %s\n  %s\n" % (
            address.get("name", ""), address.get("street", ""), address.get("city", ""),
            address.get("state", ""), address.get("zip", ""), address.get("country", "")))

    cash_text = ""
    if is_cash(order.get("paymentPreference")):
        cash_text = (
            "\nPAYING WITH CASH\n"
            "  1. Knight Labs will confirm the availability of your selected products.\n"
            "  2. We will then contact you directly, by phone or email, to arrange\n"
            "     delivery.\n"
            "  3. Please bring exactly %s in cash.\n\n"
            "PLEASE BRING THE EXACT AMOUNT. We do not carry change, so we cannot\n"
            "break larger notes. The amount above is the full order total, including\n"
            "any delivery charge.\n"
            % fmt(order["total"])
        )

    zelle_text = ""
    if is_zelle(order.get("paymentPreference")):
        zelle_text = (
            "\nHOW TO PAY WITH ZELLE\n"
            "  1. Send exactly %s\n"
            "  2. Send to %s (shows as %s)\n"
            "  3. Put %s in the memo / note field\n\n"
            "  Zelle: %s\n\n"
            "The order number in the memo is how your payment is matched to this\n"
            "order. Your order stays Unpaid until the payment is received.\n"
            % (fmt(order["total"]), ZELLE_TOKEN, ZELLE_NAME,
               order["orderNumber"], ZELLE_LINK)
        )

    # Orders placed before delivery charges existed have no shippingFee, so the
    # line is omitted rather than printed as $0.
    fee_text = ""
    if order.get("shippingFee"):
        fee_text = "\n%s: %s" % (order.get("shippingFeeLabel") or "Shipping",
                                 fmt(order["shippingFee"]))

    discount_text = ""
    if order.get("affiliate") and order.get("discountAmount"):
        discount_text = "\nAffiliate code %s: -%s" % (
            order["affiliate"].get("code", ""), fmt(order.get("discountAmount", 0)))

    message.set_content(
        "Thanks for your order.\n\n"
        "Order %s\nPlaced %s\n\n"
        "Items:\n%s\n\nSubtotal: %s%s%s\nTotal: %s\n%s\n%s"
        "View your order:\n%s\n\n"
        "Keep this link — it is the only way to view this order if you do not "
        "have an account.\n\n"
        "For research and laboratory use only. Not intended for human or "
        "veterinary consumption.\n\n— Knight Labs\n"
        % (order["orderNumber"], order["placedAt"], "\n".join(lines),
           fmt(order.get("subtotal", order["total"])), discount_text, fee_text,
           fmt(order["total"]),
           address_text, zelle_text + cash_text, link)
    )

    rows = "".join(
        '<tr><td style="padding:8px 0;border-top:1px solid #eadbb2">%s'
        '<div style="color:#716958;font-size:13px">%s &middot; Qty %d</div></td>'
        '<td style="padding:8px 0;border-top:1px solid #eadbb2;text-align:right;'
        'white-space:nowrap">%s</td></tr>'
        % (html_escape(i["name"]), html_escape(i["size"]), i["qty"], fmt(i["lineTotal"]))
        for i in order["items"])

    address_html = ""
    if address.get("street"):
        address_html = (
            '<p style="color:#716958;font-size:13px;line-height:1.7">'
            '<strong style="color:#11100b">Shipping to</strong><br>%s<br>%s<br>%s, %s %s<br>%s</p>'
            % (html_escape(address.get("name", "")), html_escape(address.get("street", "")),
               html_escape(address.get("city", "")), html_escape(address.get("state", "")),
               html_escape(address.get("zip", "")), html_escape(address.get("country", ""))))

    cash_html = ""
    if is_cash(order.get("paymentPreference")):
        cash_html = (
            '<div style="margin:24px 0;padding:18px;border:1px solid #dac89a;'
            'border-radius:12px;background:#fff8e3">'
            '<div style="font-size:11px;font-weight:900;letter-spacing:.12em;'
            'text-transform:uppercase;color:#8c6713;margin-bottom:12px">Paying with cash</div>'
            '<p style="margin:0 0 8px">1. Knight Labs will confirm the availability of '
            'your selected products.</p>'
            '<p style="margin:0 0 8px">2. We will then contact you directly, by phone or '
            'email, to arrange delivery.</p>'
            '<p style="margin:0 0 12px">3. Please bring exactly <strong>%s</strong> in cash.</p>'
            '<p style="margin:0;padding:10px 12px;border-radius:10px;background:#f5efe5">'
            '<strong>Please bring the exact amount.</strong> We do not carry change, so we '
            'cannot break larger notes. This is the full order total, including any '
            'delivery charge.</p>'
            '</div>'
            % fmt(order["total"])
        )

    zelle_html = ""
    if is_zelle(order.get("paymentPreference")):
        zelle_html = (
            '<div style="border:1px solid #d4af37;border-radius:12px;background:#fdf8e7;'
            'padding:18px;margin:22px 0">'
            '<p style="margin:0 0 12px;font-size:11px;font-weight:700;letter-spacing:.1em;'
            'text-transform:uppercase;color:#8c6713">How to pay with Zelle</p>'
            '<p style="margin:0 0 8px;font-size:14px">1. Send exactly <strong>%s</strong></p>'
            '<p style="margin:0 0 8px;font-size:14px">2. Send to <strong>%s</strong> '
            '<span style="color:#716958">(shows as %s)</span></p>'
            '<p style="margin:0 0 12px;font-size:14px">3. Put <strong>%s</strong> in the '
            'memo / note field</p>'
            '<p style="margin:0 0 12px"><a href="%s" style="display:inline-block;'
            'background:#d4af37;color:#080604;padding:10px 18px;border-radius:8px;'
            'font-weight:700;text-decoration:none">Open in Zelle</a></p>'
            '<p style="margin:0;color:#716958;font-size:12px;line-height:1.6">The order '
            'number in the memo is how your payment is matched to this order. Your order '
            'stays Unpaid until the payment is received.</p>'
            '</div>'
            % (fmt(order["total"]), html_escape(ZELLE_TOKEN), html_escape(ZELLE_NAME),
               html_escape(order["orderNumber"]), html_escape(ZELLE_LINK))
        )

    total_rows = (
        '<tr><td style="padding:12px 0;border-top:2px solid #dac89a">Subtotal</td>'
        '<td style="padding:12px 0;border-top:2px solid #dac89a;text-align:right">%s</td></tr>'
        % fmt(order.get("subtotal", order["total"]))
    )
    if order.get("affiliate") and order.get("discountAmount"):
        total_rows += (
            '<tr><td style="padding:8px 0;color:#8c6713">Affiliate code %s</td>'
            '<td style="padding:8px 0;text-align:right;color:#8c6713">-%s</td></tr>'
            % (html_escape(order["affiliate"].get("code", "")), fmt(order.get("discountAmount", 0)))
        )
    if order.get("shippingFee"):
        total_rows += (
            '<tr><td style="padding:8px 0">%s</td>'
            '<td style="padding:8px 0;text-align:right">%s</td></tr>'
            % (html_escape(order.get("shippingFeeLabel") or "Shipping"),
               fmt(order["shippingFee"]))
        )
    total_rows += (
        '<tr><td style="padding:12px 0;border-top:2px solid #dac89a"><strong>Total</strong></td>'
        '<td style="padding:12px 0;border-top:2px solid #dac89a;text-align:right">'
        '<strong>%s</strong></td></tr>' % fmt(order["total"])
    )

    message.add_alternative(
        '<html><body style="font-family:Arial,Helvetica,sans-serif;color:#11100b;margin:0;padding:24px">'
        '<div style="max-width:560px;margin:0 auto">'
        '<h2 style="letter-spacing:-.02em;margin:0 0 4px">Thanks for your order</h2>'
        '<p style="color:#716958;font-size:14px;margin:0 0 20px">Order %s</p>'
        '<table style="width:100%%;border-collapse:collapse;font-size:14px">%s%s</table>'
        '%s'
        '%s'
        '<p style="margin:24px 0"><a href="%s" style="display:inline-block;background:#d4af37;'
        'color:#080604;padding:12px 22px;border-radius:8px;font-weight:700;text-decoration:none">'
        'View your order</a></p>'
        '<p style="color:#716958;font-size:12px;line-height:1.6">Keep this link — it is the only '
        'way to view this order if you do not have an account.</p>'
        '<p style="color:#716958;font-size:12px;line-height:1.6">No payment has been collected. '
        'Knight Labs will confirm availability and the final total, then send payment instructions '
        'directly.</p>'
        '<p style="color:#8c8377;font-size:11px;line-height:1.6;border-top:1px solid #eadbb2;'
        'padding-top:14px">For research and laboratory use only. Not intended for human or '
        'veterinary consumption.</p>'
        '</div></body></html>'
        % (html_escape(order["orderNumber"]), rows, total_rows, address_html,
           zelle_html + cash_html, html_escape(link)),
        subtype="html",
    )
    return message


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
    # A bare timestamp collides when two messages go to the same address in the
    # same second, silently overwriting the earlier one.
    stamp = "%d-%s" % (int(time.time()), secrets.token_hex(3))
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

    def _read_json(self, max_bytes=MAX_BODY_BYTES):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None
        if length <= 0 or length > max_bytes:
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
        elif self.path == "/api/place-order":
            self._handle_place_order()
        elif self.path == "/api/order-lookup":
            self._handle_order_lookup()
        elif self.path == "/api/admin/orders":
            self._handle_admin_orders()
        elif self.path == "/api/admin/order-status":
            self._handle_admin_order_status()
        elif self.path == "/api/admin/stats":
            self._handle_admin_stats()
        elif self.path == "/api/admin/cancel-order":
            self._handle_admin_cancel_order()
        elif self.path == "/api/admin/restore-order":
            self._handle_admin_restore_order()
        elif self.path == "/api/stock":
            self._handle_stock()
        elif self.path == "/api/track":
            self._handle_track()
        elif self.path == "/api/admin/inventory":
            self._handle_admin_inventory()
        elif self.path == "/api/admin/set-stock":
            self._handle_admin_set_stock()
        elif self.path == "/api/validate-affiliate":
            self._handle_validate_affiliate()
        elif self.path == "/api/admin/accounts":
            self._handle_admin_accounts()
        elif self.path == "/api/admin/affiliates":
            self._handle_admin_affiliates()
        elif self.path == "/api/admin/affiliate-save":
            self._handle_admin_affiliate_save()
        elif self.path == "/api/admin/affiliate-delete":
            self._handle_admin_affiliate_delete()
        else:
            self._send_json(404, {"ok": False, "code": "not_found"})

    def _require_admin(self, data):
        """Resolve the admin session token, or send 401 and return None."""
        token = (data or {}).get("adminToken")
        email = admin_session_email(token)
        if not email:
            self._send_json(401, {"ok": False, "code": "not_authorised"})
            return None
        return email

    def _handle_validate_affiliate(self):
        """Check one code. Public, so it deliberately reveals nothing beyond
        whether the submitted code is usable and what it is worth."""
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        try:
            subtotal = max(0.0, float(data.get("subtotal") or 0))
        except (TypeError, ValueError):
            subtotal = 0.0
        rule, discount, error = affiliate_discount_for(data.get("code"), subtotal)
        if error or not rule:
            # A wrong code and an inactive code answer identically, so the
            # response cannot be used to enumerate which codes exist.
            return self._send_json(200, {
                "ok": True, "valid": False,
                "code": normalise_affiliate_code(data.get("code")),
            })
        self._send_json(200, {
            "ok": True, "valid": True,
            "code": rule["code"], "label": rule["label"],
            "type": rule["type"], "value": rule["value"],
            "percent": rule["percent"],
            "discountAmount": discount,
            "total": round(max(0.0, subtotal - discount), 2),
        })

    def _handle_admin_accounts(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        if not self._require_admin(data):
            return
        self._send_json(200, {"ok": True, "accounts": admin_accounts()})

    def _handle_admin_affiliates(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        if not self._require_admin(data):
            return
        codes = load_affiliates()
        self._send_json(200, {"ok": True, "types": list(AFFILIATE_TYPES),
                              "codes": [dict(rule, code=code)
                                        for code, rule in sorted(codes.items())]})

    def _handle_admin_affiliate_save(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        if not self._require_admin(data):
            return
        code = normalise_affiliate_code(data.get("code"))
        if not code:
            return self._send_json(400, {"ok": False, "code": "invalid_code"})
        rule = normalise_affiliate_rule({
            "label": data.get("label"),
            "type": data.get("type"),
            "value": data.get("value"),
            "active": data.get("active", True),
        })
        if not rule:
            return self._send_json(400, {"ok": False, "code": "invalid_rule"})
        if not rule["label"]:
            rule["label"] = code
        with _lock:
            codes = load_affiliates()
            if code not in codes and len(codes) >= MAX_AFFILIATE_CODES:
                return self._send_json(400, {"ok": False, "code": "too_many_codes"})
            codes[code] = rule
            save_affiliates(codes)
        self._send_json(200, {"ok": True, "code": code, "rule": rule})

    def _handle_admin_affiliate_delete(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        if not self._require_admin(data):
            return
        code = normalise_affiliate_code(data.get("code"))
        with _lock:
            codes = load_affiliates()
            if code not in codes:
                return self._send_json(404, {"ok": False, "code": "not_found"})
            del codes[code]
            save_affiliates(codes)
        # Orders already placed keep their recorded discount; only future use
        # of the code is stopped.
        self._send_json(200, {"ok": True, "code": code})

    def _handle_admin_orders(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        if not self._require_admin(data):
            return
        self._send_json(200, {"ok": True, "orders": all_orders_for_admin(),
                              "statuses": ORDER_STATUSES})

    def _handle_admin_order_status(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        email = self._require_admin(data)
        if not email:
            return
        order, error = set_order_status(data.get("orderNumber"), data.get("status"), email)
        if error:
            return self._send_json(200, {"ok": False, "code": error})
        print("[admin] %s set %s to %s" % (email, order["orderNumber"], order["status"]), flush=True)
        self._send_json(200, {"ok": True, "order": order})

    def _handle_admin_cancel_order(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        email = self._require_admin(data)
        if not email:
            return
        order, error = cancel_order(data.get("orderNumber"), email,
                                    data.get("reason"), data.get("confirm"))
        if error:
            return self._send_json(200, {"ok": False, "code": error})
        print("[admin] %s CANCELLED %s (%s)"
              % (email, order["orderNumber"], order.get("cancelReason") or "no reason given"),
              flush=True)
        self._send_json(200, {"ok": True, "order": order})

    def _handle_admin_restore_order(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        email = self._require_admin(data)
        if not email:
            return
        order, error = restore_order(data.get("orderNumber"), email, data.get("confirm"))
        if error:
            return self._send_json(200, {"ok": False, "code": error})
        print("[admin] %s restored %s to %s"
              % (email, order["orderNumber"], order["status"]), flush=True)
        self._send_json(200, {"ok": True, "order": order})

    def _handle_track(self):
        data = self._read_json()
        if data is None:
            return self._send_json(200, {"ok": True})
        try:
            track_event(data)
        except Exception as exc:  # noqa: BLE001 — analytics must never break a page
            print("[track] failed (%s: %s)" % (exc.__class__.__name__, exc), flush=True)
        self._send_json(200, {"ok": True})

    def _handle_stock(self):
        # Public: the storefront needs this to show sold-out states.
        self._send_json(200, {"ok": True, "stock": public_stock()})

    def _handle_admin_inventory(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        if not self._require_admin(data):
            return
        self._send_json(200, {"ok": True, "products": admin_inventory()})

    def _handle_admin_set_stock(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        email = self._require_admin(data)
        if not email:
            return
        slug = data.get("slug")
        size = data.get("size")
        value, error = set_stock(slug, size, data.get("stock"))
        if error:
            return self._send_json(200, {"ok": False, "code": error})
        print("[admin] %s set stock for %s %s to %d" % (email, slug, size, value), flush=True)
        self._send_json(200, {"ok": True, "products": admin_inventory()})

    def _handle_admin_stats(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        if not self._require_admin(data):
            return
        self._send_json(200, {"ok": True, "stats": admin_stats()})

    def _handle_place_order(self):
        data = self._read_json(MAX_ORDER_BODY_BYTES)
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})

        number, token, order, error = create_order(data)
        if error:
            return self._send_json(400, {"ok": False, "code": error})

        link = "%s/order.html?order=%s&token=%s" % (self._base_url(), number, token)
        delivery = "none"
        try:
            delivery = send_email(build_order_email(order, link), link)
        except Exception as exc:  # noqa: BLE001
            # The order is already saved; a mail failure must not lose it.
            print("[mail] order confirmation failed for %s (%s: %s)"
                  % (number, exc.__class__.__name__, exc), flush=True)

        self._send_json(200, {
            "ok": True,
            "orderNumber": number,
            "token": token,
            "viewUrl": link,
            "delivery": delivery,
            "order": order,
        })

    def _handle_order_lookup(self):
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"ok": False, "code": "invalid_input"})
        order, error = find_order(data.get("orderNumber"), data.get("token"))
        if error:
            return self._send_json(200, {"ok": False, "code": error})
        self._send_json(200, {"ok": True, "order": order})

    def _base_url(self):
        """Base URL for links we email out.

        These links carry single-use tokens, so the scheme matters: an http://
        link would send the token in the clear before any redirect to https.
        KL_BASE_URL wins; otherwise trust Caddy's X-Forwarded-Proto, and assume
        https for anything that is not plainly a local dev host.
        """
        configured = os.environ.get("KL_BASE_URL", "").rstrip("/")
        if configured:
            return configured

        host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_address[1]}"
        forwarded = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        if forwarded in ("http", "https"):
            scheme = forwarded
        else:
            bare = host.split(":")[0].lower()
            local = bare in ("localhost", "127.0.0.1", "::1") or bare.endswith(".local")
            scheme = "http" if local else "https"
        return f"{scheme}://{host}"

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
                # Accounts created before this existed report no date rather
                # than a made-up one.
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
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

        payload = {"ok": True, "code": "success"}
        # Admin sessions are only ever minted after a successful password check.
        if is_admin(email):
            payload["admin"] = True
            payload["adminToken"] = create_admin_session(email)
            print(f"[admin] session started for {email}", flush=True)
        self._send_json(200, payload)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    server = http.server.ThreadingHTTPServer((BIND_HOST, port), Handler)
    print(f"Knight Labs server running at http://{BIND_HOST}:{port}/")
    if DATA_DIR != ROOT:
        print(f"Data directory: {DATA_DIR}")
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
