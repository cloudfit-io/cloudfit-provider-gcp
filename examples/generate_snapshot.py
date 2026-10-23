"""Generate a bundled machine-type snapshot from a live GCP fetch.

This is what refreshes the JSON snapshots shipped by cloudfit-api and cloudfit-ui.
It fetches machine types (and on-demand, spot, and 1-year committed-use prices)
for the given regions and writes them as a list of cloudfit MachineType records,
including the scoring-depth fields (perf_factor, gpu_type, spot/CUD prices).

Prerequisites
-------------
    pip install 'cloudfit-provider-gcp'        # installs google-cloud-compute/billing
    gcloud auth application-default login       # Application Default Credentials

Run
---
    python examples/generate_snapshot.py <gcp_project_id> --output gcp_snapshot.json

    # custom regions (default: the five bundled-snapshot regions)
    python examples/generate_snapshot.py my-proj --regions us-central1 europe-west4

Notes
-----
- This makes live, billed Billing/Compute API calls against <gcp_project_id>.
- Spot and committed-use prices are populated when the Billing catalog exposes
  them; missing modes are simply omitted and fall back to on-demand at scoring
  time. Committed-use region-group matching is best-effort (see pricing.py).
- The output is a raw per-region dump. The shipped snapshots are additionally
  curated (per-region family tiers); apply any such filtering downstream.
"""

from __future__ import annotations

import argparse
import json

from cloudfit_provider_gcp import GCPProvider

# The regions carried by the bundled cloudfit-api / cloudfit-ui snapshots.
DEFAULT_REGIONS = [
    "us-central1",
    "us-east1",
    "us-west1",
    "europe-west4",
    "asia-southeast1",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a GCP machine-type snapshot.")
    parser.add_argument("project_id", help="GCP project ID (billed for the API calls).")
    parser.add_argument(
        "--regions",
        nargs="+",
        default=DEFAULT_REGIONS,
        help="Regions to fetch (default: the five bundled-snapshot regions).",
    )
    parser.add_argument(
        "--output",
        default="gcp_snapshot.json",
        help="Output JSON path (default: gcp_snapshot.json).",
    )
    args = parser.parse_args()

    provider = GCPProvider(project_id=args.project_id, enable_pricing=True)
    print(f"Fetching {len(args.regions)} region(s): {', '.join(args.regions)} ...")
    instances = provider.fetch_instances_all_regions(regions=args.regions)
    print(f"  {len(instances)} machine types fetched")

    rows = [m.model_dump(exclude_none=True) for m in instances]
    with open(args.output, "w") as f:
        json.dump(rows, f, indent=2)
        f.write("\n")

    priced = sum(1 for m in instances if m.price_hr > 0)
    spot = sum(1 for m in instances if m.spot_price_hr)
    print(f"  wrote {len(rows)} rows to {args.output} ({priced} priced, {spot} with spot price)")


if __name__ == "__main__":
    main()
