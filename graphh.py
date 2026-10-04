import json
import networkx as nx
from pyvis.network import Network

# ==========================================
# FILE PATHS
# ==========================================

NODES_FILE = "data/graph_nodes.jsonl"

EDGE_FILES = [
    "data/edges_verified.jsonl",
    "data/edges_provisional.jsonl"
]

OUTPUT_FILE = "graph.html"


# ==========================================
# CREATE GRAPH
# ==========================================

G = nx.DiGraph()


# ==========================================
# LOAD NODES
# ==========================================

with open(NODES_FILE, "r", encoding="utf-8") as f:

    for line in f:

        if not line.strip():
            continue

        node = json.loads(line)

        node_id = node["id"]

        G.add_node(
            node_id,
            label=node.get("label", node_id),
            node_type=node.get("type", ""),
            title=str(node)
        )


# ==========================================
# LOAD BOTH EDGE FILES
# ==========================================

for EDGE_FILE in EDGE_FILES:

    print(f"Loading: {EDGE_FILE}")

    with open(EDGE_FILE, "r", encoding="utf-8") as f:

        for line in f:

            if not line.strip():
                continue

            edge = json.loads(line)

            subject = edge["subject"]
            object_ = edge["object"]

            G.add_edge(
                subject,
                object_,
                label=edge.get("predicate", ""),
                title=edge.get("quote", ""),
                predicate=edge.get("predicate", ""),
                evidence_type=edge.get("evidence_type", ""),
                evidence_source=edge.get("source", "")
            )


# ==========================================
# GRAPH INFORMATION
# ==========================================

print()
print("================================")
print("GRAPH LOADED")
print("================================")
print(f"Nodes : {G.number_of_nodes()}")
print(f"Edges : {G.number_of_edges()}")
print("================================")


# ==========================================
# CREATE PYVIS GRAPH
# ==========================================

net = Network(
    height="900px",
    width="100%",
    directed=True,
    bgcolor="#ffffff",
    font_color="#222222"
)

net.from_nx(G)


# ==========================================
# VISUALIZATION SETTINGS
# ==========================================

net.set_options("""
{
    "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",

        "forceAtlas2Based": {
            "gravitationalConstant": -50,
            "centralGravity": 0.01,
            "springLength": 150,
            "springConstant": 0.08,
            "damping": 0.4
        },

        "stabilization": {
            "enabled": true,
            "iterations": 500
        }
    },

    "interaction": {
        "hover": true,
        "navigationButtons": true,
        "keyboard": true,
        "zoomView": true,
        "dragView": true
    },

    "edges": {
        "arrows": {
            "to": {
                "enabled": true
            }
        },

        "smooth": {
            "enabled": true
        }
    },

    "nodes": {
        "shape": "dot",

        "size": 15,

        "font": {
            "size": 14
        }
    }
}
""")


# ==========================================
# SAVE GRAPH
# ==========================================

net.write_html(OUTPUT_FILE)

print()
print(f"Graph saved to:")
print(OUTPUT_FILE)
print()
print("Opening graph...")
