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
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Family token in a SKU description, e.g. "n2" in "N2 Instance Core ...".
# Excludes the catalog version token ("v1") handled separately in _family_token.
_FAMILY_RE = re.compile(r"^[a-z]\d+[a-z]*$")

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


def _cud_group(region: str) -> str:
    """Billing region-group label used in committed-use SKU descriptions.

    Committed-use discounts are priced per region group (e.g. "Americas"), not
    per city like on-demand and spot SKUs. Returns "" for an unmapped region,
    in which case CUD matching is skipped and cost falls back to on-demand.
    """
    if region.startswith(("us-", "northamerica-", "southamerica-")):
        return "Americas"
    if region.startswith("europe-"):
        return "Europe"
    if region.startswith(("asia-", "australia-")):
        return "Asia Pacific"
    return ""


def _family_token(desc_lower: str) -> str | None:
    """Extract the machine family token (e.g. "n2") from a SKU description.

    Skips the catalog version token ("v1") that precedes the family in
    committed-use SKUs ("Commitment v1: N2 Cpu ...").
    """
    for tok in re.split(r"[\s:]+", desc_lower):
        if tok.startswith("v") and tok[1:].isdigit():
            continue
        if _FAMILY_RE.match(tok):
            return tok
    return None


# A (core_prices, ram_prices) pair: family → unit $/hr ($/vCPU/hr and $/GB/hr).
ComponentPrices = tuple[dict[str, float], dict[str, float]]


@dataclass
class RegionPrices:
    """Per-region component prices for each pricing mode.

    Each field is a ``(core_prices, ram_prices)`` pair keyed by machine family.
    Callers reconstruct a per-instance price with :func:`reconstruct_price`.
    Empty maps mean that mode was unavailable; cost then falls back to on-demand.
    """

    on_demand: ComponentPrices
    spot: ComponentPrices
    cud_1yr: ComponentPrices

    @classmethod
    def empty(cls) -> "RegionPrices":
        return cls(({}, {}), ({}, {}), ({}, {}))


class PricingClient:
    """Wraps the Cloud Billing Catalog API to return per-instance prices.

    Usage:
        client = PricingClient()
        prices = client.get_price_map(region="us-central1")
        price_hr = reconstruct_price("n2-standard-32", 32, 128.0, *prices.on_demand)
    """

    def __init__(self) -> None:
        self._cache: dict[str, RegionPrices] = {}

    def get_price_map(self, region: str) -> RegionPrices:
        """Return on-demand, spot, and 1-year committed-use prices for a region.

        Results are cached per region for the lifetime of the client instance.
        For production use, instantiate one PricingClient per cron run.

        Args:
            region: GCP region (e.g. "us-central1")

        Returns:
            A RegionPrices. All maps are empty if the Billing API is unavailable,
            so instances then fall back to ``price_hr=0.0``; spot/CUD maps are
            empty when those SKUs are absent, so those modes fall back to
            on-demand at scoring time.
        """
        if region in self._cache:
            return self._cache[region]

        try:
            prices = self._fetch_price_map(region)
        except Exception as exc:
            logger.warning(
                "Failed to fetch pricing for region %s: %s. "
                "Instances will have price_hr=0.0.",
                region, exc,
            )
            prices = RegionPrices.empty()

        self._cache[region] = prices
        return prices

    def _fetch_price_map(self, region: str) -> RegionPrices:
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
        cud_group = _cud_group(region)

        prices = RegionPrices.empty()
        for sku in skus:
            self._parse_sku(sku, prices, label, cud_group)
        return prices

    @staticmethod
    def _nano_to_usd(pricing_info: Any) -> float:
        """Extract USD price per unit from a SKU's pricingInfo."""
        try:
            expr = pricing_info[0].pricing_expression
            tier = expr.tiered_rates[0]
            nanos = tier.unit_price.nanos
            units = tier.unit_price.units
            return float(units + nanos / _NANO)
        except (IndexError, AttributeError):
            return 0.0

    @staticmethod
    def _parse_sku(
        sku: Any,
        prices: RegionPrices,
        region_label: str,
        cud_group: str,
    ) -> None:
        """Classify one SKU by pricing mode and route its price into the maps.

        On-demand and spot SKUs name a city ("... running in Iowa") and use
        "Instance Core"/"Instance Ram"; committed-use SKUs name a region group
        ("... in Americas for 1 Year") and use "Cpu"/"Ram". Best-effort: a SKU
        whose region label does not match is skipped, so the mode falls back to
        on-demand (spot/CUD) or to price_hr=0.0 (on-demand) downstream.
        """
        desc = sku.description.lower()
        price = PricingClient._nano_to_usd(sku.pricing_info)
        if price <= 0:
            return

        if "preemptible" in desc or "spot" in desc:
            core_prices, ram_prices = prices.spot
            label, is_cud = region_label, False
        elif "commitment" in desc and "1 year" in desc:
            core_prices, ram_prices = prices.cud_1yr
            label, is_cud = cud_group, True
        else:
            core_prices, ram_prices = prices.on_demand
            label, is_cud = region_label, False

        if label and label.lower() not in desc:
            return

        family = _family_token(desc)
        if family is None:
            return

        if is_cud:
            # Committed-use SKUs: "... N2 Cpu in Americas for 1 Year" / "... N2 Ram ...".
            if "cpu" in desc:
                core_prices[family] = price
            elif "ram" in desc:
                ram_prices[family] = price
        else:
            # On-demand and spot SKUs: "N2 Instance Core ..." / "N2 Instance Ram ...".
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
