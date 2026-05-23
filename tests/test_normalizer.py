"""Tests for cloudfit_provider_gcp.normalizer — no GCP credentials needed."""

import json
from pathlib import Path
import pytest
from cloudfit_provider_gcp.normalizer import normalize_machine_type

FIXTURES = Path(__file__).parent / "fixtures" / "machine_type_response.json"


@pytest.fixture
def raw_machines():
    with FIXTURES.open() as f:
        return json.load(f)


def get_raw(raw_machines, name):
    return next(m for m in raw_machines if m["name"] == name)


class TestNormalizeMachineType:
    def test_basic_fields_n2(self, raw_machines):
        raw = get_raw(raw_machines, "n2-standard-32")
        mt  = normalize_machine_type(raw, region="us-central1", price_hr=1.23)
        assert mt.id       == "n2-standard-32"
        assert mt.provider == "gcp"
        assert mt.vcpu     == 32
        assert mt.ram_gb   == pytest.approx(128.0, abs=0.5)
        assert mt.price_hr == 1.23
        assert mt.region   == "us-central1"
        assert mt.status   == "active"

    def test_local_ssd_from_scratch_disks(self, raw_machines):
        # c3d-standard-60-lssd has 4 × 375 GB scratch disks
        raw = get_raw(raw_machines, "c3d-standard-60-lssd")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.local_ssd_tb == pytest.approx(1.5, abs=0.1)

    def test_local_ssd_from_name_suffix(self, raw_machines):
        # If scratchDisks is empty but name has lssd suffix
        raw = dict(get_raw(raw_machines, "c3d-standard-60-lssd"))
        raw["scratchDisks"] = []   # strip the fixture disks
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.local_ssd_tb == 1.5   # falls back to name-based detection

    def test_no_local_ssd(self, raw_machines):
        raw = get_raw(raw_machines, "n2-standard-32")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.local_ssd_tb == 0.0

    def test_gpu_detection_a100(self, raw_machines):
        raw = get_raw(raw_machines, "a2-highgpu-1g")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.gpu_count  == 1
        assert mt.gpu_vram_gb == 40

    def test_no_gpu(self, raw_machines):
        raw = get_raw(raw_machines, "n2-standard-32")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.gpu_count  == 0
        assert mt.gpu_vram_gb is None

    def test_deprecated_status(self, raw_machines):
        raw = get_raw(raw_machines, "n1-standard-8")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.status == "deprecated"

    def test_obsolete_becomes_tombstoned(self, raw_machines):
        raw = get_raw(raw_machines, "f1-micro")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.status == "tombstoned"

    def test_active_when_no_deprecated_field(self, raw_machines):
        raw = get_raw(raw_machines, "c2-standard-60")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.status == "active"

    def test_generation_inferred(self, raw_machines):
        raw = get_raw(raw_machines, "n2-standard-32")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.generation == "second"

    def test_c2_generation(self, raw_machines):
        raw = get_raw(raw_machines, "c2-standard-60")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.generation == "second"

    def test_default_price_zero(self, raw_machines):
        raw = get_raw(raw_machines, "n2-standard-32")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert mt.price_hr == 0.0

    def test_output_is_machine_type(self, raw_machines):
        from cloudfit.models import MachineType
        raw = get_raw(raw_machines, "n2-standard-32")
        mt  = normalize_machine_type(raw, region="us-central1")
        assert isinstance(mt, MachineType)
