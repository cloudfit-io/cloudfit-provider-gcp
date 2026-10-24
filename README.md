# cloudfit-provider-gcp

[![PyPI version](https://img.shields.io/pypi/v/cloudfit-provider-gcp)](https://pypi.org/project/cloudfit-provider-gcp/)
[![Tests](https://github.com/cloudfit-io/cloudfit-provider-gcp/actions/workflows/ci.yml/badge.svg)](https://github.com/cloudfit-io/cloudfit-provider-gcp/actions)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

**GCP Compute Engine provider plugin for [cloudfit-core](https://github.com/cloudfit-io/cloudfit-core).**

Fetches machine types, availability, and on-demand, spot, and 1-year committed-use pricing from the GCP Compute Engine and Cloud Billing Catalog APIs, and normalizes them into `MachineType` objects that `cloudfit-core` understands, including each family's `perf_factor` and each GPU's `gpu_type`.

---

## Installation

```bash
pip install cloudfit-provider-gcp
```

Requires Python 3.10 or newer (CI tests 3.10 through 3.14) and `cloudfit-core>=0.8.2`.

---

## Authentication

Uses [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials). Set up once with:

```bash
gcloud auth application-default login
```

Or set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to a service account key path. In production (Cloud Run, GKE), credentials are picked up automatically from the instance metadata server: no configuration needed.

---

## Quick start

```python
from cloudfit_provider_gcp import GCPProvider
from cloudfit import rank, WorkloadProfile

# initialize: no credentials needed if ADC is configured
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

## Examples

Runnable scripts are in [`examples/`](examples/):

| Script | Needs GCP credentials? | What it shows |
|---|---|---|
| [`recommend.py`](examples/recommend.py) | yes (ADC) | live `GCPProvider.fetch_instances()` → `cloudfit.rank()` |
| [`recommend_offline.py`](examples/recommend_offline.py) | no | recorded fixture → `normalize_machine_type()` → `cloudfit.rank()` |

Try the offline one first: it runs anywhere, no GCP account required:

```bash
python examples/recommend_offline.py
```

```text
Ranking for 32 vCPU / 120 GB (optimize_for=balanced):

  ok  n2-standard-32            score=1.00  $  1.53/hr  [active]
  ok  c3d-standard-60-lssd      score=0.62  $  2.87/hr  [active]
  ok  c2-standard-60            score=0.59  $  2.82/hr  [active]
  --  a2-highgpu-1g             $  0.73/hr  [active]  ✗ RAM 85 GB < required 120 GB
  --  n1-standard-8             $  0.37/hr  [deprecated]  ✗ RAM 30 GB < required 120 GB
  --  f1-micro                  $  0.03/hr  [tombstoned]  ✗ RAM 1 GB < required 120 GB
```

---

## Pricing

Pricing is fetched from the [GCP Cloud Billing Catalog API](https://cloud.google.com/billing/docs/reference/rest), using each SKU's structured category (usage type, resource group, service regions) rather than parsing descriptions. `fetch_instances` fills three prices per machine type, each reconstructed from the family's per-vCPU and per-GB rates for the region:

| Field | Source SKUs |
|---|---|
| `price_hr` | on-demand |
| `spot_price_hr` | spot (preemptible) |
| `cud_1yr_price_hr` | 1-year committed use |

cloudfit-core scores whichever one the workload's `pricing_mode` selects. If a family's SKUs can't be matched, that price is left unset: `price_hr` falls back to `0.0` (the instance is still scored, with `cost_score` 0), and a missing spot or committed-use price falls back to on-demand at scoring time.

**Limitation:** the reconstruction covers CPU and RAM only. Accelerator cost is not added, so GPU machine types are under-priced by it; supply a known `price_hr` for GPU instances (the bundled snapshots do).

```python
price_hr = provider.get_pricing("n2-standard-32", region="us-central1")  # on-demand
# → about 1.55
```

---

## Scheduled refresh

### Bundled snapshots (weekly, automated)

`cloudfit-api` and `cloudfit-ui` ship a curated 875-instance GCP snapshot (alongside the AWS one from cloudfit-provider-aws). The [`refresh-snapshot`](.github/workflows/refresh-snapshot.yml) workflow in this repo runs every Monday at 06:00 UTC: it refreshes on-demand, spot, and committed-use prices in both snapshots in place with [`examples/refresh_prices.py`](examples/refresh_prices.py) (row set, regions, and statuses are preserved; GPU prices are left as is) and opens a pull request in each repo. The run fails instead of opening a PR if any region's prices can't be fetched. It authenticates to GCP with Workload Identity Federation (no stored keys) and needs the `SNAPSHOT_TOKEN`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, and `GCP_SERVICE_ACCOUNT` secrets; see the comments in the workflow file.

To refresh locally (needs `gcloud auth application-default login`):

```bash
make refresh-snapshot      # refreshes ../cloudfit-api and ../cloudfit-ui snapshots in place
```

To build a brand-new snapshot from a live fetch instead, use [`examples/generate_snapshot.py`](examples/generate_snapshot.py).

### Registry (PostgreSQL)

For a live registry, run the fetcher on a schedule and write results to the cloudfit registry store (PostgreSQL). The recommended pattern is a Cloud Scheduler trigger invoking a Cloud Run Job.

```python
from cloudfit_provider_gcp import GCPProvider
from cloudfit_provider_gcp.registry import write_to_registry

provider = GCPProvider(project_id="your-gcp-project")
instances = provider.fetch_instances_all_regions()
write_to_registry(instances, database_url=os.environ["DATABASE_URL"])
```

---

## Deprecation handling

When GCP marks a machine type as deprecated, the provider sets `status="deprecated"` on the `MachineType`. When a type is fully removed, it becomes `status="tombstoned"`: it is never deleted from the registry, so existing configs can warn instead of silently breaking.

---

## Repository structure

```
cloudfit-provider-gcp/
├── README.md
├── CHANGELOG.md             # release notes; GitHub Releases are built from it
├── CONTRIBUTING.md
├── CITATION.cff
├── pyproject.toml
├── Makefile                 # version bump, tag, test, lint, build
├── LICENSE
├── .gitignore
├── .github/
│   ├── dependabot.yml       # monthly GitHub Actions updates
│   └── workflows/
│       ├── ci.yml           # lint, mypy --strict, tests; PyPI publish and release on tags
│       └── refresh-snapshot.yml   # weekly price refresh PRs to cloudfit-api and cloudfit-ui
│
├── cloudfit_provider_gcp/
│   ├── __init__.py          # exports GCPProvider
│   ├── provider.py          # GCPProvider: implements Provider base class
│   ├── normalizer.py        # raw GCP API response → MachineType
│   ├── pricing.py           # Cloud Billing Catalog API → on-demand, spot, CUD prices
│   ├── regions.py           # GCP region list + helpers
│   └── registry.py          # write normalized instances to PostgreSQL
│
├── examples/
│   ├── recommend.py           # live fetch → rank (needs GCP credentials)
│   ├── recommend_offline.py   # fixture → rank (no credentials needed)
│   ├── generate_snapshot.py   # build a fresh snapshot from a live fetch
│   └── refresh_prices.py      # refresh prices in existing snapshots in place
│
└── tests/
    ├── test_normalizer.py   # unit tests: no API calls needed
    ├── test_pricing.py      # SKU parsing and price reconstruction
    ├── test_regions.py
    ├── test_registry.py
    └── fixtures/
        └── machine_type_response.json   # recorded GCP API response
```

---

## Related projects

- [`cloudfit-core`](https://github.com/cloudfit-io/cloudfit-core): scoring engine
- [`cloudfit-provider-aws`](https://github.com/cloudfit-io/cloudfit-provider-aws): AWS EC2 provider (public price list, no credentials)
- [`cloudfit-api`](https://github.com/cloudfit-io/cloudfit-api): REST API over the scoring engine ([live demo](https://chaitanyakasaraneni-cloudfit-api.hf.space/docs))
- [`cloudfit-ui`](https://github.com/cloudfit-io/cloudfit-ui): Gradio UI over the scoring engine ([live demo](https://chaitanyakasaraneni-cloudfit-ui.hf.space))
- [`samplesheet-parser`](https://github.com/chaitanyakasaraneni/samplesheet-parser): Illumina SampleSheet parser

## License

Apache 2.0: see [LICENSE](LICENSE).

---

<sub>Author: <a href="https://ckasaraneni.com">Chaitanya Krishna Kasaraneni</a> &nbsp;·&nbsp;
<a href="https://scholar.google.com/citations?user=Y2S8D2UAAAAJ">Google Scholar</a> &nbsp;·&nbsp;
<a href="https://orcid.org/0000-0001-5792-1095">ORCID 0000-0001-5792-1095</a></sub>
