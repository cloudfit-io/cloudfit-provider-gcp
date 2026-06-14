"""Tests for cloudfit_provider_gcp.pricing — pure functions, no GCP credentials."""

from types import SimpleNamespace

import pytest
from cloudfit_provider_gcp.pricing import PricingClient, reconstruct_price


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


class TestParseSku:
    def test_core_and_ram_into_maps(self):
        core: dict[str, float] = {}
        ram: dict[str, float] = {}
        sku_core = SimpleNamespace(
            description="N2 Instance Core running in Iowa",
            pricing_info=_fake_pricing_info(0, 31_611_000),
        )
        sku_ram = SimpleNamespace(
            description="N2 Instance Ram running in Iowa",
            pricing_info=_fake_pricing_info(0, 4_237_000),
        )
        PricingClient._parse_sku(sku_core, core, ram)
        PricingClient._parse_sku(sku_ram, core, ram)
        assert core["n2"] == pytest.approx(0.031611)
        assert ram["n2"] == pytest.approx(0.004237)

    def test_zero_price_sku_ignored(self):
        core: dict[str, float] = {}
        ram: dict[str, float] = {}
        sku = SimpleNamespace(
            description="N2 Instance Core running in Iowa",
            pricing_info=_fake_pricing_info(0, 0),
        )
        PricingClient._parse_sku(sku, core, ram)
        assert core == {} and ram == {}
