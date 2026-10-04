import json
from pathlib import Path

from pyvis.network import Network


DATA = Path("data")
OUTPUT = "rare_disease_graph.html"


# -----------------------------
# Load edges
# -----------------------------

edges = []

for filename, status in [
    ("edges_verified.jsonl", "canonical"),
    ("edges_provisional.jsonl", "provisional"),
]:
    path = DATA / filename

    if not path.exists():
        continue

    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                edge = json.loads(line)
                edge["status"] = status
                edges.append(edge)


# -----------------------------
# Node helpers
# -----------------------------

nodes = {}


def node_type(edge, side):
    return edge[f"{side}_type"]


def node_label(edge, side):
    return edge[f"{side}_label"]


def node_id(edge, side):
    return edge[side]


# -----------------------------
# Create nodes
# -----------------------------

for edge in edges:

    for side in ("subject", "object"):

        nid = node_id(edge, side)

        if nid in nodes:
            continue

        ntype = node_type(edge, side)
        label = node_label(edge, side)

        nodes[nid] = {
            "id": nid,
            "label": label,
            "type": ntype,
        }


# -----------------------------
# Network
# -----------------------------

net = Network(
    height="900px",
    width="100%",
    bgcolor="#ffffff",
    font_color="#222222",
    directed=True,
    notebook=False,
)

net.set_options("""
{
  "nodes": {
    "shape": "dot",
    "font": {
      "size": 16
    },
    "borderWidth": 2
  },

  "edges": {
    "arrows": {
      "to": {
        "enabled": true,
        "scaleFactor": 0.6
      }
    },
    "font": {
      "size": 12,
      "align": "middle",
      "background": "white"
    },
    "smooth": {
      "enabled": true,
      "type": "dynamic"
    }
  },

  "physics": {
    "enabled": true,
    "barnesHut": {
      "gravitationalConstant": -5000,
      "centralGravity": 0.15,
      "springLength": 180,
      "springConstant": 0.04,
      "damping": 0.15
    },
    "stabilization": {
      "enabled": true,
      "iterations": 150
    }
  },

  "interaction": {
    "hover": true,
    "navigationButtons": true,
    "keyboard": true,
    "tooltipDelay": 100
  }
}
""")


# -----------------------------
# Node appearance
# -----------------------------

TYPE_CONFIG = {
    "gene": {
        "color": "#4F81BD",
        "shape": "dot",
    },
    "disease": {
        "color": "#D9534F",
        "shape": "dot",
    },
    "phenotype": {
        "color": "#5CB85C",
        "shape": "dot",
    },
    "treatment": {
        "color": "#F0AD4E",
        "shape": "dot",
    },
    "molecule": {
        "color": "#9B59B6",
        "shape": "dot",
    },
    "pathway": {
        "color": "#16A085",
        "shape": "dot",
    },
    "other": {
        "color": "#95A5A6",
        "shape": "dot",
    },
}


for nid, n in nodes.items():

    config = TYPE_CONFIG.get(
        n["type"],
        TYPE_CONFIG["other"],
    )

    net.add_node(
        nid,
        label=n["label"],
        title=(
            f"<b>{n['label']}</b><br>"
            f"Type: {n['type']}<br>"
            f"ID: {nid}"
        ),
        color=config["color"],
        shape=config["shape"],
    )


# -----------------------------
# Edges
# -----------------------------

for edge in edges:

    subject = edge["subject"]
    object_ = edge["object"]

    predicate = edge["predicate"]
    quote = edge.get("quote", "")
    source = edge.get("source", "")
    evidence = edge.get("evidence_type", "")
    status = edge["status"]

    tooltip = f"""
    <b>{edge["subject_label"]}</b>
    → <b>{predicate}</b> →
    <b>{edge["object_label"]}</b>
    <br><br>

    <b>Status:</b> {status}
    <br>
    <b>Evidence:</b> {evidence}
    <br>
    <b>Source:</b> {source}
    <br><br>

    <b>Quote:</b><br>
    {quote}
    """

    # provisional edges are dashed
    if status == "provisional":
        dashes = True
        width = 1.5
    else:
        dashes = False
        width = 2.5

    net.add_edge(
        subject,
        object_,
        label=predicate,
        title=tooltip,
        dashes=dashes,
        width=width,
    )


# -----------------------------
# Save
# -----------------------------

net.write_html(
    OUTPUT,
    notebook=False,
)

print(f"Saved graph to {OUTPUT}")
print(f"Nodes: {len(nodes)}")
print(f"Edges: {len(edges)}")