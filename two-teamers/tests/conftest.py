import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT))

from app import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.sqlite"),
        "DATA_DIR": str(ROOT),
        "XLSX_PATH": str(ROOT / "2627DataSource.xlsx"),
        "BYPASS_AVAILABILITY": True,
        "SECRET_KEY": "test",
    })


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def signed_in_client(client):
    client.post(
        "/signup",
        data={
            "email": "fan@example.com",
            "password": "football123",
            "supported_team": "Neutral",
        },
    )
    return client
