# Changelog

All notable changes to `cloudfit-provider-gcp` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes._

## [0.3.1] - 2026-10-22

### Fixed
- Release CI: pinned `ruff>=0.15,<0.16` in the dev extras. ruff 0.17 enabled new default rules that failed the lint step, so the `v0.3.0` tag was never published to PyPI; 0.3.1 is the first published release with the 0.3.0 changes.

## [0.3.0] - 2026-10-22

### Added
- **Snapshot tooling.** `examples/generate_snapshot.py` builds a fresh snapshot from a live fetch; `examples/refresh_prices.py` refreshes prices on existing curated snapshots in place (idempotent, GPU prices preserved). A `make refresh-snapshot` target and a scheduled GitHub Actions workflow (`.github/workflows/refresh-snapshot.yml`) run the refresh weekly and open a PR in cloudfit-api and cloudfit-ui. Pricing stays off the request path.

### Changed
- **Rewrote pricing to the current Billing catalog.** The old parser assumed `"<Family> Instance Core running in <City>"` SKUs keyed by a per-region city (e.g. "Iowa"). The live catalog (~31k Compute SKUs) has no such "Iowa" SKU and instead prices predefined instances by region group, split across Sole Tenancy / Custom / Spot / Commitment shapes. Pricing now keys off the SKU's structured fields (`category.usage_type`, `category.resource_group`, `service_regions`) and excludes non-predefined shapes, with a small alias table for category-named families ("Compute optimized" = c2, "Memory-optimized" = m1). On-demand coverage for the bundled regions went from ~10% to ~90% and matches published GCP prices (n2-standard-8 = $0.3885/hr). `PricingClient.get_price_map` keeps the `RegionPrices` shape; `_REGION_TO_BILLING_LABEL` and `_cud_group` are removed.

### Fixed
- **Live fetches returned `vcpu=0` / `ram_gb=0` / no GPU.** The Compute API client's `to_dict` emits snake_case field names by default (`guest_cpus`, `memory_mb`), but the normalizer reads camelCase (`guestCpus`, `memoryMb`). `_list_machine_types` and `_get_machine_type_raw` now pass `preserving_proto_field_name=False` so the dict keys match what the normalizer expects. (Unit tests passed because the fixture is camelCase; only live fetches were affected.)
- **`mypy --strict` cleanliness with the Google libraries installed.** Annotated `GCPProvider._compute_client` as `Any` (was inferred `None`, so the lazy client assignment failed) and imported `billing_v1` as a submodule to avoid a namespace `attr-defined` error. These surfaced only when `google-cloud-compute`/`google-cloud-billing` are present.

### Known limitations
- `reconstruct_price` covers CPU + RAM only; accelerator cost is not added, so GPU machine types are under-priced by the reconstruction. Supply a known `price_hr` for GPU instances (the bundled snapshots do).

## [0.2.0] - 2026-06-23

### Changed
- Require `cloudfit-core>=0.8.0` for the scoring-depth fields (`perf_factor`, `gpu_type`, spot/committed-use pricing, explainability).

### Added
- **Populate `perf_factor` and `gpu_type` (scoring-depth Layers 1 and 3).** `normalize_machine_type` now sets `perf_factor` from the core `PERF_FACTORS` table (via `perf_factor_for`) and `gpu_type` from the accelerator name, so the engine scores effective per-vCPU capacity and GPU throughput instead of raw counts.
- **Fetch spot and 1-year committed-use prices (scoring-depth Layer 2).** `PricingClient.get_price_map` now returns a `RegionPrices` with on-demand, spot, and `cud_1yr` component maps, parsed from the Billing Catalog (preemptible/spot SKUs by city label; committed-use SKUs by region group). `normalize_machine_type` accepts `spot_price_hr` and `cud_1yr_price_hr`, which `GCPProvider.fetch_instances` reconstructs per instance. Missing modes fall back to on-demand. Committed-use region-group matching is best-effort.
- Tests for `perf_factor`/`gpu_type` population and spot/committed-use SKU parsing (no GCP credentials).

### Changed (internal)
- `PricingClient.get_price_map` return type changed from `(core_prices, ram_prices)` to `RegionPrices`. The only caller (`provider.py`) is updated; downstream callers using `*prices.on_demand` get the previous behavior.

## [0.1.2] - 2026-06-14

### Changed
- Require `cloudfit-core>=0.6.1` (archetype-aware scoring, validated weights, `extra="forbid"` models, and the `py.typed` marker).
- Minimum Python is now 3.10 (matches cloudfit-core; PEP 604 unions in the core models are not reliably evaluable on 3.9).

### Added
- Full type annotations across `provider.py`, `pricing.py`, and `registry.py`; the package now passes `mypy --strict` against a typed cloudfit-core.
- Unit tests for `registry.write_to_registry` (mock psycopg2, no live database) and `pricing.reconstruct_price` / SKU parsing (no GCP credentials).

### Fixed
- Documented the `_detect_local_ssd` name-suffix fallback limitation (fixed 1.5 TB regardless of size variant when the API omits `scratchDisks`).

## [0.1.1] - 2026-06-02

### Changed
- Regenerated the README offline-example output for cloudfit-core 0.4.0 (candidate-relative cost scoring; the cheap near-exact-fit now ranks first).

## [0.1.0] - 2026-05-22

### Added
- Initial release of the cloudfit GCP provider.
- `GCPProvider` implementing the cloudfit `Provider` interface from `cloudfit-core`.
- `fetch_instances(region)` to fetch machine types for a single GCP region.
- `fetch_instances_all_regions(regions=[...])` for multi-region fetches, defaulting to the full GCP region list when `regions` is omitted.
- `get_pricing(instance_id, region)` against the Cloud Billing Catalog API for on-demand pricing reconstruction.
- `get_availability(instance_id, region)` reporting active / deprecated / tombstoned status from the Compute Engine API.
- Application Default Credentials support (`gcloud auth application-default login` locally; automatic in Cloud Run / GKE).
- Normalizer (`normalizer.normalize_machine_type`) for raw GCP Compute Engine responses into cloudfit's `MachineType` schema.
- Region helpers (`regions.GCP_REGIONS`, `region_to_zone`, `zone_to_region`).
- Examples directory with live (`recommend.py`) and offline (`recommend_offline.py`) flows showing provider → core integration.
- Apache 2.0 license. CITATION.cff for academic citation.

[0.1.2]: https://github.com/cloudfit-io/cloudfit-provider-gcp/releases/tag/v0.1.2
[0.1.1]: https://github.com/cloudfit-io/cloudfit-provider-gcp/releases/tag/v0.1.1
[0.1.0]: https://github.com/cloudfit-io/cloudfit-provider-gcp/releases/tag/v0.1.0
