"""Tests for cloudfit_provider_gcp.registry — uses a mock psycopg2, no real DB."""

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from cloudfit.models import MachineType
from cloudfit_provider_gcp.registry import write_to_registry, _to_row, _UPSERT_SQL


def _machines() -> list[MachineType]:
    return [
        MachineType(id="n2-standard-32", provider="gcp", region="us-central1",
                    vcpu=32, ram_gb=128.0, price_hr=1.2, gpu_vram_gb=None),
        MachineType(id="a2-highgpu-1g", provider="gcp", region="us-central1",
                    vcpu=12, ram_gb=85.0, price_hr=3.67, gpu_count=1, gpu_vram_gb=40),
    ]


def _install_mock_psycopg2(monkeypatch):
    fake = MagicMock()
    conn = MagicMock()
    cur = MagicMock()
    fake.connect.return_value = conn
    conn.cursor.return_value = cur
    monkeypatch.setitem(sys.modules, "psycopg2", fake)
    return fake, conn, cur


def test_write_to_registry_calls_executemany_with_sql_and_rows(monkeypatch):
    _fake, conn, cur = _install_mock_psycopg2(monkeypatch)

    written = write_to_registry(_machines(), "postgresql://u:p@h/db", batch_size=500)

    assert written == 2
    cur.executemany.assert_called_once()
    sql, rows = cur.executemany.call_args[0]
    assert sql == _UPSERT_SQL
    assert len(rows) == 2
    conn.commit.assert_called_once()


def test_write_to_registry_batches(monkeypatch):
    _fake, _conn, cur = _install_mock_psycopg2(monkeypatch)

    written = write_to_registry(_machines(), "postgresql://u:p@h/db", batch_size=1)

    assert written == 2
    assert cur.executemany.call_count == 2


def test_to_row_passes_none_gpu_vram():
    mt = MachineType(id="n2-standard-32", provider="gcp", region="us-central1",
                     vcpu=32, ram_gb=128.0, price_hr=1.2, gpu_vram_gb=None)
    row = _to_row(mt, datetime.now(timezone.utc))
    assert row["gpu_vram_gb"] is None   # psycopg2 binds None -> SQL NULL
    assert row["id"] == "n2-standard-32"


def test_missing_psycopg2_raises_importerror(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg2", None)
    with pytest.raises(ImportError, match="psycopg2"):
        write_to_registry(_machines(), "postgresql://u:p@h/db")
