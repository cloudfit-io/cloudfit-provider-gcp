"""Normalizes raw GCP Compute Engine API responses into cloudfit MachineType objects."""
from __future__ import annotations
from typing import Any
from cloudfit.models import MachineType

_DEPRECATION_MAP: dict[str, str] = {
    "ACTIVE":     "active",
    "DEPRECATED": "deprecated",
    "OBSOLETE":   "tombstoned",
    "DELETED":    "tombstoned",
}

_GPU_VRAM_MAP: dict[str, int] = {
    "nvidia-tesla-a100": 40,
    "nvidia-a100-80gb":  80,
    "nvidia-h100-80gb":  80,
    "nvidia-l4":         24,
    "nvidia-tesla-v100": 16,
    "nvidia-tesla-t4":   16,
    "nvidia-tesla-p100": 16,
    "nvidia-tesla-p4":    8,
}

_GEN_MAP: dict[str, str] = {
    "n1": "first",  "n2": "second", "n2d": "second", "n4": "fourth",
    "c2": "second", "c2d": "second","c3": "third",   "c3d": "third",
    "c4": "fourth", "m1": "first",  "m2": "second",  "m3": "third",
    "a2": "second", "a3": "third",  "e2": "second",
    "t2d": "second","t2a": "second","h3": "third",   "z3": "third",
}


def normalize_machine_type(
    raw: dict[str, Any],
    region: str,
    price_hr: float = 0.0,
) -> MachineType:
    """Convert a raw GCP MachineType API dict to a cloudfit MachineType.

    Args:
        raw:      Raw dict from google.cloud.compute_v1.MachineType
        region:   GCP region this machine type was fetched from
        price_hr: On-demand price/hr from Billing API (fetched separately)

    Returns:
        Normalized MachineType ready for cloudfit-core scoring.
    """
    name   = raw.get("name", "")
    family = name.split("-")[0].lower() if "-" in name else name.lower()

    ram_gb = raw.get("memoryMb", 0) / 1024
    vcpu   = raw.get("guestCpus", 0)

    local_ssd_tb  = _detect_local_ssd(name, raw)
    gpu_count, gpu_vram_gb = _detect_gpu(raw)

    dep     = raw.get("deprecated") or {}
    status  = _DEPRECATION_MAP.get(dep.get("state", "ACTIVE"), "active")
    gen     = _GEN_MAP.get(family)

    return MachineType(
        id=name,
        provider="gcp",
        vcpu=vcpu,
        ram_gb=round(ram_gb, 1),
        price_hr=price_hr,
        local_ssd_tb=local_ssd_tb,
        gpu_count=gpu_count,
        gpu_vram_gb=gpu_vram_gb,
        region=region,
        status=status,
        generation=gen,
    )


def _detect_local_ssd(name: str, raw: dict[str, Any]) -> float:
    scratch = raw.get("scratchDisks", [])
    if scratch:
        return round(len(scratch) * 375 / 1024, 2)
    if "lssd" in name.lower():
        return 1.5   # conservative default for lssd suffix variants
    return 0.0


def _detect_gpu(raw: dict[str, Any]) -> tuple[int, int | None]:
    accs = raw.get("accelerators", [])
    if not accs:
        return 0, None
    acc   = accs[0]
    count = acc.get("guestAcceleratorCount", 0)
    atype = acc.get("guestAcceleratorType", "").lower()
    vram  = next((v for k, v in _GPU_VRAM_MAP.items() if k in atype), None)
    return count, vram
