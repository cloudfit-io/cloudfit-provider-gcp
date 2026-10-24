"""Fetches GCP pricing from the Cloud Billing Catalog API.

GCP pricing is not returned by the Compute Engine API — it lives in a separate
Cloud Billing Catalog. This module fetches per-region component prices (per-vCPU
and per-GB rates, per machine family) for on-demand, spot, and 1-year
committed-use pricing, which callers combine with :func:`reconstruct_price`.

Why structured fields, not description parsing
----------------------------------------------
The catalog has tens of thousands of Compute SKUs whose descriptions vary widely
(Sole Tenancy, Custom, Premium, GPU-attach, region groups vs cities, ...). Rather
than parse free text, we key off the SKU's structured fields:

- ``category.usage_type``   → OnDemand / Preemptible (spot) / Commit1Yr (CUD)
- ``category.resource_group`` → CPU (core) / RAM
- ``service_regions``       → the exact region ids the SKU applies to

The machine family is taken from the description's family token (e.g. "n2" in
"N2 Instance Core running in Americas"), with a small alias table for the few
families GCP names by category ("Compute optimized" = c2, "Memory-optimized" = m1).
SKU variants that are not predefined on-demand shapes (Sole Tenancy, Custom,
Premium, Extended) are excluded.

This is still best-effort: a family with no matching SKU gets no price, and the
scorer treats an unpriced instance as cost 0.0 (never free). Prices are in USD,
expressed as nano-USD; divide by 1e9.
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

# SKU category usage_type → our pricing mode (matches RegionPrices field names).
# Other usage types (Commit3Yr, etc.) are intentionally ignored.
_USAGE_TYPE_TO_MODE: dict[str, str] = {
    "OnDemand": "on_demand",
    "Preemptible": "spot",
    "Commit1Yr": "cud_1yr",
}

# SKU category resource_group → price component.
_RESOURCE_GROUP_TO_COMPONENT: dict[str, str] = {"CPU": "core", "RAM": "ram"}

# Description substrings that mark a SKU as not a predefined on-demand shape.
# Excluding these leaves exactly the base core/ram rate per family and region.
_EXCLUDE_TOKENS: tuple[str, ...] = ("sole tenancy", "custom", "premium", "extended")

# Families GCP names by category instead of a family token. A family token in
# the description always wins (e.g. "M3 Memory-optimized ..." resolves to m3);
# these aliases only apply when no token is present.
_CATEGORY_FAMILY_ALIASES: dict[str, str] = {
    "compute optimized": "c2",
    "memory-optimized": "m1",
}


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


def _family_for(desc_lower: str) -> str | None:
    """Resolve a machine family from a SKU description, token first then alias."""
    token = _family_token(desc_lower)
    if token is not None:
        return token
    for phrase, family in _CATEGORY_FAMILY_ALIASES.items():
        if phrase in desc_lower:
            return family
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
        For production use, instantiate one PricingClient per cron run; pricing
        is not meant to be fetched on the request path (see module docs).

        Args:
            region: GCP region (e.g. "us-central1")

        Returns:
            A RegionPrices. All maps are empty if the Billing API call fails,
            so instances then fall back to ``price_hr=0.0``; spot/CUD maps are
            empty when those SKUs are absent, so those modes fall back to
            on-demand at scoring time.

        Raises:
            ImportError: if google-cloud-billing is not installed. That is a
                broken installation, not a transient failure, so it is not
                downgraded to zero prices.
        """
        if region in self._cache:
            return self._cache[region]

        try:
            prices = self._fetch_price_map(region)
        except ImportError:
            raise
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
            import google.cloud.billing_v1 as billing_v1
        except ImportError as exc:
            raise ImportError(
                "google-cloud-billing is required for pricing. "
                "Install with: pip install cloudfit-provider-gcp"
            ) from exc

        client = billing_v1.CloudCatalogClient()
        skus = client.list_skus(parent=f"services/{_COMPUTE_SERVICE_ID}")

        prices = RegionPrices.empty()
        for sku in skus:
            self._parse_sku(sku, prices, region)
        return prices

    @staticmethod
    def _nano_to_usd(pricing_info: Any) -> float:
        """Extract USD price per unit from a SKU's pricingInfo (last tier)."""
        try:
            expr = pricing_info[0].pricing_expression
            tier = expr.tiered_rates[-1]
            nanos = tier.unit_price.nanos
            units = tier.unit_price.units
            return float(units + nanos / _NANO)
        except (IndexError, AttributeError):
            return 0.0

    @staticmethod
    def _parse_sku(sku: Any, prices: RegionPrices, region: str) -> None:
        """Route one SKU's price into the maps using its structured category.

        Keys off ``service_regions`` (exact region match), ``usage_type``
        (mode), and ``resource_group`` (core vs RAM). Non-predefined shapes
        (Sole Tenancy / Custom / Premium / Extended) are skipped, and the first
        match per (family, mode, component) wins.
        """
        if region not in sku.service_regions:
            return
        mode = _USAGE_TYPE_TO_MODE.get(sku.category.usage_type)
        if mode is None:
            return
        component = _RESOURCE_GROUP_TO_COMPONENT.get(sku.category.resource_group)
        if component is None:
            return

        desc = sku.description.lower()
        if any(token in desc for token in _EXCLUDE_TOKENS):
            return

        price = PricingClient._nano_to_usd(sku.pricing_info)
        if price <= 0:
            return

        family = _family_for(desc)
        if family is None:
            return

        core_prices, ram_prices = getattr(prices, mode)
        target = core_prices if component == "core" else ram_prices
        target.setdefault(family, price)


def reconstruct_price(
    machine_type_id: str,
    vcpu: int,
    ram_gb: float,
    core_prices: dict[str, float],
    ram_prices: dict[str, float],
) -> float:
    """Reconstruct a per-hour price from core + RAM component prices.

    price = (vcpu × core_price) + (ram_gb × ram_price)

    Pass the component maps for the mode you want (``*prices.on_demand``,
    ``*prices.spot``, or ``*prices.cud_1yr``).

    Args:
        machine_type_id: e.g. "n2-standard-32"
        vcpu:            Number of vCPUs
        ram_gb:          RAM in GB
        core_prices:     family → $/vCPU/hr
        ram_prices:      family → $/GB/hr

    Returns:
        Estimated price per hour in USD.
        Returns 0.0 if family not found in price maps.

    Limitation: this is a CPU + RAM reconstruction only. Accelerator cost is not
    included, so GPU machine types are under-priced here; price GPUs from their
    own catalog SKUs or supply a known price_hr for them.
    """
    family = machine_type_id.split("-")[0].lower()
    core_p = core_prices.get(family, 0.0)
    ram_p  = ram_prices.get(family, 0.0)
    if core_p == 0.0 and ram_p == 0.0:
        return 0.0
    return round((vcpu * core_p) + (ram_gb * ram_p), 4)
