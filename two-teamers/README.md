# Two Teamers

A Flask quiz covering players who represented both clubs in a fixture. The current release supports every 2026/27 Premier League fixture and discovers all 92 clubs for the team selector.

## Run locally

Initials clues preserve hyphens within a name: Bradley Wright-Phillips is `B.W-P.`, Jean-Philippe Mateta is `J-P.M.`, and space-separated Tal Ben Haim remains `T.B.H.`. The existing final full stop is retained. This applies online and to newly downloaded or refreshed offline games.

Submitted answers use rounded RapidFuzz similarity scores. Each cleaned acceptable name variant with nine or more letters/digits (excluding spaces) accepts scores of 78 or above, reports "Close but not quite." at 65–77, and rejects lower scores. Shorter variants retain the 90/70 thresholds. Exact matches always take priority; otherwise a qualifying correct match takes priority over a near match, then the higher score wins within each category. The same rules apply offline and during offline sync. Automatic acceptance while typing remains exact-only.

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

Open `http://127.0.0.1:5000`. Set `BYPASS_AVAILABILITY=1` to test every fixture outside its live window.

All regular and featured games unlock at **00:00 UK time on their fixture date**, regardless of kick-off time. For example, a fixture dated 24 October 2026 opens at 00:00 on 24 October, not the following night. The home page shows an upcoming supported-team fixture greyed out with a padlock until it opens. Games close according to `PLAYABLE_HOURS` in `app/data_loader.py`.

The home page displays live closing countdowns that tick every second in the card's body font and turn red during the final hour: the Daily Game counts down to the next UK midnight after its featured date, while a playable My Team game uses its existing `lock_at` deadline and therefore follows changes to `PLAYABLE_HOURS`. The two countdowns intentionally differ even when they represent the same fixture. At zero, a countdown reads "Closed"; this display does not change game availability rules.

Once all answers are guessed or revealed, or the player gives up, the home card instead displays the final players-found score (matching Share result, not the frozen competition score). Its countdown reads "Next game starts in": the Daily Game uses next UK midnight even if that day's fixture is not scheduled, and My Team uses the earliest future unlock time of a supported-team fixture with answers. If no such team fixture exists it reads "Next game not scheduled". At zero, next-game timers prompt a refresh rather than claiming a fixture is available. Results use the signed-in account or existing guest session; reset returns the card to its unfinished state. Unsynced offline results appear after syncing.

Production must set a unique random `SECRET_KEY` of at least 32 characters and `SESSION_COOKIE_SECURE=1`, plus persistent `DATABASE_PATH`, `FIXTURES_DIR`, and `PLAYERS_XLSX_PATH` values. Unsafe production session settings fail at startup. `python run.py` explicitly opts into local development; production must use WSGI, not the debug server. Keep an existing safe secret stable: rotating it invalidates sessions and offline sync tokens.

## Security, backups and recovery

### Admin access

Both `/admin` and `/admin/matchup` require the shared admin password, independently of normal account login. Configure `ADMIN_PASSWORD_HASH` with a Werkzeug password hash loaded from a private file outside the repository; never commit the password or its hash. If absent, admin access fails closed with HTTP 503. Successful access lasts one hour and changing the configured hash invalidates existing admin grants. Forms require the existing CSRF token. Five failed password attempts from the same IP address cause a ten-minute lockout (HTTP 429 with `Retry-After`), persisted in SQLite so clearing cookies or changing browser does not reset it. Shared-IP users share the attempt limit. Failed attempts reset after a successful login or expiry of a lockout. HTTPS and a strong password are recommended; a short numeric password is weak even with throttling.

Generate a private hash file on the deployment host using the project's Python:

```python
import getpass
import os
from pathlib import Path
from werkzeug.security import generate_password_hash

path = Path.home() / ".secrets" / "twoteamers-admin-password-hash"
path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
password = getpass.getpass("Admin password: ")
if not password:
    raise ValueError("An admin password is required.")
with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
    file.write(generate_password_hash(password) + "\n")
```

In WSGI, before calling `create_app()`, load it with `os.environ["ADMIN_PASSWORD_HASH"] = (Path.home() / ".secrets" / "twoteamers-admin-password-hash").read_text().strip()` (import `Path` from `pathlib`). Reload the web app. Back up this private configuration securely; never expose `.secrets` through static mappings.

