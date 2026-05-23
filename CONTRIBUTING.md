# Contributing to cloudfit-provider-gcp

Thank you for your interest in contributing. This package is the GCP provider plugin for [cloudfit-core](https://github.com/cloudfit-io/cloudfit-core) — it fetches GCP Compute Engine machine types, pricing, and availability and normalizes them into `cloudfit.models.MachineType` objects.

## Ways to contribute

- **Bug reports** — open an issue with a minimal reproducible example
- **New regions** — add a region to the registry (see [Extending the data maps](#extending-the-data-maps))
- **Pricing accuracy** — improve SKU matching in `pricing.py`
- **GPU / generation coverage** — keep the VRAM and generation maps current as GCP releases new families
- **Documentation** — examples, corrections, tutorials

## Development setup

```bash
git clone https://github.com/cloudfit-io/cloudfit-provider-gcp
cd cloudfit-provider-gcp

# cloudfit-core must be importable. Until it is published to PyPI, install it
# from source FIRST so the dependency below resolves to your local copy:
pip install -e ../cloudfit-core      # adjust path to your cloudfit-core checkout

pip install -e ".[dev]"
pytest
```

> The `.[dev]` install also pulls `google-cloud-compute` and `google-cloud-billing`. The unit tests don't need them (those clients are imported lazily and the tests run against recorded fixtures), but they're required to actually fetch live data.

## Running tests and lint

```bash
pytest tests/ -v
ruff check cloudfit_provider_gcp/
```

**No GCP credentials are needed to run the test suite** — `normalizer.py` and `regions.py` are pure functions tested against `tests/fixtures/machine_type_response.json`. Only live fetches (`provider.fetch_instances`) require Application Default Credentials.

## Extending the data maps

Most contributions touch one of these lookup tables:

| To add… | Edit | Notes |
|---|---|---|
| A new GCP region | `GCP_REGIONS` in `regions.py` **and** `_REGION_TO_BILLING_LABEL` in `pricing.py` | both must be updated, or pricing won't match |
| A new GPU type | `_GPU_VRAM_MAP` in `normalizer.py` | key is the GCP accelerator type, value is VRAM in GB |
| A new machine family generation | `_GEN_MAP` in `normalizer.py` | maps family prefix (e.g. `c4`) → generation label |

When you change normalization, add a representative entry to `tests/fixtures/machine_type_response.json` and a matching test in `tests/test_normalizer.py`.

## Pull request guidelines

- Keep PRs focused — one feature or fix per PR
- Add or update tests for any normalization or pricing change
- Run `pytest` and `ruff check cloudfit_provider_gcp/` before submitting
- Bump the version in `pyproject.toml` and `CITATION.cff` when releasing

## Provider interface

This package implements the `cloudfit.providers.base.Provider` interface:

```python
from cloudfit.providers.base import Provider
from cloudfit.models import MachineType

class GCPProvider(Provider):
    def fetch_instances(self, region: str) -> list[MachineType]: ...
    def get_pricing(self, instance_id: str, region: str) -> float: ...
    def get_availability(self, instance_id: str, region: str) -> float: ...
```

## Code of conduct

Be respectful. This project follows the [Contributor Covenant](https://www.contributor-covenant.org/).
