import os
import re
import uuid
import certifi
import logging
from datetime import datetime
from typing import Annotated, TypedDict

from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import operator

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from s3_simulator import save_trip_result
from tools.flight_tool import search_flights
from tools.tavily_tool import tavily_search

logger = logging.getLogger(__name__)

try:
    import psycopg
    from psycopg.rows import dict_row
    from langgraph.checkpoint.postgres import PostgresSaver
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None
    PostgresSaver = None


def get_database_url():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"
    return database_url


class DemoLLM:
    def invoke(self, messages):
        prompt_text = "\n".join(
            getattr(message, "content", str(message)) for message in messages if getattr(message, "content", None)
        )
        compact = " ".join(prompt_text.split())
        if len(compact) > 260:
            compact = compact[:260] + "..."
        return AIMessage(content=f"Demo AI response generated for: {compact}")


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if GROQ_API_KEY:
    llm = ChatGroq(model="openai/gpt-oss-120b", api_key=GROQ_API_KEY)
else:
    llm = DemoLLM()


def invoke_llm(messages):
    global llm
    try:
        return llm.invoke(messages)
    except Exception as exc:
        is_auth_error = getattr(exc, "status_code", None) == 401 or "invalid_api_key" in str(exc)
        if not is_auth_error:
            raise
        logger.warning(
            "GROQ_API_KEY was rejected. Falling back to the built-in demo response. "
            "Replace the Streamlit secret with a valid Groq API key."
        )
        llm = DemoLLM()
        return llm.invoke(messages)


class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    places_results: str
    itinerary: str
    llm_calls: int


def extract_destination_from_query(user_query: str) -> str:
    if not user_query:
        return "Unspecified"
    text = user_query.strip()
    match = re.search(r"\bto\s+([A-Za-z][A-Za-z\s,.-]+?)(?:\s+from\b|\s+including\b|\s+with\b|\s+under\b|$)", text, re.IGNORECASE)
    if match:
        destination = match.group(1).strip(" .,!?")
        if destination:
            return destination.title()

    if "trip to " in text.lower():
        destination = text.lower().split("trip to ", 1)[1]
        destination = re.split(r"\s+(?:from|including|with|under|for|and|in)\b", destination, maxsplit=1)[0]
        return destination.strip(" .,!?").title()

    return "Unspecified"


def flight_agent(state: TravelState):
    query = state["user_query"]
    flight_data = search_flights(query)
    return {
        "flight_results": flight_data,
        "messages": [AIMessage(content="Flight results fetched.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"
    hotel_results = tavily_search(query)
    return {
        "hotel_results": hotel_results,
        "messages": [AIMessage(content="Hotel information fetched.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def places_agent(state: TravelState):
    destination = extract_destination_from_query(state["user_query"])
    query = f"Top attractions and local experiences in {destination}"
    places_results = tavily_search(query)
    return {
        "places_results": places_results,
        "messages": [AIMessage(content="Places recommendations fetched.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def itinerary_agent(state: TravelState):
    prompt = f"""
Create a complete travel itinerary.

User Query:
{state['user_query']}

Flight Results:
{state['flight_results']}

Hotel Results:
{state['hotel_results']}

Places Results:
{state['places_results']}

Make the itinerary practical, budget-aware, and easy to follow.
"""

    response = invoke_llm([
        SystemMessage(content="You are an expert travel planner."),
        HumanMessage(content=prompt),
    ])

    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def final_agent(state: TravelState):
    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Flights:
{state['flight_results']}

Hotels:
{state['hotel_results']}

Places:
{state['places_results']}

Itinerary:
{state['itinerary']}

Format the final answer beautifully using these sections:

1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Destination Highlights
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations

Important:
- Be clear and practical.
- Mention that live flight API may not provide ticket prices if pricing is unavailable.
- Keep the response useful for real travel planning.
"""

    response = invoke_llm([
        SystemMessage(content="You are a professional AI travel booking assistant."),
        HumanMessage(content=final_prompt),
    ])

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


graph = StateGraph(TravelState)
graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("places_agent", places_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "places_agent")
graph.add_edge("places_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)

DATABASE_URL = get_database_url()

if DATABASE_URL and psycopg and PostgresSaver:
    try:
        _conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
        checkpointer = PostgresSaver(_conn)
        checkpointer.setup()
    except psycopg.Error:
        logger.warning(
            "DATABASE_URL is invalid or unavailable. "
            "Using in-memory conversation state instead. "
            "Remove the optional secret or provide a valid PostgreSQL URL."
        )
        checkpointer = MemorySaver()
else:
    checkpointer = MemorySaver()

travel_graph = graph.compile(checkpointer=checkpointer)


def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {"configurable": {"thread_id": thread_id}}
    result = travel_graph.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "places_results": "",
            "itinerary": "",
            "llm_calls": 0,
        },
        config=config,
    )

    final_message = result["messages"][-1]
    final_answer = getattr(final_message, "content", str(final_message))

    trip_id = thread_id if thread_id.startswith("trip-") else f"trip-{thread_id.replace('user_', '').replace('thread_', '')[:12]}"
    if not trip_id.startswith("trip-"):
        trip_id = f"trip-{uuid.uuid4().hex[:8]}"

    trip_payload = {
        "trip_id": trip_id,
        "thread_id": thread_id,
        "destination": extract_destination_from_query(user_input),
        "source_request": user_input,
        "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "answer": final_answer,
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "places_results": result.get("places_results", ""),
        "itinerary": result.get("itinerary", ""),
        "storage_class": "STANDARD",
    }
    saved_trip = save_trip_result(payload=trip_payload)

    return {
        "thread_id": thread_id,
        "trip_id": saved_trip["trip_id"],
        "version": saved_trip["version"],
        "answer": final_answer,
        "flight_results": trip_payload["flight_results"],
        "hotel_results": trip_payload["hotel_results"],
        "places_results": trip_payload["places_results"],
        "itinerary": trip_payload["itinerary"],
        "llm_calls": result.get("llm_calls", 0),
        "storage": saved_trip,
    }
