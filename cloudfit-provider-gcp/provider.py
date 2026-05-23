"""GCP Compute Engine provider for cloudfit-core."""

from __future__ import annotations
import logging
from typing import Iterator

from cloudfit.models import MachineType
from cloudfit.providers.base import Provider

from .normalizer import normalize_machine_type
from .pricing import PricingClient, reconstruct_price
from .regions import GCP_REGIONS, region_to_zone

logger = logging.getLogger(__name__)


class GCPProvider(Provider):
    """Fetches GCP Compute Engine machine types and normalizes them for cloudfit-core.

    Authentication uses Application Default Credentials (ADC). Set up with:
        gcloud auth application-default login

    Or set GOOGLE_APPLICATION_CREDENTIALS to a service account key path.
    In Cloud Run / GKE, credentials are picked up automatically.

    Args:
        project_id: Your GCP project ID (required for API calls).
        enable_pricing: If True, fetches pricing from the Billing Catalog API.
                        Disable for faster fetches or when billing API is unavailable.

    Example:
        provider = GCPProvider(project_id="my-project")
        instances = provider.fetch_instances(region="us-central1")
        print(instances[0])
    """

    def __init__(
        self,
        project_id: str,
        enable_pricing: bool = True,
    ) -> None:
        self.project_id     = project_id
        self.enable_pricing = enable_pricing
        self._pricing_client = PricingClient() if enable_pricing else None
        self._compute_client = None   # lazy init — avoids import cost if not used

    # ── Provider interface ────────────────────────────────────────────────

    def fetch_instances(self, region: str) -> list[MachineType]:
        """Fetch all available machine types for a GCP region.

        Args:
            region: GCP region (e.g. "us-central1")

        Returns:
            List of normalized MachineType objects.
        """
        client   = self._get_compute_client()
        zone     = region_to_zone(region)
        raw_list = self._list_machine_types(client, zone)

        # Fetch pricing once for the whole region
        price_map: dict[str, float] = {}
        if self._pricing_client:
            try:
                core_prices, ram_prices = self._pricing_client.get_price_map(region)  # type: ignore
            except Exception as exc:
                logger.warning("Pricing fetch failed for %s: %s", region, exc)
                core_prices, ram_prices = {}, {}
        else:
            core_prices, ram_prices = {}, {}

        instances: list[MachineType] = []
        for raw in raw_list:
            try:
                name   = raw.get("name", "")
                vcpu   = raw.get("guestCpus", 0)
                ram_gb = raw.get("memoryMb", 0) / 1024
                price  = reconstruct_price(name, vcpu, ram_gb, core_prices, ram_prices)
                mt     = normalize_machine_type(raw, region=region, price_hr=price)
                instances.append(mt)
            except Exception as exc:
                logger.debug("Skipped machine type %s: %s", raw.get("name"), exc)

        logger.info("Fetched %d machine types for region %s", len(instances), region)
        return instances

    def fetch_instances_all_regions(
        self,
        regions: list[str] | None = None,
    ) -> list[MachineType]:
        """Fetch machine types across all (or specified) GCP regions.

        Args:
            regions: List of region strings. Defaults to all known GCP regions.

        Returns:
            Combined list of MachineType objects, deduplicated by (id, region).
        """
        target_regions = regions or GCP_REGIONS
        all_instances: list[MachineType] = []

        for region in target_regions:
            try:
                instances = self.fetch_instances(region)
                all_instances.extend(instances)
            except Exception as exc:
                logger.warning("Failed to fetch region %s: %s", region, exc)

        logger.info(
            "Total: %d machine types across %d regions",
            len(all_instances), len(target_regions),
        )
        return all_instances

    def get_pricing(self, instance_id: str, region: str) -> float:
        """Return on-demand price/hr for a specific instance in a region.

        Args:
            instance_id: Machine type name (e.g. "n2-standard-32")
            region:      GCP region

        Returns:
            Price per hour in USD. Returns 0.0 if pricing unavailable.
        """
        if not self._pricing_client:
            return 0.0
        try:
            core_prices, ram_prices = self._pricing_client.get_price_map(region)  # type: ignore
            # We need vcpu + ram to reconstruct — fetch from compute API
            raw = self._get_machine_type_raw(instance_id, region)
            if not raw:
                return 0.0
            vcpu   = raw.get("guestCpus", 0)
            ram_gb = raw.get("memoryMb", 0) / 1024
            return reconstruct_price(instance_id, vcpu, ram_gb, core_prices, ram_prices)
        except Exception as exc:
            logger.warning("Pricing lookup failed for %s/%s: %s", instance_id, region, exc)
            return 0.0

    def get_availability(self, instance_id: str, region: str) -> float:
        """Return availability score 0.0–1.0 based on deprecation state.

        Args:
            instance_id: Machine type name
            region:      GCP region

        Returns:
            1.0 = active, 0.4 = deprecated, 0.0 = tombstoned/deleted.
        """
        raw = self._get_machine_type_raw(instance_id, region)
        if not raw:
            return 0.0

        dep   = raw.get("deprecated") or {}
        state = dep.get("state", "ACTIVE")
        return {"ACTIVE": 1.0, "DEPRECATED": 0.4, "OBSOLETE": 0.0, "DELETED": 0.0}.get(
            state, 1.0
        )

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_compute_client(self):
        """Lazy-initialize the Compute Engine client."""
        if self._compute_client is None:
            try:
                from google.cloud import compute_v1
                self._compute_client = compute_v1.MachineTypesClient()
            except ImportError as exc:
                raise ImportError(
                    "google-cloud-compute is required. "
                    "Install with: pip install cloudfit-provider-gcp"
                ) from exc
        return self._compute_client

    def _list_machine_types(self, client, zone: str) -> Iterator[dict]:
        """List all machine types in a zone, returning raw dicts."""
        from google.cloud import compute_v1

        request = compute_v1.ListMachineTypesRequest(
            project=self.project_id,
            zone=zone,
        )
        page_result = client.list(request=request)
        for mt in page_result:
            yield type(mt).to_dict(mt)

    def _get_machine_type_raw(
        self, instance_id: str, region: str
    ) -> dict | None:
        """Fetch a single machine type by name."""
        from google.cloud import compute_v1

        client = self._get_compute_client()
        zone   = region_to_zone(region)
        try:
            request = compute_v1.GetMachineTypeRequest(
                project=self.project_id,
                zone=zone,
                machine_type=instance_id,
            )
            mt = client.get(request=request)
            return type(mt).to_dict(mt)
        except Exception:
            return None
