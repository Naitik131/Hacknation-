import json
from pathlib import Path
from pyvis.network import Network


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = BASE_DIR / "nih_graph.html"

NODES_FILE = DATA_DIR / "nih_nodes.jsonl"
EDGES_FILE = DATA_DIR / "nih_edges.jsonl"


# ---------------------------------------------------------
# Load nodes
# ---------------------------------------------------------

nodes = []

with open(NODES_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            nodes.append(json.loads(line))


# ---------------------------------------------------------
# Load edges
# ---------------------------------------------------------

edges = []

with open(EDGES_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            edges.append(json.loads(line))


print("=" * 70)
print("NIH REPORTE​R GRAPH VISUALIZATION")
print("=" * 70)

print(f"Nodes loaded: {len(nodes)}")
print(f"Edges loaded: {len(edges)}")


# ---------------------------------------------------------
# Create PyVis network
# ---------------------------------------------------------

net = Network(
    height="850px",
    width="100%",
    bgcolor="#ffffff",
    font_color="#222222",
    directed=True,
)

net.barnes_hut(
    gravity=-30000,
    central_gravity=0.25,
    spring_length=180,
    spring_strength=0.04,
    damping=0.09,
)


# ---------------------------------------------------------
# Node styling
# ---------------------------------------------------------

node_colors = {
    "study": "#ffcc80",
    "disease": "#ef9a9a",
    "person": "#90caf9",
    "organization": "#a5d6a7",
    "nih_institute": "#ce93d8",
}


for node in nodes:
    node_id = node["id"]
    node_type = node["type"]
    label = node["label"]

    attrs = node.get("attrs", {})

    title_parts = [
        f"<b>{label}</b>",
        f"Type: {node_type}",
    ]

    if attrs:
        for key, value in attrs.items():
            if value is not None and value != "":
                title_parts.append(
                    f"{key}: {value}"
                )

    net.add_node(
        node_id,
        label=label,
        title="<br>".join(title_parts),
        color=node_colors.get(node_type, "#dddddd"),
        shape="dot",
        size=20,
        font={
            "size": 14
        },
    )


# ---------------------------------------------------------
# Edge styling
# ---------------------------------------------------------

edge_colors = {
    "studied_in": "#555555",
    "led_by": "#1976d2",
    "funded_by": "#8e44ad",
}


for edge in edges:
    subject = edge["subject"]
    object_id = edge["object"]
    predicate = edge["predicate"]

    source = edge.get("source", "")
    quote = edge.get("quote", "")
    confidence = edge.get("confidence")

    title_parts = [
        f"<b>{predicate}</b>",
    ]

    if source:
        title_parts.append(
            f"Source: {source}"
        )

    if quote:
        title_parts.append(
            f"Evidence: {quote}"
        )

    if confidence is not None:
        title_parts.append(
            f"Confidence: {confidence}"
        )

    net.add_edge(
        subject,
        object_id,
        label=predicate,
        title="<br>".join(title_parts),
        color=edge_colors.get(predicate, "#999999"),
        arrows="to",
        font={
            "size": 11,
            "align": "middle"
        },
    )


# ---------------------------------------------------------
# Physics / interaction controls
# ---------------------------------------------------------

net.set_options("""
{
  "interaction": {
    "hover": true,
    "navigationButtons": true,
    "keyboard": true,
    "multiselect": true
  },

  "physics": {
    "enabled": true,
    "solver": "forceAtlas2Based",
    "forceAtlas2Based": {
      "gravitationalConstant": -5000,
      "centralGravity": 0.15,
      "springLength": 180,
      "springConstant": 0.05,
      "damping": 0.4,
      "avoidOverlap": 1
    },
    "minVelocity": 0.75
  },

  "edges": {
    "smooth": {
      "enabled": true,
      "type": "dynamic"
    }
  },

  "nodes": {
    "borderWidth": 1,
    "shadow": true
  }
}
""")


# ---------------------------------------------------------
# Generate HTML
# ---------------------------------------------------------

net.write_html(
    str(OUTPUT_FILE),
    notebook=False
)


print()
print("Visualization created successfully.")
print()
print(f"HTML file:")
print(f"  {OUTPUT_FILE}")
print("=" * 70)