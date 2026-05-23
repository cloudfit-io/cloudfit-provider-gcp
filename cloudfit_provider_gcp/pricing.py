"""Fetches GCP on-demand pricing from the Cloud Billing Catalog API.

GCP pricing is not returned by the Compute Engine API — it lives in a
separate Cloud Billing Catalog. This module fetches and caches a price
map (machine_type_id → price_hr) for a given region.

Billing API notes
-----------------
- Service ID for Compute Engine: "6F81-5844-456A"
- SKU descriptions follow the pattern:
    "N2 Instance Core running in Americas"
    "N2 Instance Ram running in Americas"
  We reconstruct per-instance price from (cores × core_price) + (ram × ram_price).
- Prices are in USD, expressed as nano-USD units in the API response.
  Divide by 1,000,000,000 to get USD.

This module returns a best-effort price. If a SKU cannot be matched,
price_hr defaults to 0.0 — the scorer will still work, cost_score will
be 0 for unpriced instances.
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Nano-USD to USD conversion
_NANO = 1_000_000_000

# GCP Compute Engine billing service ID
_COMPUTE_SERVICE_ID = "6F81-5844-456A"

# Region → billing region label used in SKU descriptions
_REGION_TO_BILLING_LABEL: dict[str, str] = {
    "us-central1":           "Iowa",
    "us-east1":              "South Carolina",
    "us-east4":              "Northern Virginia",
    "us-west1":              "Oregon",
    "us-west2":              "Los Angeles",
    "us-west3":              "Salt Lake City",
    "us-west4":              "Las Vegas",
    "europe-west1":          "Belgium",
    "europe-west2":          "London",
    "europe-west3":          "Frankfurt",
    "europe-west4":          "Netherlands",
    "europe-west6":          "Zurich",
    "europe-central2":       "Warsaw",
    "europe-north1":         "Finland",
    "asia-east1":            "Taiwan",
    "asia-east2":            "Hong Kong",
    "asia-northeast1":       "Tokyo",
    "asia-northeast2":       "Osaka",
    "asia-northeast3":       "Seoul",
    "asia-south1":           "Mumbai",
    "asia-south2":           "Delhi",
    "asia-southeast1":       "Singapore",
    "asia-southeast2":       "Jakarta",
    "australia-southeast1":  "Sydney",
    "australia-southeast2":  "Melbourne",
    "northamerica-northeast1": "Montreal",
    "northamerica-northeast2": "Toronto",
    "southamerica-east1":    "Sao Paulo",
}


class PricingClient:
    """Wraps the Cloud Billing Catalog API to return per-instance prices.

    Usage:
        client = PricingClient()
        price_map = client.get_price_map(region="us-central1")
        price_hr  = price_map.get("n2-standard-32", 0.0)
    """

    def __init__(self) -> None:
        self._cache: dict[str, tuple[dict[str, float], dict[str, float]]] = {}

    def get_price_map(
        self, region: str
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Return component price maps for a region: ``(core_prices, ram_prices)``.

        Each map is keyed by machine family (e.g. ``"n2"``) → unit price/hr —
        ``core_prices`` is $/vCPU/hr and ``ram_prices`` is $/GB/hr. Callers
        reconstruct a per-instance price with :func:`reconstruct_price`.

        Results are cached per region for the lifetime of the client instance.
        For production use, instantiate one PricingClient per cron run.

        Args:
            region: GCP region (e.g. "us-central1")

        Returns:
            ``(core_prices, ram_prices)``. Both maps are empty if the Billing
            API is unavailable — instances then fall back to ``price_hr=0.0``.
        """
        if region in self._cache:
            return self._cache[region]

        try:
            price_maps = self._fetch_price_map(region)
        except Exception as exc:
            logger.warning(
                "Failed to fetch pricing for region %s: %s. "
                "Instances will have price_hr=0.0.",
                region, exc,
            )
            price_maps = ({}, {})

        self._cache[region] = price_maps
        return price_maps

    def _fetch_price_map(
        self, region: str
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Internal: fetch and parse SKUs from the Billing Catalog API."""
        try:
            from google.cloud import billing_v1
        except ImportError as exc:
            raise ImportError(
                "google-cloud-billing is required for pricing. "
                "Install with: pip install cloudfit-provider-gcp"
            ) from exc

        client    = billing_v1.CloudCatalogClient()
        parent    = f"services/{_COMPUTE_SERVICE_ID}"
        skus      = client.list_skus(parent=parent)
        label     = _REGION_TO_BILLING_LABEL.get(region, "")

        # Collect core and RAM prices per machine family
        core_prices: dict[str, float] = {}   # family → $/vCPU/hr
        ram_prices:  dict[str, float] = {}   # family → $/GB/hr

        for sku in skus:
            if label and label not in sku.description:
                continue
            self._parse_sku(sku, core_prices, ram_prices)

        # Caller reconstructs per-instance price from family + size.
        return core_prices, ram_prices

    @staticmethod
    def _nano_to_usd(pricing_info: Any) -> float:
        """Extract USD price per unit from a SKU's pricingInfo."""
        try:
            expr = pricing_info[0].pricing_expression
            tier = expr.tiered_rates[0]
            nanos = tier.unit_price.nanos
            units = tier.unit_price.units
            return units + nanos / _NANO
        except (IndexError, AttributeError):
            return 0.0

    @staticmethod
    def _parse_sku(sku: Any, core_prices: dict, ram_prices: dict) -> None:
        """Parse a single SKU into core or RAM price maps."""
        desc = sku.description.lower()
        price = PricingClient._nano_to_usd(sku.pricing_info)
        if price <= 0:
            return

        # Identify family from description
        # e.g. "N2 Instance Core running in Iowa" → family "n2", type "core"
        parts = desc.split()
        if len(parts) < 3:
            return

        family = parts[0].lower()

        if "core" in desc and "instance" in desc:
            core_prices[family] = price
        elif "ram" in desc and "instance" in desc:
            ram_prices[family] = price


def reconstruct_price(
    machine_type_id: str,
    vcpu: int,
    ram_gb: float,
    core_prices: dict[str, float],
    ram_prices: dict[str, float],
) -> float:
    """Reconstruct on-demand price/hr from core + RAM component prices.

    price = (vcpu × core_price) + (ram_gb × ram_price)

    Args:
        machine_type_id: e.g. "n2-standard-32"
        vcpu:            Number of vCPUs
        ram_gb:          RAM in GB
        core_prices:     family → $/vCPU/hr
        ram_prices:      family → $/GB/hr

    Returns:
        Estimated on-demand price per hour in USD.
        Returns 0.0 if family not found in price maps.
    """
    family = machine_type_id.split("-")[0].lower()
    core_p = core_prices.get(family, 0.0)
    ram_p  = ram_prices.get(family, 0.0)
    if core_p == 0.0 and ram_p == 0.0:
        return 0.0
    return round((vcpu * core_p) + (ram_gb * ram_p), 4)
