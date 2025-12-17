from collections import defaultdict

import networkx as nx

import config


class BartNetwork:
    """A object representing the BART network"""

    def __init__(self):
        self.stations = config.STATIONS
        self.lines = config.LINES
        self.station_set = set(self.stations)

        # Build the graphs
        self.graph = self._build_physical_graph()
        self.routing_graph = self._build_routing_graph()

        # segments_by_line is a useful lookup dictionary, so we can ask the question
        # "which segments belong to RED FWD?" and we get all segments involved in the
        # forward direction for the red line
        self.segments_by_line = self._get_segments_by_line()

    def _build_physical_graph(self) -> nx.Graph:
        """Builds a simple undirected graph of the BART physical track.

        The physical graph is just the simple BART map, with stations as nodes, and
        edges as segments. Instead of storing whether a station belongs to multiple
        lines or not, it stores whether the SEGMENT belongs to multiple lines:

        `(MCAR, 19TH, lines=["RED", "YELLOW", "ORANGE"])` implies that the segment from
        Macarthur to 19th St has three possible lines - red, yellow, and orange.
        """
        G = nx.Graph()

        # iterate through all the LINES in config
        for ln, seq in self.lines.items():
            for i in range(len(seq) - 1):
                # pick out the two consecutive stations in this line
                u, v = seq[i], seq[i + 1]

                if G.has_edge(u, v):
                    # if the graph already has this edge, that means this segment
                    # exists on a different line as well – capture that
                    G[u][v]["lines"].add(ln)
                else:
                    # if not, then add this edge and line to the graph
                    G.add_edge(u, v, lines={ln}, weight=1)
        return G

    def _build_routing_graph(self) -> nx.DiGraph:
        """
        Builds a directed graph where nodes are (Station, Line).

        The routing graph represents all the possible travel options. Suppose you
        arrived to Macarthur from Red, that means you are in (MCAR, RED). You could move
        to (MCAR, YELLOW), and then board a yellow line train to your next destination.
        The routing graph calculates that transfer as an additional step.

        Intuitively, the routing graph flattens the structure of graph – the edge labels
        `lines` from the physical graph are flattened into separate nodes in the routing
        graph
        """
        G = nx.DiGraph()

        # 1. Add travel edges (Station A, Red) -> (Station B, Red)
        for ln, seq in self.lines.items():
            for i in range(len(seq) - 1):
                u, v = seq[i], seq[i + 1]
                # Bidirectional travel allowed
                G.add_edge((u, ln), (v, ln), weight=1)
                G.add_edge((v, ln), (u, ln), weight=1)

        # 2. Add transfer edges at the same station
        # Find which lines serve which station
        station_to_lines = defaultdict(set)
        for ln, seq in self.lines.items():
            for s in seq:
                station_to_lines[s].add(ln)

        for s, lines_at_s in station_to_lines.items():
            lines_list = list(lines_at_s)
            for l1 in lines_list:
                for l2 in lines_list:
                    if l1 != l2:
                        # Transfer cost
                        G.add_edge(
                            (s, l1), (s, l2), weight=config.TRANSFER_PENALTY_EDGES
                        )

        return G

    def _get_segments_by_line(self) -> dict[tuple[str, str], list[tuple[str, str]]]:
        """
        Returns a dict: segments[(line, dir)] = [(u,v), (v,w)...]
        Used by the optimization model to know which segments belong to 'RED FWD'.
        """
        segments = {}
        for ln, seq in self.lines.items():
            if ln not in config.MODEL_LINES:
                continue

            # FWD direction (Order defined in config)
            fwd_segs = [(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]
            segments[(ln, "FWD")] = fwd_segs

            # REV direction (Reverse order)
            rev_seq = seq[::-1]
            rev_segs = [(rev_seq[i], rev_seq[i + 1]) for i in range(len(rev_seq) - 1)]
            segments[(ln, "REV")] = rev_segs

        return segments

    def get_all_segments(self) -> list[tuple[str, str]]:
        """Returns a list of all unique directed edges (u,v) in the system."""
        unique_segs = set()
        for segs in self.segments_by_line.values():
            unique_segs.update(segs)
        return list(unique_segs)
