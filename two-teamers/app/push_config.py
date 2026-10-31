from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

from flask import Flask


def configure_vapid(app: Flask) -> None:
    app.config["PUSH_VAPID_CONFIG_ERROR"] = ""
    if app.testing:
        return

    public_key = app.config["PUSH_VAPID_PUBLIC_KEY"].strip()
    configured_key_file = app.config["PUSH_VAPID_PRIVATE_KEY_FILE"].strip()
    if public_key and not configured_key_file:
        _set_error(
            app,
            "Set PUSH_VAPID_PRIVATE_KEY_FILE to the private key matching the public key.",
        )
        return

    private_key_file = (
        Path(configured_key_file)
        if configured_key_file
        else Path(app.config["DATABASE"]).parent / "vapid-private.pem"
    )
    if public_key and not private_key_file.is_file():
        _set_error(app, "The configured VAPID private key file is missing.")
        return

    try:
        derived_public_key = _load_or_create_key(private_key_file)
    except ImportError:
        _set_error(
            app,
            "The cryptography package is required to configure push notifications.",
        )
        return
    except (OSError, TypeError, ValueError):
        app.logger.exception("Unable to configure the VAPID key pair.")
        _set_error(app, "The VAPID private key file could not be read or is invalid.")
        return

    if public_key and public_key.rstrip("=") != derived_public_key:
        _set_error(app, "The configured VAPID public and private keys do not match.")
        return

    app.config["PUSH_VAPID_PUBLIC_KEY"] = public_key or derived_public_key
    app.config["PUSH_VAPID_PRIVATE_KEY_FILE"] = str(private_key_file)


def _load_or_create_key(private_key_file: Path) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    if private_key_file.is_file():
        private_key_pem = private_key_file.read_bytes()
    elif private_key_file.exists():
        raise ValueError("The VAPID private key path is not a file.")
    else:
        private_key_file.parent.mkdir(parents=True, exist_ok=True)
        key = ec.generate_private_key(ec.SECP256R1())
        private_key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        _write_key_if_missing(private_key_file, private_key_pem)
        private_key_pem = private_key_file.read_bytes()

    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(
        private_key.curve, ec.SECP256R1
    ):
        raise ValueError("The VAPID private key must use the P-256 curve.")

    public_key_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(public_key_bytes).rstrip(b"=").decode("ascii")


def _write_key_if_missing(private_key_file: Path, private_key_pem: bytes) -> None:
    file_descriptor, temporary_file = tempfile.mkstemp(
        prefix=".vapid-", dir=private_key_file.parent
    )
    try:
        with os.fdopen(file_descriptor, "wb") as key_file:
            key_file.write(private_key_pem)
            key_file.flush()
            os.fsync(key_file.fileno())
        try:
            os.link(temporary_file, private_key_file)
        except FileExistsError:
            pass
    finally:
        try:
            os.unlink(temporary_file)
        except FileNotFoundError:
            pass


def _set_error(app: Flask, message: str) -> None:
    app.config["PUSH_VAPID_CONFIG_ERROR"] = message
    app.logger.error("Push notifications are unavailable: %s", message)