Start with [owner actions](../docs/OWNER_ACTION_REQUIRED.md) and the [PythonAnywhere deployment checklist](../docs/DEPLOYMENT_SECURITY_CHECKLIST.md). The [security audit](../docs/SECURITY_AUDIT.md), [privacy assessment](../docs/PRIVACY_COMPLIANCE_AUDIT.md), [risk register](../docs/RISK_REGISTER.md) and [incident runbook](../docs/INCIDENT_RESPONSE.md) distinguish local fixes from unverified hosting/legal obligations.

CSRF tokens protect account and game writes, with signed owner-bound tokens protecting offline sync. Authentication attempts are rate-limited in SQLite, and baseline security headers apply. Reload old online tabs after deploying the new request helper. Analytics permission does not authorise the optional AdSense integration.

`backup_database.py --destination /private/path/outside/repository --if-due` creates a verified SQLite snapshot when the newest matching verified backup is at least seven days old. Schedule that command daily in PythonAnywhere; scheduling and off-host copies require owner action. The script does not start the app or alter the source database. It includes the default VAPID key if present; pass `--private-key` for a custom key. `--verify <backup-directory>` checks a snapshot; `--restore-from <backup-directory> --restore-to <new-private-file>` creates a non-overwriting recovery copy. Back up the stable Flask secret separately and reconcile erasures/consent before a real restoration.

`cleanup_retention.py` previews proposed cleanup (90-day stale guest/delivery records, seven-day offline session records, one-hour auth buckets). It does not delete by default; `--confirm-delete --backup <fresh-matching-backup-directory>` is required to apply. Approve retention and backup expiry before activating production cleanup; no existing production data or backups have been deleted.

## Privacy Policy

The public `/privacy-policy` page displays the policy, updated in November 2026 to disclose Google Analytics. A small link in the shared footer makes it accessible from all standard pages and newly downloaded offline quiz pages (opening the policy requires a connection). Update `app/templates/privacy_policy.html` when the policy changes.

## Google Analytics

Online pages offer equally accessible **Reject analytics** and **Accept analytics** choices. Google Analytics (`G-XZLDYJXQ8V`) is not loaded until acceptance. The choice is stored locally for up to 180 days; **Cookie settings** in the footer lets visitors change it. Withdrawal disables Analytics, removes accessible standard `_ga` cookies and reloads the page. Other open tabs reload when the choice changes. Blocked storage defaults to no automatic tracking; an explicit choice may need repeating on subsequent pages.

The tag disables Google Signals/advertising personalisation signals and sends a page location without its query string. Verify GA Admin retention, enhanced measurement, sharing and transfer settings separately. Newly downloaded offline quiz pages omit Analytics and consent UI. Existing offline downloads and old online tabs may need refreshing after deployment. No advertising or marketing consent is collected.

## How to play

The home page and quiz pages share the same **How to play** dialog. It opens automatically after a three-second delay for logged-out visitors on their first visit in that browser, or after more than seven days without a visit. Logged-in visitors and visitors seen within the last seven days do not get the automatic prompt. Every page visit refreshes the browser-local `two-teamers-last-visit` timestamp; clearing browser storage makes the next visit a first visit again. The **How to play** button remains available on the home page and playable quizzes for everyone; it opens immediately and cancels any pending automatic opening.

On mobile screens (up to 560px wide), the entire dialog is scaled to two thirds of its previous width and height. Content remains scrollable when needed. Desktop dimensions are unchanged.

If browser storage is blocked, automatic opening is skipped with a console warning, but the button still works. Newly downloaded or refreshed offline quizzes include the shared dialog and script; already saved games need refreshing online to receive the change.

## App artwork and player cards

The app uses the supplied **TT logo (5).png**, unchanged at 768x768, as `app/static/img/two-teamers-app-icon-2026.png` for browser/installed-app icons, iOS Home Screen icons and push notifications. The manifest declares its actual format and dimensions, and offline downloads include it. The previous PNG and SVG artwork have been removed; the updated service worker also removes their offline asset-cache entries on activation. The new filename avoids reusing the old icon URL. Browsers and operating systems may still retain installed-app icons; an existing Home Screen installation may need removing and adding again after deployment. Refresh existing offline downloads online to update their saved icon links.

