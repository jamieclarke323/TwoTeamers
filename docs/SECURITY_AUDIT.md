# Two Teamers security audit

Date: 2 November 2026. Scope: repository source, reachable local Git history,
local synthetic tests, dependency advisories and deployment documentation.
This is not a production penetration test, legal opinion or security guarantee.

## Architecture and trust boundaries

- Flask application factory; raw parameterised SQLite, not SQLAlchemy.
- Email/password/team accounts with Werkzeug password hashes; signed Flask
  session cookies identify accounts. No password-reset or privileged account
  management service was found.
- Account and guest quiz progress are stored separately. Account IDs come from
  the signed session, not a submitted user ID.
- The public `/admin` and `/admin/matchup` routes are roster lookup tools, not
  account administration. They reveal football answers, not private account data.
- Offline packages contain readable answers. Signed owner-bound tokens protect
  replay into the wrong account, but cannot prove honest offline gameplay.
- Web Push uses browser subscription endpoints, optional per-account categories,
  VAPID signing keys and scheduled Python scripts. There is no public test-send
  endpoint. Subscription and preference writes have login and CSRF checks.
- GA4 is the only analytics integration found. An optional AdSense integration
  exists behind settings; the owner says advertising is not currently used.
  Do not enable it under the analytics-only consent choice.
- Service worker caches selected static assets and explicitly downloaded quiz
  pages, not ordinary account pages or arbitrary cross-origin resources.

## Findings and remediation

| ID | Severity | Evidence/root cause | Change/status |
|---|---|---|---|
| S1 | High, conditional | Public fallback Flask signing key in the original app configuration; forged cookies could select another account if deployed without a real secret | Removed fallback. Production startup rejects missing/short/known-default keys and insecure session cookies. Production value still needs owner verification; no live secret was changed |
| S2 | Medium | Shared header loaded GA4 on every online visit before a privacy choice | Replaced with local consent script. No Google script/request before acceptance; equal reject/accept actions, 180-day local choice, footer withdrawal, disable flag, standard cookie cleanup and reload |
| S3 | Medium, accepted product limitation | Offline packages disclose accepted answers, which can also be entered online for ordinary scores | Owner explicitly accepts this for non-prize leaderboards. No restriction added; must revisit before prizes/paid entry |
| S4 | Low privacy/operational gap | Guest progress and push delivery history lacked expiry automation | Preview-first cleanup tool supplied. Proposed 90-day guest/delivery limits require approval and a fresh verified backup before applying. Not scheduled or run against production |
| S5 | Medium operational gap | Owner confirms no current production backup procedure | Weekly-due SQLite snapshot tool with private files, VAPID copy, checksums, integrity/foreign-key validation and non-overwriting recovery copy. Local recovery tested; production scheduling and off-host copy remain owner actions |
| S6 | Medium defence-in-depth | No general CSRF protection for account/game changes or application auth throttles | Added session CSRF tokens, cross-site Origin/Fetch Metadata rejection, shared SQLite auth throttles and payload limits |
| S7 | Low defence-in-depth | Security headers were not consistently set | Added anti-framing, MIME protection, referrer/permissions policy, HTTPS-only HSTS and a limited CSP; private HTML and push responses use no-store |
| S8 | Dependency advisory | Local cryptography 48.0.1 scan reported PYSEC-2026-3552/3553/3554; local pip 26.0.1 had installation-tool advisories | Raised cryptography floor to 50.0.0; upgrade deployment pip to a patched release. Affected cryptography certificate-verifier/PKCS7 APIs are not directly used by app code; this is not a demonstrated remote app exploit |

## Important implementation details

Production is the default for `create_app()`. Set a unique random `SECRET_KEY`
of at least 32 characters outside Git and keep it stable. Development is
explicit only when invoking `python run.py`; tests explicitly opt into test
settings. Changing an existing secret logs users out and invalidates offline
sync tokens. Do not rotate one casually or paste it into a support chat.

CSRF protects signup, login, profile, logout, game actions and offline downloads.
Push retains its existing independent CSRF token. Offline refresh/sync require
JSON and expiring owner-bound signed download tokens, and still reject
cross-origin browser requests; they deliberately do not depend on a stale
token embedded in a cached page. The shared request helper adds the online token
to same-origin game writes. Old online tabs may need reloading after deployment.

