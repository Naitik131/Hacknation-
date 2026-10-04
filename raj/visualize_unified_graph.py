import html
import json
from pathlib import Path

from pyvis.network import Network


DATA = Path("data")
OUTPUT = "rare_disease_unified_graph.html"

NODES_FILE = DATA / "graph_nodes_unified.jsonl"
EDGES_FILE = DATA / "edges_unified.jsonl"

# Default disease shown when the HTML opens.
DEFAULT_DISEASE_ID = "MONDO:0016295"


# ============================================================
# LOAD DATA
# ============================================================

nodes = {}

with open(NODES_FILE, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            node = json.loads(line)
            nodes[node["id"]] = node


edges = []

with open(EDGES_FILE, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            edges.append(json.loads(line))


# Some edges may contain endpoint metadata even when the endpoint
# is not present in graph_nodes_unified.jsonl.
for edge in edges:
    for side in ("subject", "object"):
        node_id = edge.get(side)

        if not node_id:
            continue

        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "type": edge.get(f"{side}_type") or "other",
                "label": edge.get(f"{side}_label") or node_id,
                "attrs": {},
            }


# ============================================================
# HELPERS
# ============================================================

def label_for(node_id):
    node = nodes.get(node_id, {})
    return node.get("label") or node_id


def type_for(node_id):
    node = nodes.get(node_id, {})
    return node.get("type") or "other"


def edge_label(edge, side):
    return (
        edge.get(f"{side}_label")
        or label_for(edge[side])
        or edge[side]
    )


def node_title(node):
    node_id = node["id"]
    label = node.get("label") or node_id
    node_type = node.get("type") or "other"
    attrs = node.get("attrs") or {}

    lines = [
        f"<b>{html.escape(str(label))}</b>",
        f"Type: {html.escape(str(node_type))}",
        f"ID: {html.escape(str(node_id))}",
    ]

    preferred_attrs = [
        "nct_id",
        "status",
        "study_type",
        "phase",
        "enrollment",
        "sponsor",
        "source_url",
        "year",
        "journal",
        "doi",
    ]

    for key in preferred_attrs:
        value = attrs.get(key)

        if value not in (None, "", [], {}):
            lines.append(
                f"{key.replace('_', ' ').title()}: "
                f"{html.escape(str(value))}"
            )

    return "<br>".join(lines)


# ============================================================
# NODE CONFIG
# ============================================================

TYPE_CONFIG = {
    "gene": {
        "color": "#4F81BD",
        "shape": "dot",
        "size": 22,
    },
    "disease": {
        "color": "#D9534F",
        "shape": "dot",
        "size": 32,
    },
    "phenotype": {
        "color": "#5CB85C",
        "shape": "dot",
        "size": 20,
    },
    "treatment": {
        "color": "#F0AD4E",
        "shape": "dot",
        "size": 21,
    },
    "molecule": {
        "color": "#9B59B6",
        "shape": "dot",
        "size": 20,
    },
    "pathway": {
        "color": "#16A085",
        "shape": "dot",
        "size": 21,
    },
    "study": {
        "color": "#E67E22",
        "shape": "diamond",
        "size": 25,
    },
    "asset": {
        "color": "#8E44AD",
        "shape": "square",
        "size": 21,
    },
    "paper": {
        "color": "#34495E",
        "shape": "box",
        "size": 18,
    },
    "person": {
        "color": "#7F8C8D",
        "shape": "dot",
        "size": 14,
    },
    "grant": {
        "color": "#95A5A6",
        "shape": "square",
        "size": 14,
    },
    "topic": {
        "color": "#BDC3C7",
        "shape": "ellipse",
        "size": 15,
    },
    "other": {
        "color": "#95A5A6",
        "shape": "dot",
        "size": 18,
    },
}


# ============================================================
# BUILD NETWORK
# ============================================================

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
      "size": 15,
      "face": "Arial"
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
      "size": 11,
      "align": "middle",
      "background": "white",
      "strokeWidth": 0
    },
    "smooth": {
      "enabled": true,
      "type": "dynamic"
    }
  },

  "physics": {
    "enabled": true,
    "barnesHut": {
      "gravitationalConstant": -6500,
      "centralGravity": 0.15,
      "springLength": 190,
      "springConstant": 0.035,
      "damping": 0.18
    },
    "stabilization": {
      "enabled": true,
      "iterations": 250
    }
  },

  "interaction": {
    "hover": true,
    "navigationButtons": true,
    "keyboard": true,
    "tooltipDelay": 100,
    "hideEdgesOnDrag": true,
    "multiselect": false
  }
}
""")


# ============================================================
# ADD ALL NODES
# ============================================================

for node_id, node in nodes.items():

    node_type = node.get("type") or "other"

    config = TYPE_CONFIG.get(
        node_type,
        TYPE_CONFIG["other"],
    )

    net.add_node(
        node_id,
        label=node.get("label") or node_id,
        title=node_title(node),
        color=config["color"],
        shape=config["shape"],
        size=config["size"],
        group=node_type,
        hidden=True,
    )


# ============================================================
# ADD ALL EDGES, INITIALLY HIDDEN
# ============================================================

for edge in edges:

    subject = edge["subject"]
    object_id = edge["object"]
    predicate = edge["predicate"]

    subject_label = (
        edge.get("subject_label")
        or label_for(subject)
        or subject
    )

    object_label = (
        edge.get("object_label")
        or label_for(object_id)
        or object_id
    )

    source = edge.get("source") or ""
    evidence = edge.get("evidence_type") or ""
    extracted_by = edge.get("extracted_by") or ""
    quote = edge.get("quote") or ""
    confidence = edge.get("confidence")
    contradictions = edge.get("contradicted_by") or []

    details = [
        f"<b>{html.escape(str(subject_label))}</b>",
        f"→ <b>{html.escape(str(predicate))}</b> →",
        f"<b>{html.escape(str(object_label))}</b>",
        "<br><br>",
        f"<b>Evidence:</b> {html.escape(str(evidence))}",
        f"<b>Source:</b> {html.escape(str(source))}",
        f"<b>Extracted by:</b> {html.escape(str(extracted_by))}",
    ]

    if confidence is not None:
        details.append(
            f"<b>Confidence:</b> {html.escape(str(confidence))}"
        )

    if quote:
        details.extend([
            "<br><b>Quote:</b><br>",
            html.escape(str(quote)),
        ])

    if contradictions:
        details.extend([
            "<br><b>Contradicted by:</b><br>",
            "<br>".join(
                html.escape(str(x))
                for x in contradictions
            ),
        ])

    tooltip = "<br>".join(details)

    is_provisional = (
        edge.get("status") == "provisional"
        or evidence == "hypothesis"
    )

    net.add_edge(
        subject,
        object_id,
        label=predicate,
        title=tooltip,
        dashes=is_provisional,
        width=1.5 if is_provisional else 2.2,
        arrows="to",
        hidden=True,
    )


# ============================================================
# WRITE BASE HTML
# ============================================================

net.write_html(
    OUTPUT,
    notebook=False,
)


# ============================================================
# PROGRESSIVE-REVEAL UI
# ============================================================

diseases = []

for node_id, node in nodes.items():
    if node.get("type") == "disease":
        diseases.append({
            "id": node_id,
            "label": node.get("label") or node_id,
        })

diseases.sort(
    key=lambda x: x["label"].lower()
)

disease_options = "\n".join(
    f'<option value="{html.escape(d["id"])}">'
    f'{html.escape(d["label"])}'
    f'</option>'
    for d in diseases
)

default_exists = DEFAULT_DISEASE_ID in nodes

if not default_exists and diseases:
    default_id = diseases[0]["id"]
else:
    default_id = DEFAULT_DISEASE_ID


ui = f"""
<style>
#graph-controls {{
    position: fixed;
    top: 15px;
    left: 15px;
    z-index: 9999;
    background: rgba(255,255,255,0.97);
    border: 1px solid #ddd;
    border-radius: 12px;
    padding: 14px;
    width: 330px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.12);
    font-family: Arial, sans-serif;
}}

