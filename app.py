import json
from pathlib import Path
import traceback

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from backend import run_travel_agent
from s3_simulator import (
    default_storage,
    delete_trip,
    download_trip,
    get_bucket_structure,
    get_trip,
    get_trip_storage_analytics,
    list_saved_trips,
    restore_trip_version,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="TripMate AI",
    description="LangGraph Multi-Agent Travel Planner with FastAPI Frontend",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class TravelRequest(BaseModel):
    message: str
    thread_id: str | None = None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.post("/api/travel")
async def travel_planner(request_data: TravelRequest):
    try:
        user_message = request_data.message.strip()
        if not user_message:
            return JSONResponse(status_code=400, content={"success": False, "error": "Message cannot be empty."})

        result = run_travel_agent(user_input=user_message, thread_id=request_data.thread_id)
        return JSONResponse(
            content={
                "success": True,
                "thread_id": result["thread_id"],
                "trip_id": result["trip_id"],
                "version": result["version"],
                "answer": result["answer"],
                "flight_results": result["flight_results"],
                "hotel_results": result["hotel_results"],
                "places_results": result["places_results"],
                "itinerary": result["itinerary"],
                "llm_calls": result["llm_calls"],
                "storage": result["storage"],
            }
        )
    except Exception as exc:
        print("ERROR:", exc)
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/api/trips")
async def fetch_saved_trips(
    destination: str | None = Query(default=None),
    date: str | None = Query(default=None),
    version: int | None = Query(default=None),
    q: str | None = Query(default=None, alias="q"),
):
    trips = list_saved_trips(destination=destination, date=date, version=version, query=q)
    return {"success": True, "trips": trips}


@app.get("/api/trips/{trip_id}")
async def fetch_trip_detail(trip_id: str):
    trip_data = get_trip(trip_id)
    return {"success": True, "trip": trip_data}


@app.get("/api/trips/{trip_id}/download")
async def download_trip_result(trip_id: str, version: int | None = Query(default=None), output: str = Query(default="json")):
    payload = download_trip(trip_id, version=version, output=output)
    if output == "itinerary":
        itinerary = payload.get("content", {})
        if isinstance(itinerary, dict):
            text = itinerary.get("final_itinerary", itinerary)
        else:
            text = itinerary
        content = json.dumps(text, indent=2, ensure_ascii=False) if isinstance(text, dict) else str(text)
        return PlainTextResponse(content=content, media_type="application/json")
    return JSONResponse({"success": True, "content": payload.get("content", {})})


@app.post("/api/trips/{trip_id}/restore")
async def restore_trip(trip_id: str, request: dict | None = None):
    version = 1
    if request:
        version = int(request.get("version", 1))
    result = restore_trip_version(trip_id, version)
    return {"success": True, "result": result}


@app.delete("/api/trips/{trip_id}")
async def delete_saved_trip(trip_id: str):
    deleted = delete_trip(trip_id)
    return {"success": True, "deleted": deleted, "trip_id": trip_id}


@app.get("/api/storage/analytics")
async def storage_analytics():
    return {"success": True, "analytics": get_trip_storage_analytics()}


@app.get("/api/storage/console")
async def storage_console():
    return {"success": True, "bucket": get_bucket_structure()}


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "AI Travel Planner API is running"}


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