Login allows 60 attempts per network address and 20 per normalised email in
15 minutes; signup allows 10 per network address per hour. Buckets are HMACed
with the app secret; raw IPs/emails are not stored in the limiter. Old buckets
are removed during authentication requests and by the maintenance tool. This
is not distributed bot protection. It uses WSGI `REMOTE_ADDR`, not untrusted
forwarded headers. Verify PythonAnywhere supplies the real client address;
shared networks may encounter limits. Errors return HTTP 429 and Retry-After.

The CSP currently restricts objects, base URLs, framing and form destinations.
It is **not** a full script-source/XSS policy: existing inline JSON/scripts and
future advertising require a separate nonce/source design. HTTPS enforcement,
trusted host configuration, server error handling and static mappings must also
be checked at the host. HSTS is sent only on HTTPS responses, without subdomains
or preload commitments.

The 256 KiB request cap bounds oversized input, but does not stop distributed
traffic or exhaustively bound every possible query. Authentication has password
and email length caps. Passwords remain hashed, never logged by these changes.

## Secret and exposure checks

- No tracked SQLite/database, `.env`, private-key or `.key` file was listed.
- A scan of 294 unique text blobs in reachable local Git history found no
  PEM private-key header or recognised GitHub/AWS token candidate. This is a
  limited-format scan, not proof of no secrets; remote/deleted history, generic
  credentials, GitHub Actions settings and hosting files were not verified.
- The database defaults to `two-teamers/instance`, outside Flask static.
  No application database-download route was found. Host static mappings could
  bypass Flask entirely and MUST be inspected before asserting non-exposure.
- Generated VAPID keys use owner-only files and an ignored directory. Protect
  the containing directory, backups and any explicit key path on production.
- Never publicly publish detailed findings while an exposed production setup
  remains unresolved; these documents contain no live secrets or user records.

## Verification and limits

Focused tests cover unsafe startup, real CSRF enforcement, cross-origin rejection,
signed offline sync, auth rate limiting, account isolation, backup/recovery,
retention preview and consent-free HTML. Existing offline/push regressions are
also run. Browser checks intercept Google requests: they prove gating, not GA
dashboard receipt. Refer to the final delivery report for executed results.

Executed locally:

- Final combined focused run: **119 passed** with cryptography **50.0.2**, including backup
  restoration, seven-day due guard, production-secret rejection, CSRF, account
  isolation, offline and push regressions.
- The combined run includes **10 midnight/UI tests** and four explicit
  subscription isolation/preference tests. Earlier selective authentication
  regressions also passed; do not add overlapping earlier runs to the total.
- `pip-audit --local`: **no known vulnerabilities found** after upgrading the
  isolated environment to cryptography 50.0.2 and pip 26.2.2. `pip check` passed.
  The earlier scan found seven distinct advisory IDs, duplicated in its output.
- Python compilation, Pylance diagnostics for the new security/backup/retention
  modules, and `git diff --check` passed.
- Browser consent check with Google intercepted: first visit zero Google scripts;
  rejection persisted with zero scripts; acceptance loaded one mock tag;
  accepted choice persisted; withdrawal reloaded with zero scripts and removed
  the test `_ga` cookie. No real analytics event was sent by this test.
- Follow-up mobile/multi-tab checks did not complete because the browser page
  became unavailable; those checks remain manual deployment requirements.
- A full-suite attempt was stopped after slow real-workbook setup made it
  impractical. It is **not** reported as passed. Focused fixtures exercise the
  changed paths without repeatedly loading all production spreadsheets.

The patched cryptography wheel was unavailable for this local macOS interpreter.
A checksum-verified official OpenSSL source build in task-local storage allowed
testing cryptography 50.0.2 without modifying system OpenSSL. This local build is
not part of production deployment; use supported host wheels/build requirements.

Dependency scans describe the tested environment, not packages installed on
PythonAnywhere. No live credentials, production data, production penetration
tests, actual push receipt or infrastructure settings were examined.

Remaining security work includes host verification, practical restore drills,
monitoring, full CSP, session revocation beyond ordinary client logout, complete
account lifecycle/verified recovery, and specialist review before monetisation.
