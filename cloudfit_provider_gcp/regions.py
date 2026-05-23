"""GCP region list and helpers for cloudfit-provider-gcp."""
from __future__ import annotations

GCP_REGIONS: list[str] = [
    "us-central1", "us-east1", "us-east4", "us-west1",
    "us-west2", "us-west3", "us-west4",
    "northamerica-northeast1", "northamerica-northeast2",
    "southamerica-east1",
    "europe-west1", "europe-west2", "europe-west3",
    "europe-west4", "europe-west6", "europe-central2", "europe-north1",
    "asia-east1", "asia-east2",
    "asia-northeast1", "asia-northeast2", "asia-northeast3",
    "asia-south1", "asia-south2",
    "asia-southeast1", "asia-southeast2",
    "australia-southeast1", "australia-southeast2",
]

def region_to_zone(region: str) -> str:
    """Return first zone in a region (e.g. us-central1 → us-central1-a)."""
    return f"{region}-a"

def zone_to_region(zone: str) -> str:
    """Return region for a zone (e.g. us-central1-a → us-central1)."""
    return "-".join(zone.split("-")[:-1])
