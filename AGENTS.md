# Knight Labs Storefront — Agent Instructions

## Project Summary

Static HTML/CSS/JavaScript storefront mockup for the Knight Labs research-use peptide catalog.

Current user-approved direction:

- Visual style: black/gold premium lab/storefront feel.
- Primary flow: Shop categories → product cards → product detail → cart → checkout → confirmation.
- Products and copy must stay framed as research/laboratory-use oriented.
- Checkout is currently static/client-side and does not process real payments.
- Public COA/testing/batch-documentation sections are intentionally deferred unless the user asks to add them.

## Local Preview

Run from this directory (serves static pages plus the `/api/signup` and
`/api/signin` auth endpoints used by `account.html`):

```bash
python server.py 8123
```

For static-only browsing (no sign-in/create-account), plain `http.server` still works:

```bash
python -m http.server 8123 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8123/
http://127.0.0.1:8123/supply-categories.html
http://127.0.0.1:8123/cart.html
http://127.0.0.1:8123/checkout.html
http://127.0.0.1:8123/mobile-preview.html
```

## Important Files / Patterns

- `index.html` — landing/home entry.
- `supply-categories.html` — shop/category entry.
- `category-*.html` — category pages.
- `product-*.html` — individual product detail pages.
- `cart.html` — static/client-side cart page.
- `checkout.html` — static checkout mockup.
- `order-confirmation.html` — post-checkout confirmation page.
- `assets/` — image assets.
- `server.py` — stdlib-only local dev server: serves the static site and the `/api/signup`/`/api/signin` auth endpoints backing `account.html`. Stores salted PBKDF2 password hashes in `accounts.json` (gitignored, never plaintext).
- `verify_auth.py` — small script exercising the auth endpoints (signup, wrong email, wrong password, success).
- `build_product_pages.py` and `add_*.py` scripts — prior one-off generation/update helpers. Inspect before reusing; do not assume they are the source of truth.

## Development Rules

1. Preserve the black/gold Knight Labs visual identity unless the user requests a redesign.
2. Keep pages static and dependency-light by default: plain HTML, CSS, and JavaScript.
3. Maintain consistent navigation and cart/checkout affordances across all product/category pages.
4. Do not add real payment processing, medical claims, credential collection, or backend behavior unless explicitly requested. (Local account sign-in/create-account via `server.py` was explicitly requested and added — see `server.py`/`verify_auth.py`. Do not expand this into a real production auth system without a new explicit request.)
5. Keep peptide/product copy cautious and research-use oriented.
6. For broad product/page changes, update all affected product/category pages consistently rather than one page only.
7. Prefer small, targeted edits. If generating pages with scripts, inspect the diff afterward.
8. Avoid exposing secrets or adding API keys to the repo.

## Verification Checklist

Before claiming changes are complete:

1. Start the local server:

   ```bash
   python -m http.server 8123 --bind 127.0.0.1
   ```

2. Use browser verification for the affected pages.
3. Check the console for JavaScript errors.
4. Exercise the relevant flow, especially:
   - category navigation
   - product detail page
   - add-to-cart / cart state
   - checkout page readability and contrast
   - order confirmation link/flow if touched
5. Verify mobile layout if the change affects responsive UI.
6. Inspect `git diff` before committing or reporting final status.

## Useful Skills

Load these Hermes skills when relevant:

- `frontend-design` — visual/interface improvements.
- `verification-before-completion` — before saying the site is done/working.
- `using-git-worktrees` — for risky or parallel feature work.
- `finishing-a-development-branch` — when wrapping up PR/merge/branch work.
- `receiving-code-review` / `requesting-code-review` — for review cycles.