Kit filenames are assigned in `app/badges.py`. Celtic, AC Milan, Juventus and Rangers use the supplied images copied into `app/static/img/kits/`. Como's kit is pending a supplied image; all other currently available clubs and all featured-fixture clubs have kit assets.

Unanswered player cards show their number at the bottom right with space below the clues, online and offline; the number disappears when the answer is guessed or revealed. Guessed or revealed player cards show the player's name, years at each club and any available nationality (with the existing flag formatting) and position. Apps and goals are no longer displayed on these cards, including offline and admin answer cards. Nationality and Position clues use either club's available record, both individually and through Reveal clues for all, online and in newly downloaded or refreshed offline games. Players with no data for an optional clue on either record do not offer that clue. Position values are displayed as supplied in the spreadsheet; matching values are deduplicated and differing club values are separated by a slash. Position follows the same clue scoring, ad gating, persistence and reset rules as other clues.

The featured workbook is loaded at startup without a fixed date limit. Deploy the updated workbook and reload the app to include added rows. The featured-name aliases accept `Machester United` as Manchester United and `Swansea` as Swansea City.

## Player identity in spreadsheets

The paired club stats tabs use `PlayerId` as the player's identity across all five player workbooks. Keep these IDs as text (including leading zeroes), use the same ID for the same person at every club, and different IDs for different people even if their names are identical.

Columns A–I of stats tabs are read. The existing stats columns remain Player, Years/Yrs, Apps/MP, Min, Goals/Gls and Ast. Optional `Nationality`, `PlayerId`, and `Position(s)` (or `Position`) columns are located by their headers within A–I. The updated Premier League, Championship and League One workbooks supply positions in column I; older workbooks without that header remain supported. Blank, `-`, and `Unverified` position values do not offer a clue. Columns J onward are ignored. Both `ClubStats` and `Club Stats` tab names are supported. The season tabs continue to determine club membership and the 1999-2000 eligibility cutoff; identified stats records must also have eligible years so an older namesake is not included.

The reader uses saved cell values; it does not calculate spreadsheet formulas. If IDs are formulas, recalculate and save the workbook before uploading, or export A–H as values.

Different known IDs never match. A known ID never matches a blank ID. Where **both** club records lack IDs, the previous normalized-name matching remains available; ambiguous duplicates without IDs remain excluded. Complete missing IDs on both sides to recover legitimate answers that cannot currently be linked. Player names remain the answers users type, including either club's display name for an ID match.

After uploading updated spreadsheets to PythonAnywhere, reload the web app. Startup fingerprints each quiz's ordered answer list and automatically clears registered-user and guest progress only for changed quizzes, leaving unchanged quizzes' progress intact. The bundled `app/legacy_quiz_answers.json` contains fingerprints from the committed pre-PlayerId spreadsheets for the first migration; keep it with the deployed app. This reset also clears scores and revealed clues for those changed quizzes.

## Giving up on one answer

Select an unknown player card and choose **Give up on this answer**, alongside the clue options. A confirmation warning appears before revealing the player. The answer stays visible after reloading, is not counted as found, cannot earn points on a later guess, and appears as **❌** in shared results. You can still score for the remaining players; existing clue and reset scoring rules are unchanged. Once every answer has been guessed or revealed, the game finishes and offers result sharing using only the number actually found.

This works online and offline, without watching an ad. The existing **Give up** button still reveals all remaining answers and ends the game. Revealed, unguessed cards have a light-red background and dark-red trim; correctly guessed cards stay lime. Reset clears individually revealed answers too.

## Optional offline play

The **Share** button beside **Play offline?** copies a challenge using the current quiz's two club names and `www.twoteamers.com`. It is available before and after completion, including in newly downloaded or refreshed offline games. A clipboard confirmation appears on success; clipboard failures show an error. It is separate from **Share result**, which retains the existing score-sharing message and completion dialog.

Normal games still check guesses online. To prepare a game for a journey:

1. Open a playable quiz while connected and select **Play offline**.
2. Wait for the download to finish and the saved game to open.
3. Bookmark that saved game's URL. Reopen that exact link in the same browser to resume without Wi-Fi or mobile data; the home page and other games are not downloaded.

