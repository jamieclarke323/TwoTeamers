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
