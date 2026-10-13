import unittest
from pathlib import Path

from s3_simulator import S3TripStorage, save_trip_result, list_saved_trips, get_trip_storage_analytics


class S3StorageTests(unittest.TestCase):
    def test_create_trip_version_and_retrieve(self):
        storage = S3TripStorage(bucket_root=Path("tmp_test_storage") / "trip-planner-results")
        if storage.bucket_root.exists():
            for file in sorted(storage.bucket_root.rglob("*"), reverse=True):
                if file.is_file():
                    file.unlink()
                elif file.is_dir():
                    file.rmdir()
            storage.bucket_root.rmdir()

        trip_id = "trip-demo-001"
        payload = {
            "trip_id": trip_id,
            "destination": "Japan",
            "source_request": "5-day trip to Japan",
            "answer": "Plan for Tokyo and Kyoto",
            "flight_results": {"route": "DAC to NRT"},
            "hotel_results": {"hotel": "Shibuya Hotel"},
            "places_results": {"spots": ["Tokyo Tower"]},
            "itinerary": "Day 1 Tokyo",
        }

        result = save_trip_result(storage=storage, payload=payload)
        self.assertEqual(result["trip_id"], trip_id)
        self.assertEqual(result["version"], 1)
        self.assertTrue((storage.bucket_root / trip_id / "final-itinerary.json").exists())
        self.assertTrue((storage.bucket_root / trip_id / "versions" / "v1" / "final-itinerary.json").exists())

        trip = storage.get_trip(trip_id)
        self.assertEqual(trip["current_version"], 1)
        self.assertEqual(trip["summary"]["destination"], "Japan")

    def test_storage_analytics_counts_unique_trips_and_versions(self):
        storage = S3TripStorage(bucket_root=Path("tmp_test_storage") / "trip-planner-results")
        if storage.bucket_root.exists():
            for file in sorted(storage.bucket_root.rglob("*"), reverse=True):
                if file.is_file():
                    file.unlink()
                elif file.is_dir():
                    file.rmdir()
            storage.bucket_root.rmdir()

        save_trip_result(storage=storage, payload={"trip_id": "trip-a", "destination": "Japan", "source_request": "Japan trip", "answer": "A", "flight_results": {}, "hotel_results": {}, "places_results": {}, "itinerary": "A"})
        save_trip_result(storage=storage, payload={"trip_id": "trip-a", "destination": "Japan", "source_request": "Japan trip", "answer": "B", "flight_results": {}, "hotel_results": {}, "places_results": {}, "itinerary": "B"})
        save_trip_result(storage=storage, payload={"trip_id": "trip-b", "destination": "Singapore", "source_request": "Singapore trip", "answer": "C", "flight_results": {}, "hotel_results": {}, "places_results": {}, "itinerary": "C"})

        analytics = get_trip_storage_analytics(storage=storage)
        self.assertEqual(analytics["saved_trips"], 2)
        self.assertGreaterEqual(analytics["total_objects"], 6)
        self.assertGreaterEqual(analytics["total_versions"], 3)
        self.assertIn(analytics["largest_trip"], {"trip-a", "trip-b"})

    def test_list_saved_trips_supports_search_filters(self):
        storage = S3TripStorage(bucket_root=Path("tmp_test_storage") / "trip-planner-results")
        if storage.bucket_root.exists():
            for file in sorted(storage.bucket_root.rglob("*"), reverse=True):
                if file.is_file():
                    file.unlink()
                elif file.is_dir():
                    file.rmdir()
            storage.bucket_root.rmdir()

        save_trip_result(storage=storage, payload={"trip_id": "trip-asia", "destination": "Japan", "source_request": "5-day Japan trip", "created_at": "2026-10-03T00:00:00", "answer": "Japan", "flight_results": {}, "hotel_results": {}, "places_results": {}, "itinerary": "Trip"})
        save_trip_result(storage=storage, payload={"trip_id": "trip-europe", "destination": "France", "source_request": "Paris trip", "created_at": "2026-10-04T00:00:00", "answer": "Paris", "flight_results": {}, "hotel_results": {}, "places_results": {}, "itinerary": "Trip"})

        data = list_saved_trips(storage=storage, destination="Japan")
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["trip_id"], "trip-asia")

        filtered = list_saved_trips(storage=storage, version=1)
        self.assertEqual({item["trip_id"] for item in filtered}, {"trip-asia", "trip-europe"})


if __name__ == "__main__":
    unittest.main()
