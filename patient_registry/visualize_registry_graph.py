import json
from pathlib import Path
from pyvis.network import Network


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

NODES_FILE = DATA_DIR / "registry_nodes.jsonl"
EDGES_FILE = DATA_DIR / "registry_edges.jsonl"

OUTPUT_FILE = BASE_DIR / "registry_graph.html"


# ============================================================
# LOAD NODES
# ============================================================

nodes = []

with open(
    NODES_FILE,
    "r",
    encoding="utf-8",
) as f:

    for line in f:

        if line.strip():
            nodes.append(
                json.loads(line)
            )


# ============================================================
# LOAD EDGES
# ============================================================

edges = []

with open(
    EDGES_FILE,
    "r",
    encoding="utf-8",
) as f:

    for line in f:

        if line.strip():
            edges.append(
                json.loads(line)
            )


print("=" * 70)
print("PATIENT REGISTRY GRAPH VISUALIZATION")
print("=" * 70)

print(
    f"Nodes loaded: {len(nodes)}"
)

print(
    f"Edges loaded: {len(edges)}"
)


# ============================================================
# CREATE NETWORK
# ============================================================

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


# ============================================================
# NODE COLORS
# ============================================================

node_colors = {
    "disease": "#ef9a9a",
    "asset": "#ffcc80",
}


# ============================================================
# ADD NODES
# ============================================================

for node in nodes:

    node_id = node["id"]
    node_type = node["type"]
    label = node["label"]

    attrs = node.get(
        "attrs",
        {},
    )

    title_parts = [
        f"<b>{label}</b>",
        f"Type: {node_type}",
    ]

    for key, value in attrs.items():

        if value is not None and value != "":

            title_parts.append(
                f"{key}: {value}"
            )

    net.add_node(
        node_id,
        label=label,
        title="<br>".join(
            title_parts
        ),
        color=node_colors.get(
            node_type,
            "#dddddd",
        ),
        shape="dot",
        size=25,
        font={
            "size": 15
        },
    )


# ============================================================
# EDGE COLORS
# ============================================================

edge_colors = {
    "has_registry": "#555555",
}


# ============================================================
# ADD EDGES
# ============================================================

for edge in edges:

    subject = edge["subject"]
    object_id = edge["object"]
    predicate = edge["predicate"]

    source = edge.get(
        "source",
        "",
    )

    quote = edge.get(
        "quote",
        "",
    )

    title_parts = [
        f"<b>{predicate}</b>"
    ]

    if source:

        title_parts.append(
            f"Source: {source}"
        )

    if quote:

        title_parts.append(
            f"Evidence: {quote}"
        )

    net.add_edge(
        subject,
        object_id,
        label=predicate,
        title="<br>".join(
            title_parts
        ),
        color=edge_colors.get(
            predicate,
            "#999999",
        ),
        arrows="to",
        font={
            "size": 12,
            "align": "middle",
        },
    )


# ============================================================
# VISUAL OPTIONS
# ============================================================

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


# ============================================================
# WRITE HTML
# ============================================================

net.write_html(
    str(OUTPUT_FILE),
    notebook=False,
)


print()
print("=" * 70)
print("VISUALIZATION CREATED")
print("=" * 70)

print(
    f"HTML file:"
)

print(
    f"  {OUTPUT_FILE}"
)

print("=" * 70)