The downloaded game checks exact, correct/typo, close and incorrect guesses on the device. Progress survives refreshing or closing the tab. It lasts **eight hours from download, or until the game's existing closing time, whichever is sooner**. Reopening or resetting does not extend the download. Ordinary clues, give-up, reset and result sharing work offline; ad-gated clues require returning to online play. Sharing through another app may itself need a connection.

When switching from an online quiz using **Play offline**, an existing download's page and assets are refreshed to the latest wording/UI after pending progress syncs. Its original expiry, session and progress are retained. A saved link opened without internet must still use the downloaded copy; return online and select **Play offline** to refresh it after a site update.

While a saved game is open, progress and scores sync automatically when connectivity returns. Pending actions also sync on the next online visit to any app page, including after offline access expires. Keep the browser data and reconnect within **seven days of downloading**. The server rechecks the recorded actions using the normal scoring rules; retries cannot award duplicate points. Routine sync succeeds silently. Use **Return to online play** to sync before switching; if syncing fails, a warning appears. If progress has changed on another page/device, the answers have changed, or the account differs, the app reports the conflict and keeps the offline progress locally rather than overwriting server progress. Guest downloads must sync in the same guest browser session; sign in before downloading if account scores are wanted.

Offline play requires HTTPS (localhost is allowed for development), service workers, IndexedDB and browser storage permission. Downloads belong to the browser/profile, not every device using the same account. Private browsing, clearing site data or browser storage eviction can remove them. Answers are downloaded in readable form, so offline play is not suitable for tamper-proof competitions; use caution on shared devices. Expiry prevents further play, but physical cleanup is lazy: stored answer data is pruned on the next app visit, and expired cached pages on the next saved-link visit or download. No background deletion runs while the browser is closed.

For PythonAnywhere, deploy the updated Python, templates and static files together and reload the web app. The database table is created automatically at startup; there are no new dependencies, scheduled tasks or push-notification permissions needed for offline play. Keep a stable, private production `SECRET_KEY` so existing downloads can sync. Ensure `/service-worker.js` is served by Flask at the site root with its existing scope and no-cache headers, rather than a long-lived static mapping. The worker continues to handle daily push notifications independently.

## Browser game notifications

Users can opt in from their profile and manage two independent preferences, both applying to all subscribed devices:

- **Daily Game Notifications**: one reminder for the current featured game.
- **My Team Notifications**: one reminder for each playable regular or featured fixture involving the user's supported team. Neutral users and fixtures with no shared players are skipped. The exact Daily Game fixture is excluded from My Team reminders to prevent duplicates.

Both preferences are enabled when a user first subscribes; the browser permission prompt and the account preferences must both allow delivery. Existing subscribers are migrated with both preferences enabled once. Users can change either preference in their profile without removing device subscriptions.

The Daily Game task runs at **07:31 UK time** and the My Team task at **07:45 UK time**. Each scheduled script accepts sends only during the five-minute window beginning at its scheduled time (`PUSH_SEND_WINDOW_MINUTES`, default `5`). In PythonAnywhere, create two **hourly** tasks: run `send_daily_notifications.py` at minute `31`, and `send_my_team_notifications.py` at minute `45`. The scripts check `Europe/London` time, so they run at the intended UK times across GMT/BST changes without manually changing the task schedule.

Successful and failed attempts are recorded per device and fixture using a SHA-256 hash of the subscription endpoint, not the raw endpoint. Successful sends are not repeated. Known transient push-service responses are retried up to three times; expired subscriptions (HTTP 404/410) are removed. A command-line test push is available below and can target only one account's subscribed devices.

Push notifications require HTTPS and a browser that supports Web Push. On iPhone and iPad, the user must add the site to their Home Screen before enabling notifications; the profile detects when this is required.

If `PUSH_VAPID_PUBLIC_KEY` and `PUSH_VAPID_PRIVATE_KEY_FILE` are both unset, the app generates a P-256 VAPID key pair on startup. It stores the private key beside the configured database as `vapid-private.pem` with owner-only permissions and derives the matching public key. The default `two-teamers/instance/` directory is gitignored. The web app and scheduled scripts must use the same database path so they share this key. Back up the private key securely; replacing or losing it invalidates existing browser subscriptions.

For deployments that manage VAPID keys explicitly, set these values for both the web app and scheduled tasks:

