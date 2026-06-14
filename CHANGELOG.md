# Changelog

All notable changes to `cloudfit-provider-gcp` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
