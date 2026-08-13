from __future__ import annotations

import keyring

SERVICE = "ProductIntelligence"


def save_value(name: str, value: str) -> None:
    if not value:
        delete_value(name)
        return
    keyring.set_password(SERVICE, name, value)


def load_value(name: str) -> str | None:
    return keyring.get_password(SERVICE, name)


def delete_value(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass
