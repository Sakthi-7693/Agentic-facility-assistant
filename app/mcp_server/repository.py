from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from app.config import FACILITY_DB_PATH


def _key(text: str) -> str:
    """Normalise so 'AHU-02', 'ahu 02' and 'ahu_02' all match."""
    return "".join(ch for ch in str(text).lower() if ch.isalnum())


class FacilityRepository:
    def __init__(self, db_path=FACILITY_DB_PATH) -> None:
        self._lock = threading.Lock()
        with open(db_path, "r", encoding="utf-8") as handle:
            self._db: dict[str, Any] = json.load(handle)

    def _match(self, collection: str, identifier: str) -> dict[str, Any] | None:
        """Exact match on id/name/alias, then a looser 'contains' match.

        Speech-to-text gives us "chiller one", not "CH-01", so the lookup has to
        be forgiving.
        """
        wanted = _key(identifier)
        for record in self._db[collection]:
            names = [record["id"], record["name"], *record.get("aliases", [])]
            if any(_key(n) == wanted for n in names):
                return record
        for record in self._db[collection]:
            if wanted and wanted in _key(record["name"]):
                return record
        return None

    def find_asset(self, identifier: str) -> dict[str, Any] | None:
        return self._match("assets", identifier)

    def find_building(self, identifier: str) -> dict[str, Any] | None:
        return self._match("buildings", identifier)

    def find_zone(self, building_id: str | None, floor: int | None) -> dict[str, Any] | None:
        for zone in self._db["zones"]:
            if building_id and zone["building_id"] != building_id:
                continue
            if floor is not None and zone["floor"] != floor:
                continue
            return zone
        return None

    def find_zone_by_id(self, identifier: str) -> dict[str, Any] | None:
        """Look a zone up by its ID. Agents sometimes pass a zone where an
        asset is expected, and a zone has relationships just like an asset."""
        wanted = _key(identifier)
        return next((z for z in self._db["zones"] if _key(z["id"]) == wanted), None)

    def serving_assets(self, zone_id: str) -> list[str]:
        """Which assets serve a given zone."""
        return [
            r["parent"]
            for r in self.relationships()
            if r["child"] == zone_id and r["relation"] == "serves_zone"
        ]

    def assets(self) -> list[dict[str, Any]]:
        return self._db["assets"]

    def buildings(self) -> list[dict[str, Any]]:
        return self._db["buildings"]

    def zones(self) -> list[dict[str, Any]]:
        return self._db["zones"]

    def alerts(self) -> list[dict[str, Any]]:
        return self._db["alerts"]

    def relationships(self) -> list[dict[str, Any]]:
        return self._db["relationships"]

    def service_requests(self) -> list[dict[str, Any]]:
        return self._db["service_requests"]

    def energy(self, building_id: str) -> dict[str, Any] | None:
        return self._db["energy"].get(building_id)

    def sensor_history(self, entity_id: str) -> dict[str, list[float]]:
        history = self._db["sensor_history"].get(entity_id, {})
        return {k: v for k, v in history.items() if not k.startswith("_")}

    # Writes stay in memory - the seed file is never modified, which is what
    # makes the evaluation suite repeatable.
    def add_service_request(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            request["id"] = f"SR-{2041 + len(self._db['service_requests'])}"
            request["created_at"] = datetime.now().isoformat(timespec="seconds")
            request.setdefault("status", "open")
            request.setdefault("notes", [])
            self._db["service_requests"].append(request)
            return request

    def update_service_request(
        self, request_id: str, status: str | None, note: str | None
    ) -> dict[str, Any] | None:
        with self._lock:
            for request in self._db["service_requests"]:
                if _key(request["id"]) != _key(request_id):
                    continue
                if status:
                    request["status"] = status
                if note:
                    request["notes"].append(
                        {"at": datetime.now().isoformat(timespec="seconds"), "note": note}
                    )
                return request
            return None


_repository: FacilityRepository | None = None


def get_repository() -> FacilityRepository:
    global _repository
    if _repository is None:
        _repository = FacilityRepository()
    return _repository
