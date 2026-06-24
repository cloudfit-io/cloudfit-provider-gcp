"""Tests for cloudfit_provider_gcp.pricing — pure functions, no GCP credentials."""

from types import SimpleNamespace

import pytest
from cloudfit_provider_gcp.pricing import (
    PricingClient,
    RegionPrices,
    _cud_group,
    reconstruct_price,
)


def _fake_pricing_info(units: int, nanos: int):
    rate = SimpleNamespace(unit_price=SimpleNamespace(units=units, nanos=nanos))
    expr = SimpleNamespace(tiered_rates=[rate])
    return [SimpleNamespace(pricing_expression=expr)]


class TestReconstructPrice:
    def test_basic_core_plus_ram(self):
        core = {"n2": 0.031611}
        ram = {"n2": 0.004237}
        price = reconstruct_price("n2-standard-32", 32, 128.0, core, ram)
        assert price == round(32 * 0.031611 + 128 * 0.004237, 4)
        assert price > 0

    def test_unknown_family_returns_zero(self):
        assert reconstruct_price("xyz-standard-4", 4, 16.0, {"n2": 0.03}, {"n2": 0.004}) == 0.0

    def test_empty_maps_returns_zero(self):
        assert reconstruct_price("n2-standard-4", 4, 16.0, {}, {}) == 0.0


class TestNanoToUsd:
    def test_converts_units_and_nanos(self):
        assert PricingClient._nano_to_usd(_fake_pricing_info(0, 31_611_000)) == pytest.approx(0.031611)

    def test_malformed_returns_zero(self):
        assert PricingClient._nano_to_usd([]) == 0.0


def _sku(description: str, units: int, nanos: int):
    return SimpleNamespace(description=description, pricing_info=_fake_pricing_info(units, nanos))


class TestParseSku:
    def test_on_demand_core_and_ram(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(_sku("N2 Instance Core running in Iowa", 0, 31_611_000), p, "Iowa", "Americas")
        PricingClient._parse_sku(_sku("N2 Instance Ram running in Iowa", 0, 4_237_000), p, "Iowa", "Americas")
        core, ram = p.on_demand
        assert core["n2"] == pytest.approx(0.031611)
        assert ram["n2"] == pytest.approx(0.004237)

    def test_spot_routed_to_spot_maps(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(_sku("Spot Preemptible N2 Instance Core running in Iowa", 0, 9_000_000), p, "Iowa", "Americas")
        assert p.spot[0]["n2"] == pytest.approx(0.009)
        assert p.on_demand[0] == {}   # not double-counted as on-demand

    def test_cud_1yr_routed_to_cud_maps(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(_sku("Commitment v1: N2 Cpu in Americas for 1 Year", 0, 20_000_000), p, "Iowa", "Americas")
        PricingClient._parse_sku(_sku("Commitment v1: N2 Ram in Americas for 1 Year", 0, 3_000_000), p, "Iowa", "Americas")
        assert p.cud_1yr[0]["n2"] == pytest.approx(0.020)
        assert p.cud_1yr[1]["n2"] == pytest.approx(0.003)

    def test_three_year_cud_not_captured_as_one_year(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(_sku("Commitment v1: N2 Cpu in Americas for 3 Year", 0, 15_000_000), p, "Iowa", "Americas")
        assert p.cud_1yr[0] == {}

    def test_region_mismatch_skipped(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(_sku("N2 Instance Core running in Belgium", 0, 31_611_000), p, "Iowa", "Americas")
        assert p.on_demand[0] == {}

    def test_zero_price_sku_ignored(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(_sku("N2 Instance Core running in Iowa", 0, 0), p, "Iowa", "Americas")
        assert p.on_demand[0] == {} and p.on_demand[1] == {}


class TestCudGroup:
    def test_americas_europe_asia(self):
        assert _cud_group("us-central1") == "Americas"
        assert _cud_group("europe-west4") == "Europe"
        assert _cud_group("asia-southeast1") == "Asia Pacific"
        assert _cud_group("australia-southeast1") == "Asia Pacific"

    def test_unmapped_region_returns_empty(self):
        assert _cud_group("mars-west1") == ""
