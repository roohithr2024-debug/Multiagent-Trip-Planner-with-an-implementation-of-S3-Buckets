import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_BUCKET_NAME = "trip-planner-results"
STANDARD_STORAGE_CLASS = "STANDARD"


def _normalize_trip_id(trip_id: Optional[str]) -> str:
    if not trip_id:
        import uuid
        return f"trip-{uuid.uuid4().hex[:8]}"

    clean = str(trip_id).strip()
    if not clean:
        import uuid
        return f"trip-{uuid.uuid4().hex[:8]}"

    return clean if clean.startswith("trip-") else f"trip-{clean}"


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item) for item in value]
    return str(value)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.2f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


class S3TripStorage:
    def __init__(self, bucket_root: Optional[Path | str] = None):
        if bucket_root is None:
            base_dir = Path(__file__).resolve().parent
            bucket_root = base_dir / "storage" / DEFAULT_BUCKET_NAME
        self.bucket_root = Path(bucket_root)
        self.bucket_root.mkdir(parents=True, exist_ok=True)

    def _trip_dir(self, trip_id: str) -> Path:
        return self.bucket_root / trip_id

    def _version_dir(self, trip_id: str, version: int) -> Path:
        return self.bucket_root / trip_id / "versions" / f"v{version}"

    def _list_version_dirs(self, trip_dir: Path) -> List[Path]:
        version_root = trip_dir / "versions"
        if not version_root.exists():
            return []
        return sorted(
            [path for path in version_root.iterdir() if path.is_dir() and path.name.startswith("v")],
            key=lambda p: int(p.name.replace("v", ""))
        )

    def _read_json_file(self, path: Path) -> Any:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fp:
            try:
                return json.load(fp)
            except json.JSONDecodeError:
                return {}

    def _write_json_file(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False)
            fp.write("\n")

    def _build_metadata_record(self, trip_id: str, object_key: str, version: int, object_type: str, payload: Any, storage_class: str) -> Dict[str, Any]:
        serialized = json.dumps(_to_json_safe(payload), ensure_ascii=False)
        size = len(serialized.encode("utf-8"))
        now = _iso_now()
        return {
            "object_key": object_key,
            "trip_id": trip_id,
            "object_type": object_type,
            "content_type": "application/json",
            "size_bytes": size,
            "size_label": _format_size(size),
            "created_at": now,
            "last_modified": now,
            "version": version,
            "storage_class": storage_class,
            "bucket": self.bucket_root.name,
        }

    def _get_trip_summary(self, trip_id: str, trip_dir: Path, metadata: Dict[str, Any], current_version: int) -> Dict[str, Any]:
        destination = metadata.get("destination") or metadata.get("summary", {}).get("destination") or "Unspecified"
        created_at = metadata.get("created_at") or metadata.get("summary", {}).get("created_at") or _iso_now()
        size_bytes = 0
        for item in trip_dir.rglob("*.json"):
            if item.is_file():
                try:
                    size_bytes += item.stat().st_size
                except OSError:
                    pass
        return {
            "trip_id": trip_id,
            "destination": destination,
            "created_at": created_at,
            "current_version": current_version,
            "total_versions": len(self._list_version_dirs(trip_dir)),
            "storage_used": _format_size(size_bytes),
            "storage_class": metadata.get("storage_class", STANDARD_STORAGE_CLASS),
            "summary": metadata.get("summary", {}),
            "version_history": metadata.get("version_history", []),
        }

    def save_trip_result(self, payload: Dict[str, Any], storage_class: str = STANDARD_STORAGE_CLASS) -> Dict[str, Any]:
        trip_id = _normalize_trip_id(payload.get("trip_id") or payload.get("thread_id"))
        trip_dir = self._trip_dir(trip_id)
        trip_dir.mkdir(parents=True, exist_ok=True)

        version_count = len(self._list_version_dirs(trip_dir))
        new_version = version_count + 1
        version_dir = self._version_dir(trip_id, new_version)
        version_dir.mkdir(parents=True, exist_ok=True)

        created_at = payload.get("created_at") or _iso_now()
        destination = payload.get("destination") or self._extract_destination(payload.get("source_request") or payload.get("answer") or "")
        summary_payload = {
            "trip_id": trip_id,
            "destination": destination,
            "source_request": payload.get("source_request") or "",
            "created_at": created_at,
            "updated_at": _iso_now(),
            "answer": payload.get("answer") or "",
            "trip_status": "stored",
            "storage_class": storage_class,
            "version": new_version,
        }

        object_map = {
            "flight-results.json": payload.get("flight_results", {}),
            "hotel-results.json": payload.get("hotel_results", {}),
            "places-results.json": payload.get("places_results", {}),
            "final-itinerary.json": payload.get("itinerary", payload.get("answer", {})),
            "trip-summary.json": summary_payload,
        }

        object_records = []
        for object_key, content in object_map.items():
            file_path = version_dir / object_key
            safe_content = _to_json_safe(content)
            self._write_json_file(file_path, safe_content)
            object_records.append(
                self._build_metadata_record(
                    trip_id=trip_id,
                    object_key=object_key,
                    version=new_version,
                    object_type=object_key,
                    payload=safe_content,
                    storage_class=storage_class,
                )
            )

        current_metadata = {
            "trip_id": trip_id,
            "bucket": self.bucket_root.name,
            "destination": destination,
            "created_at": created_at,
            "updated_at": _iso_now(),
            "current_version": new_version,
            "storage_class": storage_class,
            "summary": summary_payload,
            "version_history": [
                {"version": item.name.replace("v", ""), "path": str(item)} for item in self._list_version_dirs(trip_dir)
            ],
            "objects": object_records,
        }
        self._write_json_file(trip_dir / "metadata.json", current_metadata)

        for object_key, content in object_map.items():
            current_path = trip_dir / object_key
            self._write_json_file(current_path, _to_json_safe(content))

        current_metadata["version_history"] = [
            {"version": item.name.replace("v", ""), "path": str(item)} for item in self._list_version_dirs(trip_dir)
        ]
        self._write_json_file(trip_dir / "metadata.json", current_metadata)

        return {
            "trip_id": trip_id,
            "version": new_version,
            "current_version": new_version,
            "storage_class": storage_class,
            "destination": destination,
            "created_at": created_at,
            "bucket": self.bucket_root.name,
        }

    def _extract_destination(self, text: str) -> str:
        if not text:
            return "Unspecified"
        cleaned = str(text).strip()
        if " to " in cleaned.lower():
            candidate = cleaned.split(" to ", 1)[1]
            candidate = candidate.split(" from ", 1)[0].split(" including ", 1)[0]
            candidate = candidate.strip(" .!?\n")
            if candidate:
                return candidate.title()
        if "trip to " in cleaned.lower():
            candidate = cleaned.lower().split("trip to ", 1)[1]
            return candidate.strip(" .!?\n").title()
        return "Unspecified"

    def get_trip(self, trip_id: str, version: Optional[int] = None) -> Dict[str, Any]:
        trip_dir = self._trip_dir(trip_id)
        if not trip_dir.exists():
            return {"trip_id": trip_id, "exists": False}

        metadata = self._read_json_file(trip_dir / "metadata.json")
        versions = self._list_version_dirs(trip_dir)
        current_version = version or int(metadata.get("current_version") or (len(versions) if versions else 1))
        version_dir = self._version_dir(trip_id, current_version)

        object_listing = []
        for path in sorted(version_dir.iterdir()):
            if path.is_file() and path.suffix == ".json":
                object_listing.append({
                    "name": path.name,
                    "key": path.name,
                    "version": current_version,
                    "size": path.stat().st_size,
                    "last_modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                })

        summary = metadata.get("summary", {})
        return {
            "trip_id": trip_id,
            "exists": True,
            "current_version": current_version,
            "versions": [int(item.name.replace("v", "")) for item in versions],
            "source_request": summary.get("source_request") or "",
            "destination": summary.get("destination") or metadata.get("destination") or "Unspecified",
            "summary": summary,
            "objects": object_listing,
            "raw_data": {
                "flight_results": self._read_json_file(version_dir / "flight-results.json"),
                "hotel_results": self._read_json_file(version_dir / "hotel-results.json"),
                "places_results": self._read_json_file(version_dir / "places-results.json"),
                "final_itinerary": self._read_json_file(version_dir / "final-itinerary.json"),
                "trip_summary": self._read_json_file(version_dir / "trip-summary.json"),
            },
            "storage_class": metadata.get("storage_class", STANDARD_STORAGE_CLASS),
        }

    def list_trips(self, destination: Optional[str] = None, date: Optional[str] = None, version: Optional[int] = None, query: Optional[str] = None) -> List[Dict[str, Any]]:
        trips: List[Dict[str, Any]] = []
        for item in sorted(self.bucket_root.iterdir()):
            if not item.is_dir():
                continue
            metadata = self._read_json_file(item / "metadata.json")
            if not metadata:
                continue
            summary = metadata.get("summary", {})
            trip_destination = (summary.get("destination") or metadata.get("destination") or "").lower()
            created_at = summary.get("created_at") or metadata.get("created_at") or ""
            trip_id = metadata.get("trip_id") or item.name
            current_version = metadata.get("current_version") or max([int(path.name.replace("v", "")) for path in self._list_version_dirs(item)], default=1)

            if destination and destination.lower() not in trip_destination:
                continue
            if date and date not in str(created_at):
                continue
            if version is not None and int(current_version) != int(version):
                continue
            if query:
                q = query.lower()
                if q not in trip_id.lower() and q not in trip_destination and q not in str(created_at).lower():
                    continue

            trips.append({
                "trip_id": trip_id,
                "destination": summary.get("destination") or metadata.get("destination") or "Unspecified",
                "created_at": created_at,
                "current_version": current_version,
                "storage_class": metadata.get("storage_class", STANDARD_STORAGE_CLASS),
                "summary": summary,
            })
        return sorted(trips, key=lambda trip: trip.get("created_at", ""), reverse=True)

    def restore_version(self, trip_id: str, version: int) -> Dict[str, Any]:
        trip_dir = self._trip_dir(trip_id)
        if not trip_dir.exists():
            raise FileNotFoundError(f"Trip {trip_id} not found")

        version_dir = self._version_dir(trip_id, version)
        if not version_dir.exists():
            raise FileNotFoundError(f"Version v{version} for trip {trip_id} not found")

        for item in sorted(version_dir.iterdir()):
            if item.is_file() and item.suffix == ".json":
                destination_path = trip_dir / item.name
                destination_path.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")

        metadata = self._read_json_file(trip_dir / "metadata.json")
        metadata["current_version"] = version
        metadata["updated_at"] = _iso_now()
        metadata["storage_class"] = metadata.get("storage_class", STANDARD_STORAGE_CLASS)
        self._write_json_file(trip_dir / "metadata.json", metadata)
        return {"trip_id": trip_id, "restored_version": version, "status": "restored"}

    def delete_trip(self, trip_id: str) -> bool:
        trip_dir = self._trip_dir(trip_id)
        if not trip_dir.exists():
            return False
        for child in sorted(trip_dir.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        trip_dir.rmdir()
        return True

    def get_bucket_structure(self) -> Dict[str, Any]:
        objects = []
        for trip_dir in sorted(self.bucket_root.iterdir()):
            if not trip_dir.is_dir():
                continue
            for file_path in sorted(trip_dir.rglob("*.json")):
                if file_path.name == "metadata.json":
                    continue
                relative = file_path.relative_to(self.bucket_root)
                objects.append({
                    "trip_id": trip_dir.name,
                    "key": str(relative).replace("\\", "/"),
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                })
        return {"bucket": self.bucket_root.name, "objects": objects}

    def get_storage_analytics(self) -> Dict[str, Any]:
        trips = []
        total_objects = 0
        total_versions = 0
        total_size = 0
        most_recent_trip = "-"
        latest_time = None
        destination_counts: Dict[str, int] = {}
        version_counts: Dict[str, int] = {}
        trip_sizes: Dict[str, int] = {}
        recent_trips = []

        for trip_dir in sorted(self.bucket_root.iterdir()):
            if not trip_dir.is_dir():
                continue
            metadata = self._read_json_file(trip_dir / "metadata.json")
            if not metadata:
                continue
            trips.append(trip_dir.name)
            versions = self._list_version_dirs(trip_dir)
            total_versions += len(versions)
            version_label = str(len(versions))
            version_counts[version_label] = version_counts.get(version_label, 0) + 1
            trip_size = 0
            for file in trip_dir.rglob("*.json"):
                if file.is_file():
                    total_objects += 1
                    trip_size += file.stat().st_size
                    total_size += file.stat().st_size
            trip_sizes[trip_dir.name] = trip_size
            destination = (
                metadata.get("summary", {}).get("destination")
                or metadata.get("destination")
                or "Unspecified"
            )
            destination_counts[destination] = destination_counts.get(destination, 0) + 1
            created_at = metadata.get("summary", {}).get("created_at") or metadata.get("created_at") or ""
            if created_at:
                if latest_time is None or created_at > latest_time:
                    latest_time = created_at
                    most_recent_trip = trip_dir.name

        largest_trip = "-"
        largest_trip_size = -1
        for trip_dir in sorted(self.bucket_root.iterdir()):
            if not trip_dir.is_dir():
                continue
            trip_size = 0
            for file in trip_dir.rglob("*.json"):
                if file.is_file():
                    trip_size += file.stat().st_size
            if trip_size > largest_trip_size:
                largest_trip_size = trip_size
                largest_trip = trip_dir.name

        for trip_id in sorted(trips, key=lambda item: trip_sizes.get(item, 0), reverse=True):
            metadata = self._read_json_file(self._trip_dir(trip_id) / "metadata.json")
            summary = metadata.get("summary", {})
            recent_trips.append({
                "trip_id": trip_id,
                "destination": summary.get("destination") or metadata.get("destination") or "Unspecified",
                "created_at": summary.get("created_at") or metadata.get("created_at") or "",
                "versions": len(self._list_version_dirs(self._trip_dir(trip_id))),
                "storage_used": _format_size(trip_sizes[trip_id]),
                "storage_used_bytes": trip_sizes[trip_id],
            })

        recent_trips.sort(key=lambda item: item["created_at"], reverse=True)
        return {
            "saved_trips": len(trips),
            "total_objects": max(total_objects, 0),
            "total_versions": total_versions,
            "storage_used": _format_size(total_size),
            "storage_used_bytes": total_size,
            "most_recent_trip": most_recent_trip,
            "largest_trip": largest_trip,
            "bucket_name": self.bucket_root.name,
            "destination_breakdown": [
                {"label": label, "count": count}
                for label, count in sorted(destination_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "version_breakdown": [
                {"label": f"{label} version{'s' if label != '1' else ''}", "count": count}
                for label, count in sorted(version_counts.items(), key=lambda item: int(item[0]))
            ],
            "recent_trips": recent_trips[:6],
        }

    def download_trip(self, trip_id: str, version: Optional[int] = None, output: str = "json") -> Dict[str, Any]:
        trip = self.get_trip(trip_id, version=version)
        if not trip.get("exists"):
            raise FileNotFoundError(f"Trip {trip_id} not found")

        current_version = trip["current_version"]
        version_dir = self._version_dir(trip_id, current_version)

        if output == "itinerary":
            content = self._read_json_file(version_dir / "final-itinerary.json")
            return {"format": "itinerary", "content": content}
        if output == "summary":
            content = self._read_json_file(version_dir / "trip-summary.json")
            return {"format": "summary", "content": content}

        full_data = {
            "trip_id": trip_id,
            "version": current_version,
            "metadata": trip.get("summary", {}),
            "flight_results": self._read_json_file(version_dir / "flight-results.json"),
            "hotel_results": self._read_json_file(version_dir / "hotel-results.json"),
            "places_results": self._read_json_file(version_dir / "places-results.json"),
            "final_itinerary": self._read_json_file(version_dir / "final-itinerary.json"),
            "trip_summary": self._read_json_file(version_dir / "trip-summary.json"),
        }
        return {"format": "json", "content": full_data}


default_storage = S3TripStorage()


def save_trip_result(storage: Optional[S3TripStorage] = None, payload: Optional[Dict[str, Any]] = None, storage_class: str = STANDARD_STORAGE_CLASS) -> Dict[str, Any]:
    target = storage or default_storage
    payload = payload or {}
    return target.save_trip_result(payload=payload, storage_class=storage_class)


def list_saved_trips(storage: Optional[S3TripStorage] = None, destination: Optional[str] = None, date: Optional[str] = None, version: Optional[int] = None, query: Optional[str] = None) -> List[Dict[str, Any]]:
    target = storage or default_storage
    return target.list_trips(destination=destination, date=date, version=version, query=query)


def get_trip_storage_analytics(storage: Optional[S3TripStorage] = None) -> Dict[str, Any]:
    target = storage or default_storage
    return target.get_storage_analytics()


def get_bucket_structure(storage: Optional[S3TripStorage] = None) -> Dict[str, Any]:
    target = storage or default_storage
    return target.get_bucket_structure()


def get_trip(trip_id: str, storage: Optional[S3TripStorage] = None, version: Optional[int] = None) -> Dict[str, Any]:
    target = storage or default_storage
    return target.get_trip(trip_id, version=version)


def restore_trip_version(trip_id: str, version: int, storage: Optional[S3TripStorage] = None) -> Dict[str, Any]:
    target = storage or default_storage
    return target.restore_version(trip_id, version)


def delete_trip(trip_id: str, storage: Optional[S3TripStorage] = None) -> bool:
    target = storage or default_storage
    return target.delete_trip(trip_id)


def download_trip(trip_id: str, storage: Optional[S3TripStorage] = None, version: Optional[int] = None, output: str = "json") -> Dict[str, Any]:
    target = storage or default_storage
    return target.download_trip(trip_id, version=version, output=output)
