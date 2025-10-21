"""Fast Flights MCP tool

This MCP server exposes tools to search flights and summarize results using the fast-flights API.
"""

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Union
from datetime import date, datetime

from fastmcp import FastMCP
from fast_flights import (
    FlightData,
    Passengers,
    Result,
    get_flights,
    search_airport as ff_search_airport,
    Airport,
)


mcp = FastMCP("Flights")
logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), stream=sys.stdout, format='%(levelname)s: %(message)s')

def _get_currency() -> str:
    return os.getenv("FAST_FLIGHTS_CURRENCY", "USD")


def _parse_duration(duration_str: str) -> int:
    """Convert duration string like '14 hr 15 min' to minutes."""
    if not duration_str or duration_str == "None":
        return 0
    
    try:
        # Handle formats like "14 hr 15 min", "2 hr", "45 min"
        total_minutes = 0
        parts = duration_str.lower().split()
        
        for i, part in enumerate(parts):
            if part == "hr" and i > 0:
                try:
                    hours = int(parts[i-1])
                    total_minutes += hours * 60
                except ValueError:
                    pass
            elif part == "min" and i > 0:
                try:
                    minutes = int(parts[i-1])
                    total_minutes += minutes
                except ValueError:
                    pass
        
        return total_minutes
    except Exception:
        return 0


def _result_to_dict(r: Result, effective_currency: str) -> List[Dict[str, Any]]:
    """Convert a Result object to a list of flight dictionaries for JSON serialization."""
    flights = getattr(r, 'flights', [])
    if not flights:
        return [{
            "id": None,
            "airline": None,
            "price": "N/A",
            "price_value": None,
            "currency": effective_currency,
            "duration_minutes": None,
            "stops": None,
            "departure": None,
            "arrival": None,
        }]
    
    # Process all flights, not just the first one
    flight_results = []
    for flight in flights:
        flight_results.append({
            "id": getattr(flight, 'name', None),
            "airline": getattr(flight, 'name', None),
            "price": _format_money(getattr(r, 'current_price', None), effective_currency),
            "price_value": getattr(r, 'current_price', None),
            "currency": effective_currency,
            "duration_minutes": getattr(flight, 'duration', None),
            "stops": getattr(flight, 'stops', None),
            "departure": getattr(flight, 'departure', None),
            "arrival": getattr(flight, 'arrival', None),
            "is_best": getattr(flight, 'is_best', False),
            "delay": getattr(flight, 'delay', None),
        })
    
    return flight_results


def _format_money(value: Any, currency: str) -> str:
    try:
        amount = float(value)
    except Exception:
        return str(value)
    return f"{currency} {amount:,.2f}"


def _parse_iso_date(d: str) -> Optional[date]:
    """Parse an ISO date (YYYY-MM-DD) into a date object. Returns None on failure."""
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None


