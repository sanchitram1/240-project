import networkx as nx
import pytest

import src.config as config
from src.network import BartNetwork


def test_all_stations_are_served():
    """
    Integrity Check 1: The 'Orphan' Test.
    Ensures every station defined in STATIONS is actually assigned to at least one line.
    """
    # 1. Get all stations that are supposedly part of the system
    all_stations = set(config.STATIONS)

    # 2. Get all stations that are actually visited by trains
    served_stations = set()
    for line_name, stops in config.LINES.items():
        served_stations.update(stops)

    # 3. Find stations that exist on the map but have no trains
    orphans = all_stations - served_stations

    assert not orphans, (
        f"The following stations are defined but have NO lines serving them: {orphans}"
    )


def test_lines_use_valid_stations():
    """
    Integrity Check 2: The 'Ghost' Test.
    Ensures every station listed in a Line sequence actually exists in the STATIONS keys.
    Catches typos like 'LAKE' instead of 'LAKM'.
    """
    valid_station_keys = set(config.STATIONS)

    for line_name, stops in config.LINES.items():
        # Check if any stop in this line is NOT in the valid registry
        invalid_stops = set(stops) - valid_station_keys

        assert not invalid_stops, (
            f"Line '{line_name}' contains undefined stations: {invalid_stops}. "
            "Check for typos in config.LINES vs config.STATIONS."
        )


def test_network_connectivity():
    """
    Integrity Check 3: The 'Island' Test.
    Builds the actual graph and checks if the entire system is connected.
    If 12TH and FTVL are disjoint, this will fail.
    """
    # Build the network using your actual class
    bart = BartNetwork()

    # We check the 'Physical' graph (simple) first to ensure track continuity
    G = bart.routing_graph

    # Check 1: Is the graph fully connected? (Can I get from A to B?)
    # Since it's a DiGraph (directed), we check 'weakly_connected'
    # (ignoring direction) to ensure physical track continuity.
    is_connected = nx.is_weakly_connected(G)

    if not is_connected:
        # If not connected, find the separate islands to help debug
        components = list(nx.weakly_connected_components(G))
        assert is_connected, (
            f"The network is broken into {len(components)} disconnected islands! "
            f"Island 1: {list(components[0])[:5]}... "
            f"Island 2: {list(components[1])[:5]}..."
        )


def test_duplicate_stations_in_lines():
    """
    Integrity Check 4: The 'Loop' Test.
    Ensures a station doesn't appear twice in the same line sequence
    (unless we intended to support circular lines, which BART is not).
    """
    for line_name, stops in config.LINES.items():
        if len(stops) != len(set(stops)):
            # Find the duplicate
            from collections import Counter

            counts = Counter(stops)
            dupes = [st for st, count in counts.items() if count > 1]

            pytest.fail(
                f"Line '{line_name}' has duplicate stations (infinite loop?): {dupes}"
            )
