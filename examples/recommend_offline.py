"""Example: rank GCP machine types WITHOUT a GCP account.

Same flow as recommend.py, but instead of a live API call it normalizes a
recorded GCP Compute Engine response (the test fixture) and ranks it with
cloudfit-core. Runnable anywhere — no credentials, no google-cloud libs.

    recorded JSON  →  normalize_machine_type()  →  list[MachineType]  →  cloudfit.rank()

Run
---
    python examples/recommend_offline.py
"""

from __future__ import annotations

import json
from pathlib import Path

from cloudfit import WorkloadProfile, rank
from cloudfit_provider_gcp.normalizer import normalize_machine_type

# Recorded GCP API response shipped with the test suite.
FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "machine_type_response.json"


def _demo_price(raw: dict) -> float:
    """Stand-in price so the demo ranks meaningfully offline.

    Live usage gets real prices from the Billing Catalog API via the provider;
    here we approximate $/hr from a simple vCPU + RAM rate.
    """
    vcpu = raw.get("guestCpus", 0)
    ram_gb = raw.get("memoryMb", 0) / 1024
    return round(vcpu * 0.031 + ram_gb * 0.0042, 3)


def main() -> None:
    region = "us-central1"

    # 1. Describe the workload (I/O-bound demultiplexing job).
    profile = WorkloadProfile(
        vcpu=32,
        ram_gb=120,
        workload="io-intensive",
        archetype="io",
        optimize_for="balanced",
    )

    # 2. Normalize the recorded response into cloudfit MachineType objects —
    #    this is exactly what GCPProvider.fetch_instances() does internally.
    raw_machines = json.loads(FIXTURE.read_text())
    candidates = [
        normalize_machine_type(raw, region=region, price_hr=_demo_price(raw))
        for raw in raw_machines
    ]
    print(f"Normalized {len(candidates)} machine types from the recorded fixture\n")

    # 3. Score and rank with cloudfit-core. Hard floors run before scoring.
    results = rank(profile, candidates)

    # 4. Show the full ranking, including why anything was disqualified.
    print(
        f"Ranking for {profile.vcpu} vCPU / {profile.ram_gb:.0f} GB "
        f"(optimize_for={profile.optimize_for.value}):\n"
    )
    for r in results:
        m = r.instance
        if r.disqualified:
            print(f"  --  {m.id:24}  ${m.price_hr:6.2f}/hr  [{m.status}]  ✗ {r.disqualify_reason}")
        else:
            print(f"  ok  {m.id:24}  score={r.score:.2f}  ${m.price_hr:6.2f}/hr  [{m.status}]")


if __name__ == "__main__":
    main()
