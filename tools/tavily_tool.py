import os

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")
client = TavilyClient(api_key=api_key) if api_key else None


def _fallback_tavily_search(query: str):
    destination = query.replace("Best hotels for ", "").replace("Top attractions and local experiences in ", "").strip()
    return (
        f"Demo travel insight for {destination or 'your destination'}\n\n"
        "1. **Stay near major transport hubs**\n"
        "   Good connectivity, easy airport access, and walkable local neighborhoods.\n\n"
        "2. **Choose a central district**\n"
        "   Base your stay near local culture, dining, and booking convenience.\n\n"
        "3. **Plan a balanced day split**\n"
        "   Include one highlight attraction, one local food stop, and one flexible activity block."
    )


def tavily_search(query):
    if client is None:
        return _fallback_tavily_search(query)

    try:
        response = client.search(query=query, max_results=5)
        results = []
        for i, r in enumerate(response.get("results", []), 1):
            title = r.get("title", "Unknown")
            url = r.get("url", "")
            snippet = r.get("content", "").strip()
            if len(snippet) > 300:
                snippet = snippet[:300].rsplit(" ", 1)[0] + "..."
            results.append(f"{i}. **{title}**\n   {url}\n   {snippet}")
        if not results:
            return _fallback_tavily_search(query)
        return "\n\n".join(results)
    except Exception:
        return _fallback_tavily_search(query)