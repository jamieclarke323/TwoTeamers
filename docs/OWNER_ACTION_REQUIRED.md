# Owner actions, in priority order

## Before deploying

1. **Check PythonAnywhere privately:** confirm a unique stable random SECRET_KEY,
   HTTPS, Secure session cookies, WSGI (not debug) and no public mapping to the
   database, repository root, keys or backups. Do not send secret values.
   The hardened app intentionally refuses unsafe production startup.
2. **Make the first consistent backup and test recovery to a new private file.**
   Follow [the deployment checklist](DEPLOYMENT_SECURITY_CHECKLIST.md), starting
   with confirming actual paths. Your live virtualenv/source/database paths are
   not known here; do not paste placeholder commands unchanged.
3. Install patched dependencies and test in the production-compatible interpreter
   before reloading. The dependency scan found cryptography/pip advisories;
   local checks do not prove your host has the patched versions.
4. Review the new consent flow and privacy wording. It blocks Analytics before
   acceptance; analytics-only permission does not cover future advertising.

## Set up the requested seven-day backups

Use a daily PythonAnywhere task with `backup_database.py --if-due`; it creates
a snapshot when the last verified one is at least seven days old. Scheduling
must be done in your account; it has not been activated here.
Keep backups private and copy them off-host securely. Keep VAPID and Flask keys
recoverable. Approve an expiry policy (proposed: eight weekly snapshots) before
automatic deletion is added. Record a successful restore drill.

## Privacy decisions still required

- Approve or change proposed cleanup periods: guest records inactive 90 days,
  push delivery/legacy send history 90 days, offline session records seven days,
  security buckets one hour. The supplied tool previews first; production
  deletion needs a matching verified backup less than 24 hours old.
- Define account inactivity, stale subscriptions, request handling and backup
  erasure policy. Turning reminders off suppresses delivery; it does not erase
  every account/subscription automatically. Device removal now removes that
  browser subscription. No production records were deleted.
- In Google Analytics Admin: verify Signals/ads links/user-ID are off, minimise
  retention/reset extension, review enhanced measurement and sharing. Code cannot
  verify your Admin settings. Record Google/PythonAnywhere agreements, data
  locations and international-transfer safeguards.
- Complete the [ICO fee checker](https://ico.org.uk/fee-checker).
- Assess likely child users with a proportionate DPIA and age-appropriate notice.
  Get advice if collecting data from known under-13s or targeting children.
  A banner alone is not proof of valid child/parental consent.
- Identify actual EU/US audience/monitoring and business scale before concluding
  which international laws apply. Worldwide availability is not the whole test.

## Accepted product decision

You expressly accept readable offline answers and the possibility of self-score
inflation for leaderboards without prizes. That behaviour was not restricted.
Revisit before paid entry or prizes.

## Incident readiness and future changes

Read [the incident runbook](INCIDENT_RESPONSE.md), keep private recovery contacts/
codes accessible, and practise containment plus the risk-based 72-hour reporting
assessment. No current breach is alleged.

Enable MFA for host/GitHub/Google and remove unused credentials. Do not introduce
advertising, marketing email, payments or prizes under today's assumptions.
Those are future decisions requiring fresh privacy/security/consumer review,
not features silently enabled by this audit.

No paid service was purchased, live secret changed, production data deleted,
geographic restriction introduced or claim of worldwide compliance made.
