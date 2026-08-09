# Knight Labs Storefront

Static HTML/CSS/JavaScript storefront mockup for the Knight Labs research-use peptide catalog.

## Local preview

The account page (`account.html`) needs the small local auth backend, so use
`server.py` instead of `python -m http.server`. It serves the same static
files and additionally exposes the `/api/signup` and `/api/signin` endpoints.

From this folder:

```bash
python server.py 8123
```

Then open:

```text
http://127.0.0.1:8123/
http://127.0.0.1:8123/supply-categories.html
http://127.0.0.1:8123/mobile-preview.html
http://127.0.0.1:8123/account.html
```

`server.py` uses only the Python standard library. Accounts created via
`account.html` are stored locally in `accounts.json` (gitignored) as a
PBKDF2-HMAC-SHA256 hash with a random per-account salt — plaintext passwords
are never written to disk. This is a local-dev auth store, not a production
identity system.

To verify the auth endpoints directly, run the server in one terminal and,
in another:

```bash
python verify_auth.py
```

To verify the affiliate-code math directly:

```bash
python verify_affiliate.py
```

## Affiliate / promo codes

Phase 1 affiliate support is controlled server-side in `server.py` and previewed
client-side through `assets/affiliate.js`.

Current code:

```text
AC = 15% off
```

Affiliate links can use:

```text
/?ref=AC
/supply-categories.html?ref=AC
```

The browser remembers the code while the customer shops, checkout shows the
subtotal/discount/total, and `/api/place-order` validates the code again before
saving the order. Orders store the affiliate code, percent, discount amount,
subtotal, and final total so the confirmation, order page, account dashboard,
and admin dashboard can display it.

If you only need to browse the static pages and don't need sign in/create
account to work, `python -m http.server 8123 --bind 127.0.0.1` still works
as before.

## Notes

- Products are presented for research and laboratory use only.
- Public COA/testing/batch-documentation sections are intentionally deferred.
- Current checkout is static/client-side and does not process payments yet.
