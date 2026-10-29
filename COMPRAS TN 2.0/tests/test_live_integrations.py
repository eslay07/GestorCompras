from __future__ import annotations

import os

import pytest

from compras_tn.bootstrap import build_container

pytestmark = pytest.mark.live


@pytest.fixture
def live_services():  # type: ignore[no-untyped-def]
    if os.environ.get("COMPRAS_TN_LIVE") != "1":
        pytest.skip("Prueba manual: establezca COMPRAS_TN_LIVE=1 y credenciales de sesión.")
    username = os.environ.get("COMPRAS_TN_USER", "")
    password = os.environ.get("COMPRAS_TN_PASSWORD", "")
    if not username or not password:
        pytest.skip("Faltan COMPRAS_TN_USER y COMPRAS_TN_PASSWORD.")
    container = build_container()
    container.services.login(username, password)
    yield container.services
    container.services.logout()
    container.database.close()


def test_live_smtp_imap_pop(live_services) -> None:  # type: ignore[no-untyped-def]
    assert "verificadas" in live_services.test_mail_connection()


def test_live_google_sheets(live_services) -> None:  # type: ignore[no-untyped-def]
    assert "verificada" in live_services.test_google_connection()


def test_live_seafile(live_services) -> None:  # type: ignore[no-untyped-def]
    assert "verificada" in live_services.test_seafile_connection()


def test_live_telcos(live_services) -> None:  # type: ignore[no-untyped-def]
    assert "verificada" in live_services.test_telcos_connection()
