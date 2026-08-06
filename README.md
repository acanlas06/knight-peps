# Knight Labs Storefront

Static HTML/CSS/JavaScript storefront for the Knight Labs research-use peptide catalog, with a small Python standard-library backend for accounts, orders, admin status updates, and Zelle payment instructions.

## Local preview

Use `server.py` instead of `python -m http.server` for normal development. It serves the static files and exposes the local API endpoints for auth, checkout, order lookup, payment reporting, inventory, analytics, and admin views.

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
http://127.0.0.1:8123/checkout.html
```

`server.py` uses only the Python standard library. Accounts created via `account.html` are stored locally in `accounts.json` (gitignored) as a PBKDF2-HMAC-SHA256 hash with a random per-account salt — plaintext passwords are never written to disk. This is a local-dev auth store, not a production identity system.

To verify the auth endpoints directly, run the server in one terminal and, in another:

```bash
python verify_auth.py
```

If you only need to browse static pages and do not need sign in, checkout, order lookup, or admin APIs to work, `python -m http.server 8123 --bind 127.0.0.1` still works for static preview only.

## Zelle checkout setup

Checkout is Zelle-only for now. The site does **not** collect bank/card details and does **not** automatically mark orders paid. The flow is:

1. Customer submits checkout.
2. The backend creates an order with status `Pending Zelle Payment`.
3. The backend generates a unique memo/code, for example `KL-01008 ZELLE-HVRUKW`.
4. The confirmation and order pages show the exact Zelle recipient, amount, and memo.
5. The customer may click `I sent the Zelle payment`, which changes the order to `Payment Reported`.
6. Admin manually reconciles the Zelle deposit by amount + memo + sender/timing, then marks the order `Paid`.

Create a local Zelle config from the example file once the public Zelle recipient is ready:

```bash
cp zelle-config.example.json zelle-config.json
```

Edit `zelle-config.json`:

```json
{
  "recipient": "payments@example.com",
  "businessName": "Knight Labs",
  "holdHours": 24,
  "note": "Include the exact memo code so we can match your payment."
}
```

Only put the public Zelle email/phone/customer-facing payment handle in this file. Do **not** store bank login details, bank account numbers, passwords, API tokens, or other sensitive credentials. `zelle-config.json` is gitignored.

You can also override the public Zelle config with environment variables:

```bash
KL_ZELLE_RECIPIENT='payments@example.com' \
KL_ZELLE_BUSINESS_NAME='Knight Labs' \
KL_ZELLE_HOLD_HOURS='24' \
python server.py 8123
```

Until a real recipient is configured, checkout will show the placeholder `ZELLE_RECIPIENT_NOT_CONFIGURED`.

## Order/admin operations

Order statuses are:

- `Pending Zelle Payment` — order created; customer still needs to send Zelle.
- `Payment Reported` — customer clicked the report-payment button; admin still needs to verify receipt.
- `Paid` — admin confirmed the Zelle payment.
- `On its way` — order is being fulfilled/shipped/delivered.
- `Delivered` — fulfillment complete.
- `Cancelled` — order was cancelled.

Manual Zelle reconciliation checklist:

1. Open the admin dashboard.
2. Filter/review `Pending Zelle Payment` and `Payment Reported` orders.
3. Match the bank/Zelle activity against the order total and memo/code.
4. If the payment matches, change the order status to `Paid`.
5. Do not mark an order paid from the customer button alone; that button only records that the customer claims payment was sent.

## Notes

- Products are presented for research and laboratory use only.
- Public COA/testing/batch-documentation sections are intentionally deferred.
- Local records such as `accounts.json`, `orders.json`, `inventory.json`, `analytics.json`, admin config, SMTP config, and real Zelle config are gitignored.
