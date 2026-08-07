# Deploying Knight Labs to Hetzner

Everything here is tested. Follow it in order — the DNS step gates HTTPS, and
HTTPS gates going live safely, because the site accepts passwords.

Target: Hetzner **CX22** in **Ashburn, Virginia** (~$4.59/mo, 2 vCPU, 4 GB RAM,
40 GB NVMe, 20 TB traffic).

---

## 1. Get a domain

HTTPS certificates cannot be issued for a bare IP address, so a domain is
required before the site can safely take passwords.

- Your **GitHub Student Developer Pack** includes a free `.me` domain for a year
  from Namecheap.
- Or any `.com` for roughly $10–15/year.

You do not need to configure it yet. Just have it registered.

## 2. Create the server

1. Sign up at hetzner.com/cloud and create a project.
2. **Add your SSH key first** (Security → SSH Keys). Do this before creating the
   server — otherwise Hetzner emails you a root password, which is worse.
3. New server:
   - Location: **Ashburn, VA**
   - Image: **Ubuntu 24.04**
   - Type: **CX22** (shared vCPU, x86)
   - SSH key: the one you just added
4. Note the public IPv4 address.

> I can't do this part for you — it needs your account and payment details, and
> I don't handle credentials.

## 3. Point DNS at it

At your registrar, create two records:

| Type | Name | Value |
|------|------|-------|
| A | `@` | your server IP |
| A | `www` | your server IP |

Verify before continuing — Caddy will fail to get a certificate otherwise:

```bash
nslookup yourdomain.com
```

DNS can take anywhere from a minute to a couple of hours to propagate.

## 4. Run setup

SSH in and run one command:

```bash
ssh root@YOUR_SERVER_IP
curl -fsSL https://raw.githubusercontent.com/acanlas06/knight-peps/main/deploy/setup.sh \
  | bash -s yourdomain.com
```

Prefer to read it first (sensible for anything piped to bash):

```bash
git clone https://github.com/acanlas06/knight-peps.git /tmp/kl
less /tmp/kl/deploy/setup.sh
bash /tmp/kl/deploy/setup.sh yourdomain.com
```

This installs Python and Caddy, creates an unprivileged `knightlabs` user,
clones the app to `/opt/knight-labs`, puts live data in `/var/lib/knight-labs`,
installs the service and HTTPS config, enables the firewall and automatic
security updates, and schedules nightly backups.

## 5. Add your secrets

These are deliberately **not** in git.

**Mail** — paste your Gmail app password:

```bash
nano /var/lib/knight-labs/smtp-config.json
systemctl restart knight-labs
```

**Admin access** — register your account on the live site first, then:

```bash
nano /var/lib/knight-labs/admin-config.json
```

```json
{ "admins": ["knightpeps@gmail.com"] }
```

No restart needed; the allowlist is read on every request.

## 6. Check it

```bash
systemctl status knight-labs caddy
journalctl -u knight-labs -n 30
curl -I https://yourdomain.com
```

Then in a browser, confirm:

- [ ] `https://` with a valid padlock, and `http://` redirects to it
- [ ] Sign up, sign in, password reset email arrives
- [ ] Place an order — confirmation email arrives with the Zelle panel
- [ ] Admin sign-in reaches the dashboard; set a status; set stock
- [ ] `https://yourdomain.com/orders.json` returns **404**, not your order data

That last one matters. Verify it.

---

## Day to day

**Deploy new code** (after pushing to `main`):

```bash
sudo bash /opt/knight-labs/deploy/update.sh
```

It health-checks afterwards and rolls back automatically if the site stops
answering.

**Logs:**

```bash
journalctl -u knight-labs -f
tail -f /var/log/caddy/knight-labs.log
```

**Backups** run nightly at 03:15 into `/var/lib/knight-labs/backups`, keeping 30
days. `smtp-config.json` is excluded on purpose — a backup archive is a poor
place for a password. Pull a copy down periodically:

```bash
scp root@YOUR_IP:/var/lib/knight-labs/backups/*.tar.gz ./
```

An on-server backup does not protect you from losing the server. Get them off
the box.

---

## Design notes

**Data lives outside the checkout.** `KL_DATA_DIR=/var/lib/knight-labs`, so
`git reset --hard` during a deploy can never delete orders or accounts.

**The Python server binds `127.0.0.1` only.** It is not reachable from the
internet at all; Caddy is the sole public listener and terminates TLS.

**The service runs unprivileged** with systemd hardening (`ProtectSystem=strict`,
`NoNewPrivileges`, a single `ReadWritePaths`). A compromise of the app cannot
write outside its data directory.

**Caddy 404s the data files** — `orders.json`, `accounts.json`, the configs,
`/outbox/`, `/deploy/`, `/.git/` and any `.py`/`.sh`/`.bat`. Defence in depth in
case a file ever lands in the app directory.

**Restarts are automatic** on crash and on reboot.

---

## Known limitations

**Storage is JSON files on one server.** Fine at low volume. Concurrent writes
are serialised by a lock, but there is no transactional guarantee and no
replication. If order volume becomes real, move to SQLite or Postgres before it
bites.

**No staging environment.** Deploys go straight to production; the health check
and auto-rollback are the safety net, not a substitute for one.

**Gmail sending caps at roughly 500 messages/day** and personal-account mail is
more likely to hit spam folders. For real volume, move to Resend or SendGrid —
only `smtp-config.json` changes.

**Check Hetzner's acceptable-use policy** for your product category before
launch, and confirm your bank permits Zelle for business use. Better to know now
than after a suspension.
