import os
import uuid

import streamlit as st


def configure_secrets() -> None:
    """Expose Streamlit Cloud secrets to the existing backend configuration."""
    for key in (
        "DATABASE_URL",
        "GROQ_API_KEY",
        "TAVILY_API_KEY",
        "AVIATIONSTACK_API_KEY",
        "DEFAULT_ORIGIN_IATA",
    ):
        if os.getenv(key):
            continue
        try:
            value = st.secrets.get(key)
        except Exception:
            value = None
        if value:
            os.environ[key] = str(value)


configure_secrets()

from backend import run_travel_agent
from s3_simulator import (
    get_bucket_structure,
    get_trip,
    get_trip_storage_analytics,
    list_saved_trips,
)


st.set_page_config(
    page_title="TripMate AI",
    page_icon="✈️",
    layout="wide",
)


def display_result(result: dict) -> None:
    st.success(f"Trip saved as `{result['trip_id']}` (version {result['version']}).")
    if str(result["answer"]).startswith("Demo AI response generated"):
        st.warning(
            "Groq rejected the configured API key, so this is a demo response. "
            "Update `GROQ_API_KEY` in Streamlit Secrets for AI-generated planning."
        )
    st.markdown(result["answer"])

    with st.expander("Flight results"):
        st.markdown(str(result["flight_results"]))
    with st.expander("Hotel results"):
        st.markdown(str(result["hotel_results"]))
    with st.expander("Destination highlights"):
        st.markdown(str(result["places_results"]))
    with st.expander("Generated itinerary"):
        st.markdown(str(result["itinerary"]))

    display_s3_details(result["trip_id"])


def display_s3_details(trip_id: str) -> None:
    """Render the S3 simulator records created for the selected trip."""
    st.subheader("🪣 S3 bucket storage")
    st.caption("This project simulates an S3 bucket using versioned JSON objects on disk.")

    try:
        trip = get_trip(trip_id)
        analytics = get_trip_storage_analytics()
        bucket = get_bucket_structure()
    except Exception as exc:
        st.error(f"Unable to load S3 storage details: {exc}")
        return

    if not trip.get("exists"):
        st.warning(f"No S3 record was found for `{trip_id}`.")
        return

    metric_columns = st.columns(5)
    metric_columns[0].metric("Bucket", bucket.get("bucket", "-"))
    metric_columns[1].metric("Trip prefix", trip_id)
    metric_columns[2].metric("Current version", f"v{trip.get('current_version', 1)}")
    metric_columns[3].metric("Stored objects", len(trip.get("objects", [])))
    metric_columns[4].metric("Storage class", trip.get("storage_class", "STANDARD"))

    st.markdown("**Object listing for this trip**")
    object_rows = [
        {
            "Object key": f"{trip_id}/{item['key']}",
            "Version": f"v{item['version']}",
            "Size (bytes)": item["size"],
            "Last modified": item["last_modified"],
        }
        for item in trip.get("objects", [])
    ]
    if object_rows:
        st.dataframe(object_rows, use_container_width=True, hide_index=True)
    else:
        st.info("This trip has no JSON objects in the bucket.")

    versions = trip.get("versions", [])
    st.write(f"**Version history:** {', '.join(f'v{version}' for version in versions) or 'None'}")

    with st.expander("Bucket-wide storage analytics", expanded=True):
        analytics_columns = st.columns(4)
        analytics_columns[0].metric("Saved trips", analytics.get("saved_trips", 0))
        analytics_columns[1].metric("Total objects", analytics.get("total_objects", 0))
        analytics_columns[2].metric("Total versions", analytics.get("total_versions", 0))
        analytics_columns[3].metric("Storage used", analytics.get("storage_used", "0 B"))
        st.write(f"**Bucket:** `{analytics.get('bucket_name', bucket.get('bucket', '-'))}`")
        st.write(f"**Most recent trip:** `{analytics.get('most_recent_trip', '-')}`")
        st.write(f"**Largest stored trip:** `{analytics.get('largest_trip', '-')}`")

        all_object_rows = [
            {
                "Trip ID": item["trip_id"],
                "Object key": item["key"],
                "Size (bytes)": item["size"],
            }
            for item in bucket.get("objects", [])
        ]
        if all_object_rows:
            st.markdown("**All bucket objects**")
            st.dataframe(all_object_rows, use_container_width=True, hide_index=True)


st.title("✈️ TripMate AI")
st.caption("Multi-agent travel planning with flights, hotels, highlights, and an itinerary.")

if "thread_id" not in st.session_state:
    st.session_state.thread_id = f"user_{uuid.uuid4().hex}"

with st.form("travel_request"):
    user_message = st.text_area(
        "What trip would you like to plan?",
        placeholder="Plan a 7-day trip to Japan from Bangladesh for two people under 200,000 BDT.",
        height=120,
    )
    submitted = st.form_submit_button("Plan my trip", type="primary")

if submitted:
    if not user_message.strip():
        st.warning("Please describe your trip before submitting.")
    else:
        with st.spinner("Researching flights, hotels, attractions, and your itinerary..."):
            try:
                result = run_travel_agent(
                    user_input=user_message.strip(),
                    thread_id=st.session_state.thread_id,
                )
            except Exception as exc:
                st.error(f"Unable to plan this trip: {exc}")
            else:
                st.session_state.latest_result = result

if "latest_result" in st.session_state:
    display_result(st.session_state.latest_result)

with st.sidebar:
    st.header("Saved trips")
    try:
        saved_trips = list_saved_trips()
    except Exception as exc:
        st.warning(f"Saved trips are unavailable: {exc}")
        saved_trips = []

    if not saved_trips:
        st.caption("No saved trips yet.")
    else:
        st.caption("Select a trip to inspect its S3 objects and versions.")
        for trip in saved_trips[:20]:
            label = f"{trip.get('destination', 'Unspecified')} · {trip.get('trip_id', '')}"
            if st.button(label, key=f"saved-{trip.get('trip_id')}"):
                st.session_state.latest_result = {
                    "trip_id": trip.get("trip_id", ""),
                    "version": trip.get("current_version", 1),
                    "answer": trip.get("summary", {}).get("answer", ""),
                    "flight_results": "",
                    "hotel_results": "",
                    "places_results": "",
                    "itinerary": "",
                }
                st.rerun()
