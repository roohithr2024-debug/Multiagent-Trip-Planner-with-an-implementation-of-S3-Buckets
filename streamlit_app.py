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
from s3_simulator import list_saved_trips


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
