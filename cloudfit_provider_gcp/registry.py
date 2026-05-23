"""Write normalized MachineType instances to the cloudfit registry store (PostgreSQL).

Schema
------
    machine_types (
        id              TEXT,
        provider        TEXT,
        region          TEXT,
        vcpu            INTEGER,
        ram_gb          REAL,
        price_hr        REAL,
        local_ssd_tb    REAL,
        gpu_count       INTEGER,
        gpu_vram_gb     INTEGER,
        status          TEXT,
        generation      TEXT,
        fetched_at      TIMESTAMP,
        PRIMARY KEY (id, provider, region)
    )

The registry uses upsert (INSERT ... ON CONFLICT DO UPDATE) so re-running
the fetcher is always safe — it updates existing rows rather than duplicating.
Tombstoned instances are never deleted; they stay in the registry with
status='tombstoned' so existing configs can warn rather than break silently.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cloudfit.models import MachineType

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS machine_types (
    id           TEXT        NOT NULL,
    provider     TEXT        NOT NULL,
    region       TEXT        NOT NULL,
    vcpu         INTEGER     NOT NULL,
    ram_gb       REAL        NOT NULL,
    price_hr     REAL        NOT NULL DEFAULT 0.0,
    local_ssd_tb REAL        NOT NULL DEFAULT 0.0,
    gpu_count    INTEGER     NOT NULL DEFAULT 0,
    gpu_vram_gb  INTEGER,
    status       TEXT        NOT NULL DEFAULT 'active',
    generation   TEXT,
    fetched_at   TIMESTAMP   NOT NULL,
    PRIMARY KEY (id, provider, region)
);
"""

_UPSERT_SQL = """
INSERT INTO machine_types
    (id, provider, region, vcpu, ram_gb, price_hr, local_ssd_tb,
     gpu_count, gpu_vram_gb, status, generation, fetched_at)
VALUES
    (%(id)s, %(provider)s, %(region)s, %(vcpu)s, %(ram_gb)s,
     %(price_hr)s, %(local_ssd_tb)s, %(gpu_count)s, %(gpu_vram_gb)s,
     %(status)s, %(generation)s, %(fetched_at)s)
ON CONFLICT (id, provider, region) DO UPDATE SET
    vcpu         = EXCLUDED.vcpu,
    ram_gb       = EXCLUDED.ram_gb,
    price_hr     = EXCLUDED.price_hr,
    local_ssd_tb = EXCLUDED.local_ssd_tb,
    gpu_count    = EXCLUDED.gpu_count,
    gpu_vram_gb  = EXCLUDED.gpu_vram_gb,
    status       = EXCLUDED.status,
    generation   = EXCLUDED.generation,
    fetched_at   = EXCLUDED.fetched_at;
"""


def write_to_registry(
    instances: list["MachineType"],
    database_url: str,
    batch_size: int = 500,
) -> int:
    """Write or update machine types in the cloudfit registry (PostgreSQL).

    Args:
        instances:    List of normalized MachineType objects to persist.
        database_url: PostgreSQL connection string.
                      e.g. "postgresql://user:pass@host:5432/cloudfit"
        batch_size:   Number of rows to upsert per transaction.

    Returns:
        Number of rows written.

    Raises:
        ImportError:  If psycopg2 is not installed.
        RuntimeError: If the database connection or write fails.
    """
    try:
        import psycopg2
    except ImportError as exc:
        raise ImportError(
            "psycopg2-binary is required for registry writes. "
            "Install with: pip install 'cloudfit-provider-gcp[registry]'"
        ) from exc

    fetched_at = datetime.now(timezone.utc)
    rows = [_to_row(mt, fetched_at) for mt in instances]

    try:
        conn = psycopg2.connect(database_url)
        cur  = conn.cursor()
        cur.execute(_CREATE_TABLE_SQL)

        written = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            cur.executemany(_UPSERT_SQL, batch)
            written += len(batch)
            logger.debug("Upserted batch %d/%d", i + batch_size, len(rows))

        conn.commit()
        cur.close()
        conn.close()

        logger.info("Wrote %d machine types to registry", written)
        return written

    except Exception as exc:
        raise RuntimeError(f"Registry write failed: {exc}") from exc


def _to_row(mt: "MachineType", fetched_at: datetime) -> dict:
    """Convert a MachineType to a registry row dict."""
    return {
        "id":           mt.id,
        "provider":     mt.provider,
        "region":       mt.region,
        "vcpu":         mt.vcpu,
        "ram_gb":       mt.ram_gb,
        "price_hr":     mt.price_hr,
        "local_ssd_tb": mt.local_ssd_tb,
        "gpu_count":    mt.gpu_count,
        "gpu_vram_gb":  mt.gpu_vram_gb,
        "status":       mt.status,
        "generation":   mt.generation,
        "fetched_at":   fetched_at,
    }