#graph-controls h3 {{
    margin: 0 0 8px 0;
    font-size: 18px;
}}

#graph-controls p {{
    margin: 6px 0 10px 0;
    color: #666;
    font-size: 12px;
    line-height: 1.4;
}}

#disease-select {{
    width: 100%;
    padding: 9px;
    border: 1px solid #ccc;
    border-radius: 7px;
    font-size: 13px;
    background: white;
}}

.graph-btn {{
    margin-top: 8px;
    margin-right: 5px;
    padding: 8px 11px;
    border: none;
    border-radius: 7px;
    cursor: pointer;
    font-size: 12px;
}}

#load-disease {{
    background: #D9534F;
    color: white;
}}

#reset-graph {{
    background: #eee;
    color: #333;
}}

#expand-selected {{
    background: #4F81BD;
    color: white;
}}

#graph-status {{
    margin-top: 9px;
    font-size: 12px;
    color: #555;
}}

#graph-legend {{
    position: fixed;
    bottom: 15px;
    left: 15px;
    z-index: 9999;
    background: rgba(255,255,255,0.95);
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 10px 12px;
    font-family: Arial, sans-serif;
    font-size: 11px;
    box-shadow: 0 3px 12px rgba(0,0,0,0.08);
}}

.legend-row {{
    margin: 3px 0;
}}
</style>

<div id="graph-controls">
    <h3>Rare Disease Knowledge Graph</h3>

    <p>
        Select a disease to start with its directly connected
        genes, phenotypes, treatments and clinical studies.
        Click a node to progressively reveal more evidence.
    </p>

    <select id="disease-select">
        {disease_options}
    </select>

    <br>

    <button class="graph-btn" id="load-disease">
        Load disease
    </button>

    <button class="graph-btn" id="reset-graph">
        Reset
    </button>

    <button class="graph-btn" id="expand-selected">
        Expand selected
    </button>

    <div id="graph-status">
        Loading...
    </div>
</div>

