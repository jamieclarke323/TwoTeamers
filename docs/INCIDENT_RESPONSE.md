# Two Teamers incident and personal-data breach runbook

Owner: Jamie Clarke. Public privacy contact: twoteamerssupport@gmail.com.
Keep private hosting/GitHub/Google recovery contacts, support references and
emergency access codes outside Git. This runbook is a template for action, not
evidence that a breach has occurred.

## First hour: contain and preserve

1. Record awareness time in UTC, who discovered it, symptoms and affected systems.
   Examples: unknown logins, unexpected account changes, public database URL,
   unusual push sends, new deployment key, leaked secret, missing database.
2. Stop the suspected exposure: remove public mappings, disable affected web
   functionality/tasks or use hosting maintenance controls. Do not wipe/rebuild
   before preserving evidence. Disable push tasks if endpoint/key abuse is suspected.
3. Use a known-safe device/account. Secure PythonAnywhere, GitHub, email and Google
   access; revoke unknown sessions/keys and enable MFA. Do not share secrets in chat.
4. Preserve logs, relevant timestamps, deployment revision, configuration-change
   history and a consistent database snapshot to restricted private storage.
   Record who copied/accessed evidence and hashes. Do not upload user data to
   public issues, external analysis tools or this repository.
5. Contact hosting support if host access/exposure is involved. Record actions.
   Notify insurer/law enforcement/NCSC where appropriate, not as a substitute for
   regulator obligations.

## Same day: assess scope and notification

- Determine confidentiality, integrity and availability impact: accounts/emails,
  password hashes, scores, sessions, guest identifiers, push endpoints/keys,
  children, backups and logs. Estimate people/records, exposure duration,
  download evidence and whether access remains possible. Distinguish evidence
  from unknowns; no observed download does not prove no disclosure.
- Identify threat actor/access route and which credentials were exposed.
  Rotate affected credentials in a controlled order. Secret-key rotation logs
  users out and invalidates signed offline tokens; VAPID replacement requires
  device resubscription. Assess password resets if hashes were exposed; there
  is no automated password-recovery service in this application.
- **UK GDPR:** notify ICO without undue delay and, where feasible, within
  **72 hours of awareness**, unless unlikely to risk individuals' rights and
  freedoms. Do not wait for perfect certainty; provide available information,
  explain delays and follow up in stages when necessary.
- If likely **high risk**, inform affected individuals without undue delay,
  clearly describing the incident, likely effects, mitigation and contact route,
  unless a relevant legal exception applies. Do not expose recipients to one
  another in bulk email.
- Record every breach and the notification/no-notification rationale. Not every
  security alert is a personal-data breach and not every breach is reportable.
  If EU/other regimes apply, assess their regulators/deadlines separately.

Official guidance: [ICO personal-data breaches](https://ico.org.uk/for-organisations/report-a-breach/personal-data-breach/personal-data-breaches-a-guide/).
Use the current reporting channel from the ICO website, not a copied phone number.

## Restore and reopen

1. Fix/isolate the root cause before restoring. Rebuild compromised hosts/access
   paths where necessary; do not trust a backup created after compromise blindly.
2. Pause app writes and scheduled tasks. Verify the selected backup checksums,
   integrity and provenance. Restore to a new private file first using
   `backup_database.py --restore-from ... --restore-to ...`.
3. Inspect synthetic or authorised account behaviour, score counts, permissions
   and VAPID continuity. Preserve the incident database separately.
4. Reapply verified account erasures and consent withdrawals since the snapshot.
   A database rollback can revive subscriptions/preferences; do not restart push
   until these are reconciled.
5. Switch the configured database path/reload safely with a rollback plan.
   Test HTTPS, account isolation, Analytics rejection, notification preferences
   and protected file paths. Re-enable tasks only after verification.
6. Watch errors/traffic, confirm affected-user communications, and retain an
   incident record in restricted storage for a justified period.

## Private incident record fields

Incident ID; awareness/detection/event times; reporter; facts and uncertainties;
systems and data categories; affected groups including children; number/range;
evidence hashes/location/access; impact/likelihood assessment; containment and
credential actions; reportability decision/reasons/time; ICO reference and
updates; user communications; restoration checks; erasure/consent reconciliation;
root cause; corrective action owner/deadline; review/retention date.

## Rehearsal

Before deployment and quarterly: simulate a publicly exposed database report,
find the host setting that closes access, locate a verified backup, restore
to an isolated copy and practise the 72-hour assessment without sending a real
breach report or contacting real users.
