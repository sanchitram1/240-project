import networkx as nx
import pytest

from src.network import Segment
from src.routing import build_path_lookup


# 1. Mock Infrastructure
class MockBartNetwork:
    """A tiny fake network to isolate the routing logic."""

    def __init__(self, routing_graph, stations):
        self.routing_graph = routing_graph
        self.stations = stations
        # The routing logic expects a station_set for filtering, though
        # build_path_lookup mainly uses self.stationsp
        self.station_set = set(stations)


@pytest.fixture
def toy_network():
    """
    Creates a 'T-shaped' network to test direct travel and transfers.

    Structure:
    Line RED:    A <-> B <-> C
    Line BLUE:         B <-> D

    Stations: A, B, C, D
    Transfer Station: B (Passengers must switch RED <-> BLUE to go A->D)
    """
    G = nx.DiGraph()

    # --- 1. Travel Edges (Bidirectional) ---
    # RED Line: A <-> B <-> C
    # Weights are 1.0 for travel
    edges = [
        # (Station, Line) -> (Station, Line)
        (("A", "RED"), ("B", "RED")),
        (("B", "RED"), ("A", "RED")),
        (("B", "RED"), ("C", "RED")),
        (("C", "RED"), ("B", "RED")),
        # BLUE Line: B <-> D
        (("B", "BLUE"), ("D", "BLUE")),
        (("D", "BLUE"), ("B", "BLUE")),
    ]
    for u, v in edges:
        G.add_edge(u, v, weight=1.0)

    # --- 2. Transfer Edges (At Station B) ---
    # Cost = 4.0 (Penalty)
    # Connect (B, RED) <-> (B, BLUE)
    G.add_edge(("B", "RED"), ("B", "BLUE"), weight=4.0)
    G.add_edge(("B", "BLUE"), ("B", "RED"), weight=4.0)

    stations = ["A", "B", "C", "D"]
    return MockBartNetwork(G, stations)


# ------------------------------------------------------------------
# 2. The Tests
# ------------------------------------------------------------------


def test_direct_route(toy_network):
    """Test A -> C (Same Line). Should have no transfers."""
    lookup = build_path_lookup(toy_network)

    # Path: A -> B -> C
    segments = lookup[("A", "C")]
    print(segments)

    assert len(segments) == 2
    assert segments[0] == Segment("A", "B")
    assert segments[1] == Segment("B", "C")


def test_transfer_route(toy_network):
    """Test A -> D (Red to Blue). Must transfer at B."""
    lookup = build_path_lookup(toy_network)

    # Path: A(Red) -> B(Red) --Transfer--> B(Blue) -> D(Blue)
    # The 'Segment' list should only capture physical moves: A->B, B->D
    segments = lookup[("A", "D")]

    assert len(segments) == 2
    assert segments[0] == Segment("A", "B")
    assert segments[1] == Segment("B", "D")
    # Note: The transfer B->B is internal to the routing graph
    # and should NOT appear in the physical segments list.


def test_completeness(toy_network):
    """
    CRITICAL: Ensure that for N stations, we generate exactly
    N*(N-1) paths. Every possible pair must exist.
    """
    lookup = build_path_lookup(toy_network)

    stations = toy_network.stations
    missing_pairs = []

    for origin in stations:
        for dest in stations:
            if origin == dest:
                continue

            if (origin, dest) not in lookup:
                missing_pairs.append(f"{origin}->{dest}")

    assert not missing_pairs, (
        f"Build Path Lookup failed to generate paths for: {missing_pairs}"
    )


def test_impossible_route():
    """Test disconnected graph behavior."""
    G = nx.DiGraph()
    G.add_edge(("A", "RED"), ("B", "RED"), weight=1)
    # C is disconnected

    net = MockBartNetwork(G, ["A", "B", "C"])
    lookup = build_path_lookup(net)

    # A->B exists
    assert ("A", "B") in lookup
    # A->C does NOT exist
    assert ("A", "C") not in lookup
