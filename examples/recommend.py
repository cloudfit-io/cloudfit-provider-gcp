"""Example: recommend a GCP machine type for a workload.

Plugs cloudfit-provider-gcp into cloudfit-core:

    GCPProvider.fetch_instances()  →  list[MachineType]  →  cloudfit.rank()

Prerequisites
-------------
    pip install cloudfit-provider-gcp          # also installs cloudfit-core
    gcloud auth application-default login       # Application Default Credentials

Run
---
    python examples/recommend.py <gcp_project_id> [region]

    # e.g.
    python examples/recommend.py my-gcp-project us-central1
"""

from __future__ import annotations

import sys

from cloudfit import WorkloadProfile, rank
from cloudfit_provider_gcp import GCPProvider


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python examples/recommend.py <gcp_project_id> [region]")
        raise SystemExit(1)

    project_id = sys.argv[1]
    region = sys.argv[2] if len(sys.argv) > 2 else "us-central1"

    # 1. Describe the workload — here, an I/O-bound demultiplexing job.
    #    optimize_for: cost | performance | availability | balanced
    profile = WorkloadProfile(
        vcpu=32,
        ram_gb=120,
        workload="io-intensive",
        archetype="io",
        optimize_for="balanced",
    )

    # 2. Fetch candidate instances live from GCP (needs ADC credentials).
    provider = GCPProvider(project_id=project_id)
    print(f"Fetching GCP machine types for {region} ...")
    candidates = provider.fetch_instances(region=region)
    print(f"  {len(candidates)} machine types fetched\n")

    # 3. Score and rank them with cloudfit-core. Hard floors (RAM/vCPU/GPU)
    #    are applied automatically before scoring.
    results = rank(profile, candidates)
    qualified = [r for r in results if not r.disqualified]

    # 4. Show the top picks.
    print(
        f"Top picks for {profile.vcpu} vCPU / {profile.ram_gb:.0f} GB "
        f"(optimize_for={profile.optimize_for.value}):\n"
    )
    if not qualified:
        print("  no instance met the hard floors")
    for i, r in enumerate(qualified[:5], 1):
        m = r.instance
        print(
            f"  #{i}  {m.id:24}  score={r.score:.2f}  "
            f"${m.price_hr:6.2f}/hr  {m.vcpu:>3} vCPU / {m.ram_gb:>5.0f} GB  [{m.status}]"
        )

    print(f"\n{len(results) - len(qualified)} of {len(results)} disqualified by hard floors.")


if __name__ == "__main__":
    main()
