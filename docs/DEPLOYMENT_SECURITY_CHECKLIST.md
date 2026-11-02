# PythonAnywhere deployment and maintenance

Do not deploy blindly: production secret/HTTPS/static mappings are currently
unknown. Follow one step at a time. No production modification has been performed
by this audit. Preserve the existing working deployment until prerequisites pass.

## 1. Discover paths privately

In PythonAnywhere Web, note the WSGI path, virtualenv path, source directory and
HTTPS enforcement. In WSGI, confirm whether DATABASE_PATH and a stable SECRET_KEY
are set; do not print their secret values. The repository default database is
`two-teamers/instance/two-teamers.sqlite`; an override takes priority.

Review every static mapping. Never map the repository root, `instance`, backups,
home directory, `.git` or secret directory publicly. Application tests cannot
check mappings that bypass Flask. Confirm the production DB, journals, WAL/SHM
files and keys are outside public mappings. Restrict directories to the app
account (normally 700) and private files to 600, without breaking the host.
Enable MFA on PythonAnywhere, GitHub and Google; store recovery codes privately.

## 2. First backup, before code pull or migrations

Using the actual project virtualenv Python and database path, run the new backup
tool from a reviewed copy before deploying changed application code:

```bash
/actual/virtualenv/bin/python /actual/source/two-teamers/backup_database.py \
  --database /actual/private/two-teamers.sqlite \
  --destination /actual/private-backups/two-teamers
```

These are deliberately labelled placeholders; source/virtualenv paths have not
been confirmed. The helper uses only Python standard-library dependencies and
does not start Flask or run startup migrations. Before the new helper is
available, SQLite's `.backup` command can create a consistent private copy:

```bash
sqlite3 /actual/private/two-teamers.sqlite \
  ".backup '/actual/private-backups/before-security.sqlite'"
```

Create/protect the backup directory first. Never use an ordinary `cp` of a live
SQLite database as the sole backup, and never publish a database backup.

The helper copies a default VAPID key beside the database if present. For an
explicit key, pass `--private-key /actual/private/vapid.pem`. Back up the stable
Flask secret and deployment config separately using restricted secret storage;
the helper deliberately does not collect arbitrary environment variables.

## 3. Prove recovery and weekly scheduling

```bash
/actual/virtualenv/bin/python /actual/source/two-teamers/backup_database.py \
  --verify /actual/private-backups/two-teamers/backup-RETURNED_ID
/actual/virtualenv/bin/python /actual/source/two-teamers/backup_database.py \
  --restore-from /actual/private-backups/two-teamers/backup-RETURNED_ID \
  --restore-to /actual/private-restore-test.sqlite
```

The restore target must not exist. Inspect counts/integrity on the private copy;
do not point the live app at it for a drill. Recovery excludes secret/config
restoration and real consent reconciliation until those are exercised manually.

In PythonAnywhere Tasks, schedule a **daily** task running the same backup
command with `--if-due`. It creates a new snapshot when no matching verified
snapshot is less than **seven days** old. This avoids dependence on a weekly
scheduler feature and runs at most one snapshot per seven-day interval during
normal sequential execution. A failure/corrupt snapshot returns nonzero.
Review task output and the newest successful timestamp weekly; scheduling is
not yet configured and this helper is not an alerting service.

Keep a protected, preferably encrypted copy off-host. Host-only backups do not
protect against losing the host account or host storage. Proposed expiry: eight
weekly copies; owner approval is required before deletion/rotation. No automatic
backup deletion was introduced. Explain this to anyone handling erasure requests.

## 4. Review/pull/install

- Confirm reviewed changes are committed and pushed; this audit has not committed
  or pushed automatically. Record the previous revision and take the backup first.
- `git pull --ff-only` in the actual source checkout; do not reset local changes.
- In the actual virtualenv: upgrade pip to a patched version (at least 26.2),
  then `python -m pip install --upgrade -r requirements.txt`.
- Cryptography now requires at least 50.0.0. Do not silently use an older version
  if a wheel/build fails: select a supported PythonAnywhere interpreter/wheel or
  resolve supported OpenSSL/Rust build requirements and test first.
- Run `python -m pip check`, focused tests and a dependency advisory scan.
  Test tools can use an isolated virtualenv rather than changing the live one.

## 5. Production settings, then reload

- `create_app()` is production by default and rejects missing/short/default
  signing keys. Confirm the existing private random secret has at least 32
  characters; keep it unchanged if safe. If missing/compromised, create a new
  random secret privately, plan session/offline invalidation and assess incident
  exposure. Do not copy a sample key from docs.
- `SESSION_COOKIE_SECURE=1` is required. Enforce HTTPS in PythonAnywhere and
  verify the WSGI scheme is correct; do not trust arbitrary forwarded headers.
- Production must use WSGI, not `python run.py` or debugger/reloader. Local
  `python run.py` explicitly opts into development and is not production.
- Verify DATABASE_PATH, fixture paths and stable VAPID settings match scheduled
  push tasks. Confirm REWARDED_ADS_ENABLED remains off; analytics consent does
  not authorise advertising.
- Startup migrations are additive (including auth_attempts); no production
  retention deletion is scheduled. Reload from PythonAnywhere Web and inspect
  private error logs before allowing traffic.

## 6. Live smoke test with your own test accounts only

Verify login/signup/profile/logout, two-account isolation, normal guesses,
offline download and sync, CSRF failures, notification preference changes and
device removal. Check HTTPS cookies/headers and real client-address limiting
without locking out other users.

On a clean browser: no Google requests before choice, none after rejection,
requests only after acceptance, footer withdrawal stops future tracking and
removes accessible standard cookies; test another tab, mobile and blocked storage.
Never use production users for testing.

Inspect host mappings and probe known private-path URLs without downloading
sensitive data. Require 404/403 and no content disclosure. A handful of probes
cannot establish that all possible files are protected.

## 7. Rollback

If startup fails, leave traffic/tasks paused and fix settings or redeploy the
recorded prior revision. Remember the old revision may restore unsafe defaults
and immediate analytics: rollback is not itself a security fix. Added tables
can remain. Do not delete them or reset the database.

If data restoration is necessary, pause writes/tasks, verify a snapshot, create
a new private recovered file, reconcile deletions/consent and switch the
configured database path deliberately. Preserve the original and key/config.
Do not overwrite a live SQLite database.

## Ongoing schedule

- Daily: scheduled backup due-check; inspect failure notices/task dashboard.
- Weekly: confirm successful backup age, copy off-host, check access/log anomalies.
- Monthly: dependency audit/patch rehearsal, access/MFA and privacy settings review.
- Quarterly: isolated restore and incident drill; review retention/erasure records.
- Before ads, marketing, prizes, payments or new targeting: security/privacy and
  children's risk assessment, supplier/transfer review and updated notices.

Retention cleanup is **not** activated by this deployment. Run
`cleanup_retention.py --database ...` for counts only. After approving the proposed
periods and taking a fresh backup, `--confirm-delete --backup <snapshot-directory>`
applies cleanup. Account and subscription lifecycle still need a separate policy.
