"""Tests for cloudfit_provider_gcp.pricing — pure functions, no GCP credentials."""

from types import SimpleNamespace

import pytest
from cloudfit_provider_gcp.pricing import (
    PricingClient,
    RegionPrices,
    _family_for,
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


def _sku(description, units, nanos, usage_type="OnDemand", resource_group="CPU",
         regions=("us-central1",)):
    return SimpleNamespace(
        description=description,
        pricing_info=_fake_pricing_info(units, nanos),
        category=SimpleNamespace(usage_type=usage_type, resource_group=resource_group),
        service_regions=list(regions),
    )


class TestParseSku:
    def test_on_demand_core_and_ram(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(_sku("N2 Instance Core running in Americas", 0, 31_611_000), p, "us-central1")
        PricingClient._parse_sku(_sku("N2 Instance Ram running in Americas", 0, 4_237_000,
                                      resource_group="RAM"), p, "us-central1")
        core, ram = p.on_demand
        assert core["n2"] == pytest.approx(0.031611)
        assert ram["n2"] == pytest.approx(0.004237)

    def test_spot_routed_by_usage_type(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(
            _sku("Spot Preemptible N2 Instance Core running in Americas", 0, 12_390_000,
                 usage_type="Preemptible"), p, "us-central1")
        assert p.spot[0]["n2"] == pytest.approx(0.01239)
        assert p.on_demand[0] == {}

    def test_cud_1yr_routed_by_usage_type(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(
            _sku("Commitment v1: N2 Cpu in Americas for 1 Year", 0, 19_915_000,
                 usage_type="Commit1Yr"), p, "us-central1")
        assert p.cud_1yr[0]["n2"] == pytest.approx(0.019915)

    def test_three_year_commitment_ignored(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(
            _sku("Commitment v1: N2 Cpu in Americas for 3 Year", 0, 15_000_000,
                 usage_type="Commit3Yr"), p, "us-central1")
        assert p.cud_1yr[0] == {}

    def test_region_not_in_service_regions_skipped(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(
            _sku("N2 Instance Core running in Netherlands", 0, 34_802_000,
                 regions=("europe-west4",)), p, "us-central1")
        assert p.on_demand[0] == {}

    def test_sole_tenancy_excluded(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(
            _sku("N2 Sole Tenancy Instance Core running in Americas", 0, 31_611_000), p, "us-central1")
        assert p.on_demand[0] == {}

    def test_category_named_family_resolved(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(_sku("Compute optimized Core running in Americas", 0, 33_982_000), p, "us-central1")
        assert p.on_demand[0]["c2"] == pytest.approx(0.033982)

    def test_zero_price_sku_ignored(self):
        p = RegionPrices.empty()
        PricingClient._parse_sku(_sku("N2 Instance Core running in Americas", 0, 0), p, "us-central1")
        assert p.on_demand[0] == {} and p.on_demand[1] == {}


class TestFamilyFor:
    def test_token_wins_over_alias(self):
        assert _family_for("m3 memory-optimized instance core running in americas") == "m3"

    def test_alias_when_no_token(self):
        assert _family_for("compute optimized core running in americas") == "c2"
        assert _family_for("memory-optimized instance core running in americas") == "m1"

    def test_none_when_unresolvable(self):
        assert _family_for("network egress to somewhere") is None


class TestMissingBillingLibrary:
    def test_get_price_map_raises_clear_import_error(self, monkeypatch):
        """A missing google-cloud-billing must not silently become $0 prices."""
        monkeypatch.setitem(__import__("sys").modules, "google.cloud.billing_v1", None)
        with pytest.raises(ImportError, match="google-cloud-billing is required"):
            PricingClient().get_price_map("us-central1")

    def test_transient_api_failure_still_degrades_to_empty_prices(self, monkeypatch):
        client = PricingClient()

        def boom(region):
            raise RuntimeError("503 from the Billing API")

        monkeypatch.setattr(client, "_fetch_price_map", boom)
        prices = client.get_price_map("us-central1")
        assert prices.on_demand == RegionPrices.empty().on_demand
