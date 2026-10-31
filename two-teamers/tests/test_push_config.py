from pathlib import Path
import stat

from flask import Flask

from app import create_app
from app.push_config import configure_vapid


def _app(instance_path: Path) -> Flask:
    app = Flask("push-config-test", instance_path=str(instance_path))
    app.config.update(
        DATABASE=str(instance_path / "test.sqlite"),
        PUSH_VAPID_PUBLIC_KEY="",
        PUSH_VAPID_PRIVATE_KEY_FILE="",
        PUSH_VAPID_CONFIG_ERROR="",
    )
    return app


def test_vapid_key_is_generated_once_and_reused_with_private_permissions(tmp_path):
    instance_path = tmp_path / "instance"
    app = _app(instance_path)
    configure_vapid(app)

    private_key_file = Path(app.config["PUSH_VAPID_PRIVATE_KEY_FILE"])
    public_key = app.config["PUSH_VAPID_PUBLIC_KEY"]
    assert private_key_file == instance_path / "vapid-private.pem"
    assert private_key_file.is_file()
    assert stat.S_IMODE(private_key_file.stat().st_mode) == 0o600
    assert public_key
    assert not app.config["PUSH_VAPID_CONFIG_ERROR"]

    second_app = _app(instance_path)
    configure_vapid(second_app)
    assert second_app.config["PUSH_VAPID_PUBLIC_KEY"] == public_key
    assert Path(second_app.config["PUSH_VAPID_PRIVATE_KEY_FILE"]).read_bytes() == (
        private_key_file.read_bytes()
    )


def test_vapid_configuration_rejects_mismatched_keys(tmp_path):
    instance_path = tmp_path / "instance"
    initial_app = _app(instance_path)
    configure_vapid(initial_app)

    app = _app(instance_path)
    app.config.update(
        PUSH_VAPID_PUBLIC_KEY="not-the-matching-public-key",
        PUSH_VAPID_PRIVATE_KEY_FILE=initial_app.config["PUSH_VAPID_PRIVATE_KEY_FILE"],
    )
    configure_vapid(app)

    assert "do not match" in app.config["PUSH_VAPID_CONFIG_ERROR"]


def test_app_startup_enables_push_with_persisted_generated_keys(tmp_path, monkeypatch):
    monkeypatch.setattr("app.load_game_data", lambda *args: ([], [], [], {}))
    database = tmp_path / "instance" / "two-teamers.sqlite"
    app = create_app(
        {
            "DATABASE": str(database),
            "DATA_DIR": str(tmp_path),
            "XLSX_PATH": str(tmp_path / "players.xlsx"),
            "PUSH_VAPID_PUBLIC_KEY": "",
            "PUSH_VAPID_PRIVATE_KEY_FILE": "",
            "SECRET_KEY": "test",
        }
    )

    assert Path(app.config["PUSH_VAPID_PRIVATE_KEY_FILE"]) == (
        database.parent / "vapid-private.pem"
    )
    client = app.test_client()
    assert client.post(
        "/signup",
        data={
            "email": "fan@example.com",
            "password": "football123",
            "supported_team": "Neutral",
        },
    ).status_code == 302
    profile = client.get("/profile").get_data(as_text=True)
    button = profile.split('id="push-toggle"', 1)[1].split("</button>", 1)[0]
    assert 'data-push-configured="true"' in button
    assert "disabled" not in button

    with client.session_transaction() as browser_session:
        csrf_token = browser_session["push_csrf_token"]
    response = client.post(
        "/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-token",
            "keys": {"p256dh": "public", "auth": "secret"},
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200
