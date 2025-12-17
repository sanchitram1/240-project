from collections import defaultdict
from dataclasses import dataclass

import networkx as nx
import plotly.graph_objects as go

import config


# Use dataclasses to represent reused concepts in the code
@dataclass(frozen=True)
class LineDirection:
    line: str
    direction: str  # "FWD" or "REV"


@dataclass(frozen=True)
class Segment:
    u: str
    v: str

    def __repr__(self):
        return f"{self.u}->{self.v}"


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
        Edges store which lines run on them: {'lines': {'RED', 'YELLOW'}}

        E.g.: `(MCAR, 19TH, lines=["RED", "YELLOW", "ORANGE"])` implies that the segment
        from Macarthur to 19th St has three possible lines - red, yellow, and orange.
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
        """Builds a directed graph where nodes are (Station, Line).
        Edges allow travel (cost=1) or transfers (cost=PENALTY).

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

    def _get_segments_by_line(self) -> dict[LineDirection, list[Segment]]:
        """
        Returns a structured lookup of which segments belong to which line/direction.
        """
        segments = {}
        for ln, seq in self.lines.items():
            if ln not in config.MODEL_LINES:
                continue

            # FWD direction
            key_fwd = LineDirection(line=ln, direction="FWD")
            segments[key_fwd] = [
                Segment(seq[i], seq[i + 1]) for i in range(len(seq) - 1)
            ]

            # REV direction
            rev_seq = seq[::-1]
            key_rev = LineDirection(line=ln, direction="REV")
            segments[key_rev] = [
                Segment(rev_seq[i], rev_seq[i + 1]) for i in range(len(rev_seq) - 1)
            ]

        return segments

    def get_all_segments(self) -> list[Segment]:
        """Returns a list of all unique directed edges (u,v) in the system."""
        unique_segs = set()
        for seg_list in self.segments_by_line.values():
            unique_segs.update(seg_list)
        return list(unique_segs)

    # TODO: improve this, ideally in a way that renders it consistently with BART's
    # actual map, but at the very least in a way that leads to viewing the lines without
    # any unnecessary overlaps
    def visualize(self):
        """Interactive Plotly visualization of the network topology."""
        G = self.graph
        # Use spring layout since we don't have lat/lon
        pos = nx.spring_layout(G, seed=42, k=0.5)

        edge_x = []
        edge_y = []
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            line=dict(width=1, color="#888"),
            hoverinfo="none",
            mode="lines",
        )

        node_x = []
        node_y = []
        node_text = []
        for node in G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            # Count how many lines serve this station
            lines = G.edges(node, data="lines")
            # Just a rough heuristic for size/color
            node_text.append(f"{node}")

        node_trace = go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text",
            text=node_text,
            textposition="top center",
            hoverinfo="text",
            marker=dict(showscale=False, color="skyblue", size=15, line_width=2),
        )

        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                title="BART Network Topology",
                # font_size=16,
                showlegend=False,
                hovermode="closest",
                margin=dict(b=20, l=5, r=5, t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            ),
        )
        fig.show()


if __name__ == "__main__":
    bart = BartNetwork()
    bart.visualize()
