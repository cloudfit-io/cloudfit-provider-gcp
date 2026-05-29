# Changelog

All notable changes to `cloudfit-provider-gcp` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No unreleased changes.

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

[Unreleased]: https://github.com/cloudfit-io/cloudfit-provider-gcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cloudfit-io/cloudfit-provider-gcp/releases/tag/v0.1.0
