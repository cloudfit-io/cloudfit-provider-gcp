"""Refresh prices in existing bundled snapshots from a live GCP Billing fetch.

This is the scheduled-refresh entry point. Pricing is what drifts over time
(weeks to months), not the machine-type set, so this updates on-demand, spot,
and 1-year committed-use prices on already-curated snapshot files *in place*
without changing their curation (row set, regions, statuses). It is idempotent.

- Non-GPU instances: price_hr is refreshed and spot_price_hr / cud_1yr_price_hr
  are added from the live catalog.
- GPU instances: price_hr is left untouched (GPU cost is not reconstructed; see
  pricing.py) and they get no spot/CUD.
- perf_factor and gpu_type are (re)applied so the files stay complete.

Only the regions present in the snapshots are fetched. No project is needed: the
Billing catalog is global. Requires `gcloud auth application-default login`.

Run
---
    python examples/refresh_prices.py path/to/gcp_snapshot.json [more.json ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from cloudfit.models import MachineType
from cloudfit.scorer import perf_factor_for

from cloudfit_provider_gcp.pricing import PricingClient, RegionPrices, reconstruct_price


def _gpu_type_for(row: dict[str, Any]) -> str | None:
    """Derive the accelerator name from family + VRAM for a snapshot row."""
    family = str(row["id"]).split("-")[0]
    if family == "a2":
        return "nvidia-a100-80gb" if row.get("gpu_vram_gb") == 80 else "nvidia-tesla-a100"
    if family == "a3":
        return "nvidia-h100-80gb"
    if family == "g2":
        return "nvidia-l4"
    return None


def _refresh_row(row: dict[str, Any], maps: dict[str, RegionPrices]) -> dict[str, Any]:
    row["perf_factor"] = perf_factor_for(row["id"])
    if row.get("gpu_count", 0) > 0:
        gpu_type = _gpu_type_for(row)
        if gpu_type:
            row["gpu_type"] = gpu_type
        return MachineType(**row).model_dump(exclude_none=True)

    prices = maps.get(row["region"])
    if prices is not None:
        mid, vcpu, ram = row["id"], row["vcpu"], row["ram_gb"]
        on_demand = reconstruct_price(mid, vcpu, ram, *prices.on_demand)
        spot = reconstruct_price(mid, vcpu, ram, *prices.spot)
        cud = reconstruct_price(mid, vcpu, ram, *prices.cud_1yr)
        if on_demand > 0:
            row["price_hr"] = on_demand
        if spot > 0:
            row["spot_price_hr"] = spot
        if cud > 0:
            row["cud_1yr_price_hr"] = cud
    return MachineType(**row).model_dump(exclude_none=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh snapshot prices from the Billing catalog.")
    parser.add_argument("snapshots", nargs="+", help="Snapshot JSON file(s) to update in place.")
    args = parser.parse_args()

    data = {path: json.load(open(path)) for path in args.snapshots}
    regions = sorted({row["region"] for rows in data.values() for row in rows})

    client = PricingClient()
    print(f"Fetching pricing for {len(regions)} region(s): {', '.join(regions)} ...")
    maps = {region: client.get_price_map(region) for region in regions}

    # PricingClient logs and returns empty maps on a failed fetch. Fail loudly
    # instead, so a scheduled run with broken credentials doesn't pass silently.
    failed = [region for region, prices in maps.items() if not prices.on_demand[0]]
    if failed:
        sys.exit(f"error: no on-demand prices fetched for {', '.join(failed)}; snapshots left unchanged.")

    for path, rows in data.items():
        out = [_refresh_row(row, maps) for row in rows]
        priced = sum(1 for r in out if r.get("spot_price_hr"))
        with open(path, "w") as f:
            json.dump(out, f, indent=2)
            f.write("\n")
        print(f"  {path}: {len(out)} rows, {priced} with spot price")


if __name__ == "__main__":
    main()
