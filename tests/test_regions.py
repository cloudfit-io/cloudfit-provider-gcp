"""Tests for cloudfit_provider_gcp.regions."""

from cloudfit_provider_gcp.regions import (
    GCP_REGIONS, region_to_zone, zone_to_region
)


def test_gcp_regions_not_empty():
    assert len(GCP_REGIONS) > 0


def test_region_to_zone():
    assert region_to_zone("us-central1") == "us-central1-a"
    assert region_to_zone("europe-west1") == "europe-west1-a"
    assert region_to_zone("asia-east1")   == "asia-east1-a"


def test_zone_to_region():
    assert zone_to_region("us-central1-a") == "us-central1"
    assert zone_to_region("us-central1-b") == "us-central1"
    assert zone_to_region("europe-west1-c") == "europe-west1"


def test_roundtrip_region_zone_region():
    for region in GCP_REGIONS:
        zone = region_to_zone(region)
        assert zone_to_region(zone) == region


def test_all_regions_have_zone():
    for region in GCP_REGIONS:
        zone = region_to_zone(region)
        assert zone.startswith(region)
        assert zone.endswith("-a")