def _date_in_past(d: date) -> bool:
    """Return True if the provided date is before today."""
    try:
        return d < date.today()
    except Exception:
        return False


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def search_airports(query: str, limit: int = 10) -> str:
    """Search for airports by name or code.

    This wraps the fast-flights `search_airports()` API and returns a JSON list of
    matching airports. Each airport is serialized as an object with fields:
    - name: enum member name (e.g. TAIPEI_SONGSHAN_AIRPORT)
    - code: likely the IATA code (if available on the enum `.value`)
    - repr: string representation of the enum

    Example:
        airport = search_airports("taipei")[0]
        # Airport.TAIPEI_SONGSHAN_AIRPORT

    Parameters:
    - query: search string (city name, airport name, or IATA code)
    - limit: max number of results to return
    """
    try:
        # fast_flights exposes `search_airport` (singular) — it may return a list
        results = ff_search_airport(query)
    except Exception as e:
        logger.error("airport search failed: %s", e)
        return json.dumps({"error": str(e)})

    # If the API returned enum members or objects, serialize them simply.
    raw = []
    for a in (results or [])[:limit]:
        # If it's an enum-like Airport, include name and value
        if hasattr(a, "name") or hasattr(a, "value"):
            raw.append({
                "name": getattr(a, "name", None),
                "value": getattr(a, "value", None),
                "repr": str(a),
            })
        else:
            try:
                json.dumps(a)
                raw.append(a)
            except Exception:
                raw.append(str(a))

    return json.dumps(raw)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def search_flights(
    from_airport: str,
    to_airport: str,
    departure_date: str,
    return_date: str | None = None,
    cabin: str | None = None,
    adults: int = 1,
    children: int = 0,
    infants_in_seat: int = 0,
    infants_on_lap: int = 0,
    currency: str | None = None,
    airlines: str | None = None,
    max_stops: int | None = None,
) -> str:
    """Search flights between two cities.

    Required parameters:
    - from_airport, to_airport: IATA codes or city names
    - departure_date: YYYY-MM-DD

    Optional parameters:
    - return_date: YYYY-MM-DD (for round-trip flights)
    - cabin: economy|premium-economy|business|first (defaults to economy)
    - adults: number of adult passengers (defaults to 1)
    - children: number of child passengers (defaults to 0)
    - infants_in_seat: number of infants with seats (defaults to 0)
    - infants_on_lap: number of infants on lap (defaults to 0)
    - currency: 3-letter currency code (defaults to USD)
    - airlines: comma-separated IATA codes or alliances (SKYTEAM, STAR_ALLIANCE, ONEWORLD)
    - max_stops: maximum number of stops (defaults to no limit)

    Returns JSON string with provider response (subset) for later processing.
    """
    effective_currency = currency or _get_currency()
    # Validate dates are ISO format and not in the past
    dep_date_obj = _parse_iso_date(departure_date)
    if dep_date_obj is None:
        return json.dumps({"error": "Invalid departure_date format. Use YYYY-MM-DD", "departure_date": departure_date})
    if _date_in_past(dep_date_obj):
        return json.dumps({"error": "departure_date cannot be in the past", "departure_date": departure_date})

    ret_date_obj = None
    if return_date:
        ret_date_obj = _parse_iso_date(return_date)
        if ret_date_obj is None:
            return json.dumps({"error": "Invalid return_date format. Use YYYY-MM-DD", "return_date": return_date})
        if _date_in_past(ret_date_obj):
            return json.dumps({"error": "return_date cannot be in the past", "return_date": return_date})
        # Ensure return date is not before departure
        if ret_date_obj < dep_date_obj:
            return json.dumps({"error": "return_date cannot be before departure_date", "departure_date": departure_date, "return_date": return_date})
    
    # Build flight data list
    flight_data_kwargs = {
        "date": departure_date,
        "from_airport": from_airport,
        "to_airport": to_airport,
    }
    
    # Add optional parameters
    if airlines:
        # Parse comma-separated airline codes
        airline_list = [airline.strip().upper() for airline in airlines.split(",")]
        flight_data_kwargs["airlines"] = airline_list
    
    if max_stops is not None:
        flight_data_kwargs["max_stops"] = max_stops
    
    flight_data_list = [FlightData(**flight_data_kwargs)]
    
    # Add return flight if specified
    if return_date:
        return_flight_kwargs = flight_data_kwargs.copy()
        return_flight_kwargs.update({
            "date": return_date,
            "from_airport": to_airport,
            "to_airport": from_airport,
        })
        flight_data_list.append(FlightData(**return_flight_kwargs))
        trip_type = "round-trip"
    else:
        trip_type = "one-way"
    
    # Map cabin to seat type
    seat_mapping = {
        "economy": "economy",
        "premium_economy": "premium_economy", 
        "business": "business",
        "first": "first"
    }
    seat_type = seat_mapping.get(cabin, "economy")
    
    # Validate passenger constraints
    total_passengers = adults + children + infants_in_seat + infants_on_lap
    if total_passengers > 9:
        return json.dumps({
            "error": "Total passengers cannot exceed 9",
            "request": {
                "from_airport": from_airport,
                "to_airport": to_airport,
                "departure_date": departure_date,
                "return_date": return_date,
                "cabin": cabin,
                "adults": adults,
                "children": children,
                "infants_in_seat": infants_in_seat,
                "infants_on_lap": infants_on_lap,
                "currency": effective_currency,
                "airlines": airlines,
                "max_stops": max_stops,
            }
        })
    
    if infants_on_lap > adults:
        return json.dumps({
            "error": "Must have at least one adult per infant on lap",
            "request": {
                "from_airport": from_airport,
                "to_airport": to_airport,
                "departure_date": departure_date,
                "return_date": return_date,
                "cabin": cabin,
                "adults": adults,
                "children": children,
                "infants_in_seat": infants_in_seat,
                "infants_on_lap": infants_on_lap,
                "currency": effective_currency,
                "airlines": airlines,
                "max_stops": max_stops,
            }
        })
    
    passengers = Passengers(
        adults=adults,
        children=children,
        infants_in_seat=infants_in_seat,
        infants_on_lap=infants_on_lap
    )
    
    logger.debug(f"Searching flights: {flight_data_list}")
    result: Result = get_flights(
        flight_data=flight_data_list,
        trip=trip_type,
        seat=seat_type,
        passengers=passengers,
        fetch_mode="fallback",
    )

    # Convert to list format for consistency with existing tools
    summary: List[Dict[str, Any]] = _result_to_dict(result, effective_currency)
    return json.dumps({
        "request": {
            "from_airport": from_airport,
            "to_airport": to_airport,
            "departure_date": departure_date,
            "return_date": return_date,
            "cabin": cabin,
            "adults": adults,
            "children": children,
            "infants_in_seat": infants_in_seat,
            "infants_on_lap": infants_on_lap,
            "currency": effective_currency,
            "airlines": airlines,
            "max_stops": max_stops,
        },
        "count": len(summary),
        "summary": summary,
        "raw": summary,
    })

# host can be specified with HOST env variable
# transport can be specified with MCP_TRANSPORT env variable (defaults to streamable-http)
def run_server():
    "Run the MCP server"
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    run_server()


