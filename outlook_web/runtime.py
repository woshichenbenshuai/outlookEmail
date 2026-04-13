#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime helpers for local execution and packaged builds."""

from __future__ import annotations

import os
import secrets
import sys
import traceback
from pathlib import Path


APP_NAME = "OutlookEmail"
SECRET_KEY_FILE = "secret_key.txt"
DATABASE_FILE = "outlook_accounts.db"
STARTUP_LOG_FILE = "startup-error.log"
WEAK_SECRET_KEYS = {
    "your-secret-key-here",
    "secret",
    "password",
    "admin",
    "admin123",
    "123456",
    "12345678",
}


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def runtime_root() -> Path:
    override = os.getenv("OUTLOOK_EMAIL_HOME")
    if override:
        root = Path(override).expanduser()
    elif is_frozen():
        if os.name == "nt":
            root = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / APP_NAME
        elif sys.platform == "darwin":
            root = Path.home() / "Library" / "Application Support" / APP_NAME
        else:
            xdg_home = os.getenv("XDG_DATA_HOME")
            root = Path(xdg_home).expanduser() / APP_NAME if xdg_home else Path.home() / ".local" / "share" / APP_NAME
    else:
        root = bundle_root()

    root.mkdir(parents=True, exist_ok=True)
    return root


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def default_database_path() -> Path:
    if is_frozen():
        return runtime_root() / "data" / DATABASE_FILE
    return bundle_root() / "data" / DATABASE_FILE


def startup_log_path() -> Path:
    return runtime_root() / STARTUP_LOG_FILE


def _is_weak_secret_key(value: str) -> bool:
    key = (value or "").strip()
    if len(key) < 32:
        return True
    return key.lower() in WEAK_SECRET_KEYS


def _resolve_secret_key_path() -> Path:
    configured = (os.getenv("SECRET_KEY_FILE") or "").strip()
    if configured:
        path = Path(configured).expanduser()
    elif is_frozen():
        path = runtime_root() / SECRET_KEY_FILE
    else:
        path = bundle_root() / "data" / "secret_key"

    if not path.is_absolute():
        base_root = runtime_root() if is_frozen() else bundle_root()
        path = base_root / path
    return path


def resolve_secret_key() -> str:
    secret_key = (os.getenv("SECRET_KEY") or "").strip()
    if secret_key:
        if _is_weak_secret_key(secret_key):
            raise RuntimeError("SECRET_KEY is too weak; use at least 32 random characters")
        return secret_key

    secret_key_path = _resolve_secret_key_path()
    if secret_key_path.exists():
        stored = secret_key_path.read_text(encoding="utf-8").strip()
        if not stored:
            raise RuntimeError(f"SECRET_KEY_FILE is empty: {secret_key_path}")
        if _is_weak_secret_key(stored):
            raise RuntimeError(f"SECRET_KEY in file is too weak: {secret_key_path}")
        return stored

    secret_key_path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_hex(32)
    secret_key_path.write_text(generated, encoding="utf-8")
    try:
        os.chmod(secret_key_path, 0o600)
    except Exception:
        pass
    return generated


def record_startup_error(exc: BaseException) -> Path:
    log_path = startup_log_path()
    error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_path.write_text(error_text, encoding="utf-8")
    return log_path


def notify_startup_error(log_path: Path) -> None:
    message = (
        "OutlookEmail 启动失败。\n\n"
        f"错误日志已写入:\n{log_path}\n\n"
        "请把这个日志发给开发者。"
    )

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "OutlookEmail", 0x10)
            return
        except Exception:
            pass

    print(message, file=sys.stderr)
