# cloudfit-provider-gcp

[![PyPI version](https://img.shields.io/pypi/v/cloudfit-provider-gcp)](https://pypi.org/project/cloudfit-provider-gcp/)
[![Tests](https://github.com/cloudfit-io/cloudfit-provider-gcp/actions/workflows/ci.yml/badge.svg)](https://github.com/cloudfit-io/cloudfit-provider-gcp/actions)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

**GCP Compute Engine provider plugin for [cloudfit-core](https://github.com/cloudfit-io/cloudfit-core).**

Fetches machine types, pricing, and availability from the GCP Compute Engine API and normalizes them into `MachineType` objects that `cloudfit-core` understands.

---

## Installation

```bash
pip install cloudfit-provider-gcp
```

Requires Python 3.9+ and `cloudfit-core>=0.1.0`.

---

## Authentication

Uses [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials). Set up once with:

```bash
gcloud auth application-default login
```

Or set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to a service account key path. In production (Cloud Run, GKE), credentials are picked up automatically from the instance metadata server — no configuration needed.

---

## Quick start

```python
from cloudfit_provider_gcp import GCPProvider
from cloudfit import rank, WorkloadProfile

# initialize — no credentials needed if ADC is configured
provider = GCPProvider(project_id="your-gcp-project")

# fetch all machine types for a region
instances = provider.fetch_instances(region="us-central1")
print(f"fetched {len(instances)} machine types")

# plug directly into cloudfit-core
profile = WorkloadProfile(
    vcpu=60,
    ram_gb=224,
    workload="io-intensive",
    archetype="io",
    optimize_for="balanced",
)

results = rank(profile, instances)
for r in results[:3]:
    print(f"{r.instance.id:35s}  score={r.score:.2f}  ${r.instance.price_hr:.2f}/hr")
```

---

## Fetching multiple regions

```python
from cloudfit_provider_gcp import GCPProvider

provider = GCPProvider(project_id="your-gcp-project")

regions = ["us-central1", "us-east1", "europe-west1", "asia-east1"]
all_instances = []
for region in regions:
    all_instances.extend(provider.fetch_instances(region=region))

print(f"total: {len(all_instances)} machine types across {len(regions)} regions")
```

---

## Pricing

Pricing is fetched from the [GCP Cloud Billing Catalog API](https://cloud.google.com/billing/docs/reference/rest). Prices are on-demand (no committed-use or spot discount), reconstructed per instance from each family's vCPU and RAM SKU rates. If a family's SKUs can't be matched, `price_hr` falls back to `0.0` and the instance is still scored (its `cost_score` is just 0).

```python
price_hr = provider.get_pricing("n2-standard-32", region="us-central1")
# → 1.5468
```

---

## Cron / scheduled refresh

For production use, run the fetcher on a daily schedule and write results to the cloudfit registry store (PostgreSQL). The recommended pattern is a Cloud Scheduler trigger invoking a Cloud Run Job.

```python
from cloudfit_provider_gcp import GCPProvider
from cloudfit_provider_gcp.registry import write_to_registry

provider = GCPProvider(project_id="your-gcp-project")
instances = provider.fetch_instances_all_regions()
write_to_registry(instances, database_url=os.environ["DATABASE_URL"])
```

---

## Deprecation handling

When GCP marks a machine type as deprecated, the provider sets `status="deprecated"` on the `MachineType`. When a type is fully removed, it becomes `status="tombstoned"` — it is never deleted from the registry, so existing configs can warn instead of silently breaking.

---

## Repository structure

```
cloudfit-provider-gcp/
├── README.md
├── CONTRIBUTING.md
├── CITATION.cff
├── pyproject.toml
├── LICENSE
├── .gitignore
│
├── cloudfit_provider_gcp/
│   ├── __init__.py          # exports GCPProvider
│   ├── provider.py          # GCPProvider — implements Provider base class
│   ├── normalizer.py        # raw GCP API response → MachineType
│   ├── pricing.py           # Cloud Billing Catalog API → price_hr
│   ├── regions.py           # GCP region list + helpers
│   └── registry.py          # write normalized instances to PostgreSQL
│
└── tests/
    ├── test_normalizer.py   # unit tests — no API calls needed
    ├── test_regions.py
    └── fixtures/
        └── machine_type_response.json   # recorded GCP API response
```

---

## Related projects

- [`cloudfit-core`](https://github.com/cloudfit-io/cloudfit-core) — scoring engine
- [`cloudfit-provider-aws`](https://github.com/cloudfit-io/cloudfit-provider-aws) — AWS provider (coming soon)
- [`samplesheet-parser`](https://github.com/chaitanyakasaraneni/samplesheet-parser) — Illumina SampleSheet parser

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

<sub>Author: <a href="https://ckasaraneni.com">Chaitanya Krishna Kasaraneni</a> &nbsp;·&nbsp;
<a href="https://scholar.google.com/citations?user=Y2S8D2UAAAAJ">Google Scholar</a> &nbsp;·&nbsp;
<a href="https://orcid.org/0000-0001-5792-1095">ORCID 0000-0001-5792-1095</a></sub>
