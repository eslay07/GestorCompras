"""Tests para el módulo email_task_scanner."""
import email
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from gestorcompras.services.email_task_scanner import (
    clean_html,
    decode_header_value,
    extract_text,
    normalize_for_search,
    parse_header_date,
    raw_hash,
    scan_inbox,
)

TZ = ZoneInfo("America/Guayaquil")


def test_decode_header_value_plain():
    assert decode_header_value("Hello world") == "Hello world"


def test_clean_html_strips_tags():
    assert "Hello" in clean_html("<p>Hello</p>")


def test_normalize_for_search_removes_accents():
    assert normalize_for_search("café") == "CAFE"
    assert normalize_for_search(None) == ""
    assert normalize_for_search("") == ""


def test_raw_hash_deterministic():
    data = b"test data"
    h1 = raw_hash(data)
    h2 = raw_hash(data)
    assert h1 == h2
    assert len(h1) == 64


def test_extract_text_plain():
    msg = email.message_from_string("Subject: Test\n\nBody text here")
    assert "Body text here" in extract_text(msg)


def test_parse_header_date_valid():
    msg = email.message_from_string("Date: Thu, 01 Jan 2025 12:00:00 +0000\n\nBody")
    dt = parse_header_date(msg, TZ)
    assert dt is not None
    assert dt.year == 2025


def test_parse_header_date_missing():
    msg = email.message_from_string("Subject: No date\n\nBody")
    assert parse_header_date(msg) is None


def _make_raw_email(subject: str, body: str, date_str: str, from_addr: str = "test@example.com") -> bytes:
    return (
        f"From: {from_addr}\r\n"
        f"Subject: {subject}\r\n"
        f"Date: {date_str}\r\n"
        f"To: dest@telconet.ec\r\n"
        f"\r\n"
        f"{body}"
    ).encode("utf-8")


@patch("gestorcompras.services.email_task_scanner.imaplib.IMAP4_SSL")
def test_scan_inbox_filters_by_task_number(mock_imap_cls):
    ahora = datetime.now(TZ)
    hace_1h = ahora - timedelta(hours=1)
    date_str = ahora.strftime("%a, %d %b %Y %H:%M:%S %z")

    raw1 = _make_raw_email(
        'TAREA: "123456" - Notificacion',
        "Estimados MAVESA\nFACTURA: FAC-001 OC: 55555\nRUC: 1790016919001\nuser@telconet.ec",
        date_str,
    )
    raw2 = _make_raw_email(
        'TAREA: "999999" - Otra',
        "Otro correo sin datos relevantes",
        date_str,
    )

    mock_conn = MagicMock()
    mock_imap_cls.return_value = mock_conn
    mock_conn.login.return_value = ("OK", [])
    mock_conn.select.return_value = ("OK", [])
    mock_conn.search.return_value = ("OK", [b"1 2"])
    mock_conn.fetch.side_effect = [
        ("OK", [(b"2", raw2)]),
        ("OK", [(b"1", raw1)]),
    ]

    results = scan_inbox(
        {"address": "user@telconet.ec", "password": "pass"},
        hace_1h, ahora,
        task_numbers=["123456"],
    )
    assert len(results) == 1
    assert results[0]["task_number"] == "123456"
    assert results[0]["factura"] == "FAC-001"
    assert results[0]["oc"] == "55555"
    assert results[0]["ruc"] == "1790016919001"


@patch("gestorcompras.services.email_task_scanner.imaplib.IMAP4_SSL")
def test_scan_inbox_returns_all_without_filter(mock_imap_cls):
    ahora = datetime.now(TZ)
    hace_1h = ahora - timedelta(hours=1)
    date_str = ahora.strftime("%a, %d %b %Y %H:%M:%S %z")

    raw1 = _make_raw_email('TAREA: "111111"', "Body1", date_str)

    mock_conn = MagicMock()
    mock_imap_cls.return_value = mock_conn
    mock_conn.login.return_value = ("OK", [])
    mock_conn.select.return_value = ("OK", [])
    mock_conn.search.return_value = ("OK", [b"1"])
    mock_conn.fetch.return_value = ("OK", [(b"1", raw1)])

    results = scan_inbox(
        {"address": "user@telconet.ec", "password": "pass"},
        hace_1h, ahora,
    )
    assert len(results) == 1
    assert results[0]["task_number"] == "111111"


def test_scan_inbox_raises_on_missing_credentials():
    with pytest.raises(ValueError, match="incompletas"):
        scan_inbox({}, datetime.now(TZ), datetime.now(TZ))
