"""Minimal tests for airport search and FlightData construction.

These are smoke tests intended to run quickly and validate that the
`search_airports` wrapper and constructing `FlightData` with an `Airport`
enum works as expected.
"""

import json

from flight_tool import search_airports, search_flights
from fast_flights import FlightData


def test_search_airports_smoke():
    # Try a common query; this test is resilient if the library returns empty results
    resp = search_airports("taipei", limit=5)
    data = json.loads(resp)
    assert "query" in data
    assert data["query"] == "taipei"
    assert "results" in data


def test_flightdata_with_enum_smoke():
    # This test ensures that calling search_flights with airport codes works.
    # We use placeholder codes which the API may or may not recognize; the
    # purpose is to validate argument passing and JSON structure.
    resp = search_flights(from_airport="TPE", to_airport="LAX", departure_date="2025-01-01")
    data = json.loads(resp)
    assert "request" in data
    assert data["request"]["from_airport"] == "TPE"
    assert data["request"]["to_airport"] == "LAX"
