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
