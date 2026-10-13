# TripMate AI

## Multi-Agent Travel Planning with Versioned S3-Style Storage

TripMate AI is an intelligent travel-planning application that transforms a
natural-language travel request into a practical, structured trip plan. It
combines a LangGraph multi-agent workflow with travel research tools, an
LLM-powered planning layer, and an S3-style storage simulator for organizing
trip results as versioned JSON objects.

The application is designed as a demonstration of how specialized AI agents
can collaborate to complete a real-world planning task while preserving the
result as an auditable, versioned data record.

## Key Capabilities

- **Flight research** using AviationStack.
- **Hotel and travel research** using Tavily.
- **Destination discovery** with attraction and local-experience suggestions.
- **AI itinerary generation** based on the request, research results, and
  budget requirements.
- **Multi-agent orchestration** using LangGraph and LangChain.
- **Versioned trip storage** using an S3-style local storage simulator.
- **Trip object management** for summaries, flights, hotels, places, and
  itineraries.
- **Storage analytics** including object counts, version counts, storage
  usage, destination breakdowns, and recent-trip information.
- **FastAPI interface** with a browser-based frontend.
- **Streamlit interface** with an interactive travel-planning and storage
  dashboard.
- **PostgreSQL-backed conversation checkpoints**, with an in-memory fallback
  when PostgreSQL is not configured.
- **Demo-mode responses** when an LLM provider is unavailable or its API key is
  rejected.

## How It Works

TripMate AI processes each request through a sequential LangGraph workflow:

```text
User Request
     |
     v
Flight Research Agent
     |
     v
Hotel Research Agent
     |
     v
Destination Highlights Agent
     |
     v
Itinerary Planning Agent
     |
     v
Final Response Agent
     |
     v
Versioned Trip Storage
```

Each agent contributes a focused part of the final answer. The completed
result is then stored as a trip record with a unique trip ID and version
number.

## S3-Style Storage Model

The project includes a local S3 simulator that represents a bucket using the
following structure:

```text
storage/
└── trip-planner-results/
    └── trip-<id>/
        ├── metadata.json
        ├── flight-results.json
        ├── hotel-results.json
        ├── places-results.json
        ├── final-itinerary.json
        ├── trip-summary.json
        └── versions/
            ├── v1/
            │   ├── flight-results.json
            │   ├── hotel-results.json
            │   ├── places-results.json
            │   ├── final-itinerary.json
            │   └── trip-summary.json
            └── v2/
                └── ...
```

For every saved trip, the storage layer records:

- Bucket name and trip prefix.
- Current version and version history.
- Storage class.
- Object keys and file sizes.
- Creation and modification timestamps.
- Trip metadata and source request.
- Bucket-wide storage analytics.

The Streamlit interface exposes these records through an S3 storage dashboard,
including object listings, version history, storage metrics, and bucket-wide
analytics.

## Technology Stack

- **Language:** Python 3.10+
- **Workflow orchestration:** LangGraph
- **LLM framework:** LangChain
- **LLM provider:** Groq
- **Travel research:** Tavily
- **Flight data:** AviationStack
- **API framework:** FastAPI
- **Interactive UI:** Streamlit
- **Web frontend:** Jinja2, HTML, CSS, and JavaScript
- **Conversation persistence:** PostgreSQL with LangGraph checkpoints
- **Local object storage simulation:** Python filesystem-based S3 simulator

## Project Structure

```text
.
├── app.py                 # FastAPI application and REST endpoints
├── streamlit_app.py       # Streamlit user interface and storage dashboard
├── backend.py             # LangGraph workflow and travel agents
├── s3_simulator.py        # Versioned S3-style storage implementation
├── requirements.txt       # Python dependencies
├── tools/
│   ├── flight_tool.py     # Flight search and airport resolution
│   └── tavily_tool.py     # Hotel and destination research
├── templates/
│   └── index.html         # FastAPI web interface
├── static/
│   ├── script.js          # Browser UI behavior
│   └── style.css          # Browser UI styling
├── test_s3_storage.py     # Storage behavior tests
├── Dockerfile             # Container configuration
├── .env.example           # Environment variable template
└── README.md              # Project documentation
```

## Requirements

Before running the application locally, install:

- Python 3.10 or newer.
- The dependencies listed in `requirements.txt`.
- Optional PostgreSQL access for persistent conversation checkpoints.
- API keys for Groq, Tavily, and AviationStack when live integrations are
  required.

## Configuration

Create a `.env` file in the project root based on `.env.example`:

```env
DATABASE_URL=postgresql://user:password@host:5432/travel_db
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
AVIATIONSTACK_API_KEY=your_aviationstack_api_key
DEFAULT_ORIGIN_IATA=DAC
```

`DATABASE_URL` is optional. When it is not provided, the application uses
in-memory conversation checkpoints. Do not commit `.env` files or API keys to
source control.

## Installation

### Windows

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### macOS and Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Application

### FastAPI application

```bash
python app.py
```

Open the browser interface at:

```text
http://127.0.0.1:8000/
```

### Streamlit application

```bash
streamlit run streamlit_app.py
```

The Streamlit interface provides trip generation, saved-trip browsing, and a
dedicated view of the S3-style bucket contents.

## REST API

The FastAPI application exposes the following endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Check application health |
| `POST` | `/api/travel` | Generate and store a travel plan |
| `GET` | `/api/trips` | List saved trips with optional filters |
| `GET` | `/api/trips/{trip_id}` | Retrieve a saved trip |
| `GET` | `/api/trips/{trip_id}/download` | Download stored trip content |
| `POST` | `/api/trips/{trip_id}/restore` | Restore a selected trip version |
| `DELETE` | `/api/trips/{trip_id}` | Delete a saved trip |
| `GET` | `/api/storage/analytics` | Retrieve storage analytics |
| `GET` | `/api/storage/console` | Retrieve the bucket object listing |

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/travel \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Plan a 3-day trip to Tokyo with a budget of $1200\"}"
```

## Testing

Run the storage test suite with:

```bash
python -m unittest test_s3_storage.py
```

The tests cover trip creation, versioning, object persistence, filtering, and
storage analytics.

## Design Notes

- The application keeps travel responsibilities separated across specialized
  agents instead of placing all logic in one prompt.
- Every generated result is stored in multiple JSON objects so individual
  components can be inspected or downloaded independently.
- Versioned storage makes repeated requests for the same trip auditable.
- External API failures are represented in the generated result where
  possible, while configuration failures are surfaced to the user.
- The local storage simulator is intended for demonstration and development;
  it provides an S3-like data model without requiring an AWS account.

## Contributing

Contributions are welcome. To contribute:

1. Create a feature branch.
2. Make a focused change.
3. Add or update tests when behavior changes.
4. Run the relevant test suite.
5. Open a pull request with a clear description of the change.

## License

See [LICENSE](LICENSE) for the project license.
