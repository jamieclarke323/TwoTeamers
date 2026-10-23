# Two Teamers

A Flask quiz covering players who represented both clubs in a fixture. The current release supports every 2026/27 Premier League fixture and discovers all 92 clubs for the team selector.

## Run locally

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

Open `http://127.0.0.1:5000`. Set `BYPASS_AVAILABILITY=1` to test every fixture outside its live 30-day window.

Production should set `SECRET_KEY`, `SESSION_COOKIE_SECURE=1`, and persistent `DATABASE_PATH`, `FIXTURES_DIR`, and `PLAYERS_XLSX_PATH` values.

## Player identity in spreadsheets

The paired club stats tabs use `PlayerId` as the player's identity across all five player workbooks. Keep these IDs as text (including leading zeroes), use the same ID for the same person at every club, and different IDs for different people even if their names are identical.

Only columns A–H of stats tabs are read. The existing stats columns remain Player, Years/Yrs, Apps/MP, Min, Goals/Gls and Ast. Optional `Nationality` and `PlayerId` columns are located by their headers within A–H: for example, PlayerId can be in column H after Nationality or column G when Nationality is absent. Columns I onward are ignored, including duplicate headers. Both `ClubStats` and `Club Stats` tab names are supported. The season tabs continue to determine club membership and the 1999-2000 eligibility cutoff; identified stats records must also have eligible years so an older namesake is not included.

The reader uses saved cell values; it does not calculate spreadsheet formulas. If IDs are formulas, recalculate and save the workbook before uploading, or export A–H as values.

Different known IDs never match. A known ID never matches a blank ID. Where **both** club records lack IDs, the previous normalized-name matching remains available; ambiguous duplicates without IDs remain excluded. Complete missing IDs on both sides to recover legitimate answers that cannot currently be linked. Player names remain the answers users type, including either club's display name for an ID match.

After uploading updated spreadsheets to PythonAnywhere, reload the web app. Startup fingerprints each quiz's ordered answer list and automatically clears registered-user and guest progress only for changed quizzes, leaving unchanged quizzes' progress intact. The bundled `app/legacy_quiz_answers.json` contains fingerprints from the committed pre-PlayerId spreadsheets for the first migration; keep it with the deployed app. This reset also clears scores and revealed clues for those changed quizzes.

## Giving up on one answer

Select an unknown player card and choose **Give up on this answer**, alongside the clue options. A confirmation warning appears before revealing the player. The answer stays visible after reloading, is not counted as found, cannot earn points on a later guess, and appears as **❌** in shared results. You can still score for the remaining players; existing clue and reset scoring rules are unchanged. Once every answer has been guessed or revealed, the game finishes and offers result sharing using only the number actually found.

This works online and offline, without watching an ad. The existing **Give up** button still reveals all remaining answers and ends the game. Revealed, unguessed cards have a light-red background and dark-red trim; correctly guessed cards stay lime. Reset clears individually revealed answers too.

## Optional offline play

Normal games still check guesses online. To prepare a game for a journey:

1. Open a playable quiz while connected and select **Play offline**.
2. Wait for the download to finish and the saved game to open.
3. Bookmark that saved game's URL. Reopen that exact link in the same browser to resume without Wi-Fi or mobile data; the home page and other games are not downloaded.

The downloaded game checks exact, correct/typo, close and incorrect guesses on the device. Progress survives refreshing or closing the tab. It lasts **eight hours from download, or until the game's existing closing time, whichever is sooner**. Reopening or resetting does not extend the download. Ordinary clues, give-up, reset and result sharing work offline; ad-gated clues require returning to online play. Sharing through another app may itself need a connection.

When switching from an online quiz using **Play offline**, an existing download's page and assets are refreshed to the latest wording/UI after pending progress syncs. Its original expiry, session and progress are retained. A saved link opened without internet must still use the downloaded copy; return online and select **Play offline** to refresh it after a site update.

While a saved game is open, progress and scores sync automatically when connectivity returns. Pending actions also sync on the next online visit to any app page, including after offline access expires. Keep the browser data and reconnect within **seven days of downloading**. The server rechecks the recorded actions using the normal scoring rules; retries cannot award duplicate points. Wait for the synced message before switching to online play. If progress has changed on another page/device, the answers have changed, or the account differs, the app reports the conflict and keeps the offline progress locally rather than overwriting server progress. Guest downloads must sync in the same guest browser session; sign in before downloading if account scores are wanted.

Offline play requires HTTPS (localhost is allowed for development), service workers, IndexedDB and browser storage permission. Downloads belong to the browser/profile, not every device using the same account. Private browsing, clearing site data or browser storage eviction can remove them. Answers are downloaded in readable form, so offline play is not suitable for tamper-proof competitions; use caution on shared devices. Expiry prevents further play, but physical cleanup is lazy: stored answer data is pruned on the next app visit, and expired cached pages on the next saved-link visit or download. No background deletion runs while the browser is closed.

For PythonAnywhere, deploy the updated Python, templates and static files together and reload the web app. The database table is created automatically at startup; there are no new dependencies, scheduled tasks or push-notification permissions needed for offline play. Keep a stable, private production `SECRET_KEY` so existing downloads can sync. Ensure `/service-worker.js` is served by Flask at the site root with its existing scope and no-cache headers, rather than a long-lived static mapping. The worker continues to handle daily push notifications independently.

## Browser game notifications

Users can opt in from their profile. At 7:30am UK time, the daily task sends a browser push only when that user's supported team has a playable fixture dated that UK day. Users set to Neutral, fixtures with no shared players, and fixtures that are not playable are skipped. Clicking the notification opens that fixture.

Push notifications require HTTPS and a browser that supports Web Push. On iPhone and iPad, the user must add the site to their Home Screen before enabling notifications. Generate one VAPID key pair and keep the private key outside the repository. Configure these values for both the web app and the scheduled task:

- `PUSH_VAPID_PUBLIC_KEY`: URL-safe base64 public key.
- `PUSH_VAPID_PRIVATE_KEY_FILE`: path to the PEM private key, readable only by the app account.
- `PUSH_VAPID_SUBJECT`: contact URI for the application, such as `mailto:twoteamerssupport@gmail.com`.

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

Install dependencies in the PythonAnywhere virtualenv with `pip install -r requirements.txt`, configure the three environment variables in the web app's WSGI configuration, and reload the web app. In PythonAnywhere's **Tasks** page, create a daily scheduled task to run the script with the same database, fixture, and VAPID values. Run it with the project's virtualenv Python from the `two-teamers` directory; set the environment values in the task command as well, since the scheduled task does not inherit the web app's WSGI process environment:

```bash
cd /home/USERNAME/TwoTeamers/two-teamers && \
DATABASE_PATH=/home/USERNAME/TwoTeamers/two-teamers/instance/two-teamers.sqlite \
FIXTURES_DIR=/home/USERNAME/TwoTeamers \
PUSH_VAPID_PUBLIC_KEY='YOUR_PUBLIC_KEY' \
PUSH_VAPID_PRIVATE_KEY_FILE=/home/USERNAME/.secrets/twoteamers-vapid.pem \
PUSH_VAPID_SUBJECT=mailto:twoteamerssupport@gmail.com \
/home/USERNAME/.virtualenvs/ENVIRONMENT/bin/python send_daily_notifications.py
```

PythonAnywhere scheduled task times use UTC. To deliver at 7:30am UK time, schedule the task for 07:30 UTC during GMT and 06:30 UTC during BST, updating the task when the UK clocks change. Test the command manually before relying on the schedule.
