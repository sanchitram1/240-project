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

    def visualize(self):
        """
        Interactive Plotly visualization of the network topology.
        Uses Kamada-Kawai layout for a cleaner, map-like arrangement.
        """
        G = self.graph

        # Kamada-Kawai layout is better for transport maps (less overlapping)
        pos = nx.kamada_kawai_layout(G, scale=2)

        fig = go.Figure()

        # 1. Draw Edges (One trace per Line Color)
        # We iterate through lines to ensure we get the specific color for each.
        # NOTE: Segments shared by multiple lines will be drawn on top of each other.
        for line_name, stations in self.lines.items():
            color = config.LINE_COLORS.get(line_name, "#888")

            edge_x = []
            edge_y = []

            # Walk the sequence of stations for this line
            for i in range(len(stations) - 1):
                u, v = stations[i], stations[i + 1]
                if u in pos and v in pos:
                    x0, y0 = pos[u]
                    x1, y1 = pos[v]
                    edge_x.extend([x0, x1, None])
                    edge_y.extend([y0, y1, None])

            fig.add_trace(
                go.Scatter(
                    x=edge_x,
                    y=edge_y,
                    line=dict(width=4, color=color),  # Thicker lines
                    hoverinfo="name",
                    name=line_name,
                    mode="lines",
                )
            )

        # 2. Draw Stations (Nodes)
        node_x = []
        node_y = []
        node_text = []

        for node in G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            node_text.append(node)

        node_trace = go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text",
            text=node_text,
            textposition="middle center",  # Text inside the dot often looks cleaner
            textfont=dict(size=10, color="white"),  # White text on black dot
            hoverinfo="text",
            marker=dict(color="black", size=30, line=dict(width=2, color="white")),
            name="stations",
        )

        fig.add_trace(node_trace)

        # 3. Layout Styling
        fig.update_layout(
            title="BART Network Topology",
            showlegend=True,
            hovermode="closest",
            margin=dict(b=20, l=5, r=5, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor="white",
        )

        fig.show()

    def visualize_routing(self):
        """
        Visualizes the State-Space Graph in 3D.

        Concept:
        - X, Y: Physical location of the station.
        - Z: The Line (Red=0, Blue=1, etc.)

        This reveals the "Transfer Elevators" connecting the layers.
        """
        # 1. Get the 2D layout for X, Y coords
        pos_2d = nx.kamada_kawai_layout(self.graph, scale=2)

        # 2. Assign a "Z-height" to each line
        # We only plot the lines we model + OAK
        unique_lines = sorted(list(self.lines.keys()))
        line_to_z = {
            ln: i * 2 for i, ln in enumerate(unique_lines)
        }  # Spaced out by 2 units

        fig = go.Figure()

        # Part A: Draw the "Floors" (Travel Edges)
        for ln in unique_lines:
            z_height = line_to_z[ln]
            color = config.LINE_COLORS.get(ln, "#888")

            edge_x, edge_y, edge_z = [], [], []

            # Actually, let's iterate the Routing Graph directly to be true to the data
            # Filter edges where both nodes are on line 'ln'
            for u_node, v_node in self.routing_graph.edges():
                u_st, u_ln = u_node
                v_st, v_ln = v_node

                # Check if this is a "Travel Edge" on the current line
                if u_ln == ln and v_ln == ln:
                    x0, y0 = pos_2d[u_st]
                    x1, y1 = pos_2d[v_st]
                    edge_x.extend([x0, x1, None])
                    edge_y.extend([y0, y1, None])
                    edge_z.extend([z_height, z_height, None])

            fig.add_trace(
                go.Scatter3d(
                    x=edge_x,
                    y=edge_y,
                    z=edge_z,
                    mode="lines",
                    line=dict(color=color, width=5),
                    name=f"Travel: {ln}",
                    hoverinfo="name",
                )
            )

        # Part B: Draw the "Elevators" (Transfer Edges)
        trans_x, trans_y, trans_z = [], [], []

        for u_node, v_node in self.routing_graph.edges():
            u_st, u_ln = u_node
            v_st, v_ln = v_node

            # It is a transfer if stations are same, but lines are different
            if u_st == v_st and u_ln != v_ln:
                x, y = pos_2d[u_st]
                z1 = line_to_z[u_ln]
                z2 = line_to_z[v_ln]

                trans_x.extend([x, x, None])
                trans_y.extend([y, y, None])
                trans_z.extend([z1, z2, None])

        fig.add_trace(
            go.Scatter3d(
                x=trans_x,
                y=trans_y,
                z=trans_z,
                mode="lines",
                line=dict(color="grey", width=1, dash="dot"),  # Thin dotted lines
                name="Transfer (Penalty)",
                hoverinfo="none",
            )
        )

        # Part C: Draw Nodes (Stations)
        node_x, node_y, node_z, node_text = [], [], [], []
        for st, ln in self.routing_graph.nodes():
            x, y = pos_2d[st]
            z = line_to_z[ln]

            node_x.append(x)
            node_y.append(y)
            node_z.append(z)
            node_text.append(f"{st} ({ln})")

        fig.add_trace(
            go.Scatter3d(
                x=node_x,
                y=node_y,
                z=node_z,
                mode="markers",
                marker=dict(size=4, color="black"),
                text=node_text,
                name="Nodes",
                hoverinfo="text",
            )
        )

        # Layout
        fig.update_layout(
            title="BART State-Space Routing Graph (3D)",
            scene=dict(
                xaxis=dict(visible=False),
                yaxis=dict(visible=False),
                zaxis=dict(
                    title="Line Layer",
                    tickvals=list(line_to_z.values()),
                    ticktext=list(line_to_z.keys()),
                ),
            ),
            margin=dict(l=0, r=0, b=0, t=40),
        )
        fig.show()


if __name__ == "__main__":
    bart = BartNetwork()
    bart.visualize_routing()