- `PUSH_VAPID_PUBLIC_KEY`: URL-safe base64 public key.
- `PUSH_VAPID_PRIVATE_KEY_FILE`: path to the PEM private key, readable only by the app account.
- `PUSH_VAPID_SUBJECT`: contact URI for the application, such as `mailto:twoteamerssupport@gmail.com`.

The sender uses cryptography's standard PEM parser and passes the parsed P-256 key directly to VAPID, supporting both PKCS8 and traditional EC PEM files, including surrounding blank lines. Keep the existing private key when deploying sender fixes; regenerating it would invalidate existing subscriptions. Push-service acceptance does not confirm that a device displayed the notification.

Generate a VAPID key pair in the project's virtual environment with:

```bash
python - <<'PY'
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

key = ec.generate_private_key(ec.SECP256R1())
private = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
public = key.public_key().public_bytes(
    serialization.Encoding.X962,
    serialization.PublicFormat.UncompressedPoint,
)
print("Private key (save as a PEM file outside the repository):")
print(private.decode())
print("Public key (set as PUSH_VAPID_PUBLIC_KEY):")
print(base64.urlsafe_b64encode(public).rstrip(b"=").decode())
PY
```

Install dependencies in the PythonAnywhere virtualenv with `pip install -r requirements.txt`, then reload the web app. Add both hourly tasks in PythonAnywhere's **Tasks** page. Run each with the project's virtualenv Python from the `two-teamers` directory; scheduled tasks do not inherit the web app's WSGI environment, so set the same database and fixture paths in each task command. If using an explicitly configured VAPID pair, also pass the same three VAPID values to both tasks. With the app-generated key, no VAPID environment variables are needed as long as the tasks use the same deployment directory. Replace the example paths with the actual deployment paths before use:

```bash
cd /home/jamieclarke323/TwoTeamers/two-teamers && \
DATABASE_PATH=/home/jamieclarke323/TwoTeamers/two-teamers/instance/two-teamers.sqlite \
FIXTURES_DIR=/home/jamieclarke323/TwoTeamers \
/home/USERNAME/.virtualenvs/ENVIRONMENT/bin/python send_daily_notifications.py
```

Use the same command for the second task, replacing `send_daily_notifications.py` with `send_my_team_notifications.py`. For explicitly configured keys, add `PUSH_VAPID_PUBLIC_KEY`, `PUSH_VAPID_PRIVATE_KEY_FILE`, and `PUSH_VAPID_SUBJECT` to both commands. PythonAnywhere's task trigger is hourly at the selected minute; the application sends only in the matching UK-time window.

Before deploying, make a consistent SQLite backup outside the repository, using the actual database and backup paths:

```bash
sqlite3 /path/to/instance/two-teamers.sqlite \
  ".backup '/path/to/private-backups/two-teamers-before-push.sqlite'"
```

The SQLite backup does not include the VAPID key file. Back up the app-generated `<database directory>/vapid-private.pem` separately to a private location (by default, `two-teamers/instance/vapid-private.pem`); if using an explicitly configured key, back up that file instead. Preserve the same key across deployments. The preference and delivery tables are created by an additive startup migration; existing subscriptions and gameplay data are retained. For a code-only rollback, disable the two scheduled tasks, redeploy the previous app code and reload the web app; the added tables and columns can remain. If the database itself must be restored, first stop scheduled tasks and app writes, then restore the backup and reload:

```bash
sqlite3 /path/to/instance/two-teamers.sqlite \
  ".restore '/path/to/private-backups/two-teamers-before-push.sqlite'"
```

To send a real test, use an account that has enabled push on a device. This CLI-only command requires an explicit confirmation flag and sends only to that account's subscribed devices; there is no public test endpoint:

```bash
cd /path/to/TwoTeamers/two-teamers
DATABASE_PATH=/path/to/instance/two-teamers.sqlite \
FIXTURES_DIR=/path/to/TwoTeamers \
/path/to/virtualenv/bin/python send_test_push.py \
  --email test-account@example.com --confirm-send
```

If using explicitly configured keys, add the same three VAPID environment variables to the test command. The test command confirms server-side delivery acceptance only. Verify notifications on a real subscribed browser/device after deployment, including a Home Screen-installed iPhone or iPad if those devices are in use; local tests do not verify production credentials, task configuration, or device delivery.
