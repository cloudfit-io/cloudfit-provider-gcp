# Changelog

All notable changes to `cloudfit-provider-gcp` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