<div id="graph-legend">
    <div class="legend-row">🔴 Disease</div>
    <div class="legend-row">🔵 Gene</div>
    <div class="legend-row">🟢 Phenotype</div>
    <div class="legend-row">🟠 Clinical study</div>
    <div class="legend-row">🟣 Treatment / asset</div>
    <div class="legend-row">⬛ Paper</div>
    <div class="legend-row">╌ Provisional / hypothesis edge</div>
</div>

<script>
(function() {{

    const DEFAULT_DISEASE = {json.dumps(default_id)};

    const diseaseLabels = {json.dumps({
        d["id"]: d["label"] for d in diseases
    })};

    const nodeIds = new Set(
        {json.dumps(list(nodes.keys()))}
    );

    const edgeRecords = {json.dumps([
        {
            "subject": e["subject"],
            "object": e["object"],
        }
        for e in edges
    ])};


    function neighborsOf(nodeId) {{
        const neighbors = new Set();

        edgeRecords.forEach(function(edge) {{
            if (edge.subject === nodeId) {{
                neighbors.add(edge.object);
            }}

            if (edge.object === nodeId) {{
                neighbors.add(edge.subject);
            }}
        }});

        return Array.from(neighbors);
    }}


    function edgesTouching(nodeId) {{
        const ids = [];

        edges.forEach(function(edge) {{
            if (
                edge.from === nodeId ||
                edge.to === nodeId
            ) {{
                ids.push(edge.id);
            }}
        }});

        return ids;
    }}


    function hideEverything() {{
        const allNodeIds = nodes.getIds();
        const allEdgeIds = edges.getIds();

        nodes.update(
            allNodeIds.map(function(id) {{
                return {{
                    id: id,
                    hidden: true
                }};
            }})
        );

        edges.update(
            allEdgeIds.map(function(id) {{
                return {{
                    id: id,
                    hidden: true
                }};
            }})
        );
    }}


    function showNode(nodeId) {{
        if (!nodeIds.has(nodeId)) {{
            return;
        }}

        nodes.update([
            {{
                id: nodeId,
                hidden: false
            }}
        ]);
    }}


    function showEdge(edgeId) {{
        edges.update([
            {{
                id: edgeId,
                hidden: false
            }}
        ]);
    }}


    function showConnection(nodeId) {{
        showNode(nodeId);

        const neighborIds = neighborsOf(nodeId);

        neighborIds.forEach(function(neighborId) {{
            showNode(neighborId);
        }});

        const connectedEdges = [];

        edges.forEach(function(edge) {{
            if (
                edge.from === nodeId ||
                edge.to === nodeId
            ) {{
                connectedEdges.push(edge.id);
            }}
        }});

        connectedEdges.forEach(function(edgeId) {{
            showEdge(edgeId);
        }});

        return neighborIds.length;
    }}


    function loadDisease(diseaseId) {{
        hideEverything();

        if (!nodeIds.has(diseaseId)) {{
            document.getElementById("graph-status").innerText =
                "Disease not found in unified graph.";
            return;
        }}

        const count = showConnection(diseaseId);

        network.selectNodes([diseaseId]);

        network.focus(
            diseaseId,
            {{
                scale: 1.0,
                animation: {{
                    duration: 700,
                    easingFunction: "easeInOutQuad"
                }}
            }}
        );

        document.getElementById("graph-status").innerText =
            diseaseLabels[diseaseId] +
            " · " +
            count +
            " directly connected entities";
    }}


    function expandNode(nodeId) {{
        const count = showConnection(nodeId);

        network.selectNodes([nodeId]);

        document.getElementById("graph-status").innerText =
            "Expanded " +
            (diseaseLabels[nodeId] || nodeId) +
            " · " +
            count +
            " connected entities";
    }}


    document.getElementById("load-disease")
        .addEventListener("click", function() {{
            const diseaseId =
                document.getElementById("disease-select").value;

            loadDisease(diseaseId);
        }});


    document.getElementById("reset-graph")
        .addEventListener("click", function() {{
            loadDisease(
                document.getElementById("disease-select").value
            );
        }});


    document.getElementById("expand-selected")
        .addEventListener("click", function() {{
            const selected = network.getSelectedNodes();

            if (selected.length === 0) {{
                return;
            }}

            selected.forEach(function(nodeId) {{
                expandNode(nodeId);
            }});
        }});


    network.on("click", function(params) {{
        if (!params.nodes || params.nodes.length === 0) {{
            return;
        }}

        const nodeId = params.nodes[0];

        // Clicking any visible node reveals its next layer.
        expandNode(nodeId);
    }});


    // Load default disease after the graph has initialized.
    setTimeout(function() {{
        loadDisease(DEFAULT_DISEASE);
    }}, 700);

}})();
</script>
"""


html_path = Path(OUTPUT)
html_text = html_path.read_text(encoding="utf-8")

html_text = html_text.replace(
    "</body>",
    ui + "\n</body>",
)

html_path.write_text(
    html_text,
    encoding="utf-8",
)


# ============================================================
# SUMMARY
# ============================================================

print(f"Saved unified graph to {OUTPUT}")
print(f"Nodes: {len(nodes)}")
print(f"Edges: {len(edges)}")
print(f"Diseases available: {len(diseases)}")
print(f"Default disease: {default_id}")
