import json
from pathlib import Path
from html import escape

# ============================================================
# CONFIG
# ============================================================

BASE = Path(__file__).resolve().parent

NODES_FILE = BASE / "data" / "graph_nodes_unified.jsonl"
EDGES_FILE = BASE / "data" / "edges_unified.jsonl"

OUTPUT = BASE / "rare_disease_progressive.html"

DEFAULT_DISEASE = "MONDO:0016295"

# How many hops to show initially
INITIAL_HOPS = 1

# Maximum nodes shown at once
MAX_VISIBLE_NODES = 250


# ============================================================
# LOAD GRAPH
# ============================================================

def load_jsonl(path):
    rows = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON line in {path}: {line[:100]}")

    return rows


print("=" * 60)
print("RARE DISEASE KNOWLEDGE GRAPH VISUALIZER")
print("=" * 60)

print("\nLoading nodes...")
nodes = load_jsonl(NODES_FILE)

print("Loading edges...")
edges = load_jsonl(EDGES_FILE)

print(f"\nTotal nodes: {len(nodes)}")
print(f"Total edges: {len(edges)}")


# ============================================================
# INDEX NODES
# ============================================================

node_by_id = {}

for node in nodes:
    node_id = node.get("id")

    if node_id:
        node_by_id[node_id] = node


# ============================================================
# INDEX EDGES
# ============================================================

edges_by_node = {}

for edge in edges:
    subject = edge.get("subject")
    obj = edge.get("object")

    if not subject or not obj:
        continue

    edges_by_node.setdefault(subject, []).append(edge)
    edges_by_node.setdefault(obj, []).append(edge)


# ============================================================
# NODE STYLING
# ============================================================

TYPE_CONFIG = {
    "disease": {
        "color": "#ef4444",
        "shape": "dot",
        "size": 30,
    },
    "gene": {
        "color": "#3b82f6",
        "shape": "dot",
        "size": 24,
    },
    "variant": {
        "color": "#8b5cf6",
        "shape": "diamond",
        "size": 22,
    },
    "phenotype": {
        "color": "#f59e0b",
        "shape": "dot",
        "size": 20,
    },
    "mechanism": {
        "color": "#10b981",
        "shape": "hexagon",
        "size": 22,
    },
    "patient_group": {
        "color": "#ec4899",
        "shape": "dot",
        "size": 20,
    },
    "paper": {
        "color": "#64748b",
        "shape": "box",
        "size": 16,
    },
    "study": {
        "color": "#06b6d4",
        "shape": "box",
        "size": 18,
    },
    "asset": {
        "color": "#84cc16",
        "shape": "box",
        "size": 18,
    },
    "person": {
        "color": "#94a3b8",
        "shape": "dot",
        "size": 14,
    },
    "organization": {
        "color": "#f97316",
        "shape": "box",
        "size": 18,
    },
    "grant": {
        "color": "#a78bfa",
        "shape": "box",
        "size": 14,
    },
    "topic": {
        "color": "#f97316",
        "shape": "dot",
        "size": 16,
    },
}


def node_config(node):
    node_type = node.get("type", "other")

    config = TYPE_CONFIG.get(
        node_type,
        {
            "color": "#94a3b8",
            "shape": "dot",
            "size": 16,
        },
    )

    return config


def node_label(node):
    label = node.get("label") or node.get("id") or "Unknown"

    # Keep labels manageable
    if len(label) > 70:
        label = label[:67] + "..."

    return label


def node_title(node):
    node_id = node.get("id", "")
    label = node.get("label", "")
    node_type = node.get("type", "")

    attrs = node.get("attrs", {})

    lines = [
        f"<b>{escape(str(label))}</b>",
        f"Type: {escape(str(node_type))}",
        f"ID: {escape(str(node_id))}",
    ]

    if node_type == "asset":
        resource_type = attrs.get("resource_type")
        if resource_type:
            lines.append(
                f"Resource type: {escape(str(resource_type))}"
            )

    if attrs:
        shown = 0
        for key, value in attrs.items():
            # Avoid repeating source information that is already
            # displayed by the generic node metadata.
            if key == "source" and len(lines) > 3:
                continue

            value_string = str(value)

            if len(value_string) > 300:
                value_string = value_string[:297] + "..."

            lines.append(
                f"{escape(str(key))}: {escape(value_string)}"
            )

            shown += 1
            if shown >= 8:
                break

    return "<br>".join(lines)


# ============================================================
# DISEASE LIST
# ============================================================

diseases = []

for node in nodes:
    if node.get("type") == "disease":
        diseases.append(
            {
                "id": node.get("id"),
                "label": node.get("label") or node.get("id"),
            }
        )

diseases.sort(
    key=lambda x: str(x["label"]).lower()
)

print(f"Diseases available: {len(diseases)}")


# ============================================================
# GET NEIGHBORHOOD
# ============================================================

def get_neighborhood(root_id, hops=1):
    """
    Return nodes and edges within N hops of root_id.
    """

    if root_id not in node_by_id:
        return set(), []

    visited = {root_id}
    frontier = {root_id}

    selected_edges = []

    for _ in range(hops):

        next_frontier = set()

        for current in frontier:

            for edge in edges_by_node.get(current, []):

                subject = edge.get("subject")
                obj = edge.get("object")

                if not subject or not obj:
                    continue

                selected_edges.append(edge)

                other = obj if subject == current else subject

                if other not in visited:
                    visited.add(other)
                    next_frontier.add(other)

        frontier = next_frontier

        if not frontier:
            break

    # Deduplicate edges
    unique_edges = {}

    for edge in selected_edges:

        key = (
            edge.get("subject"),
            edge.get("predicate"),
            edge.get("object"),
            edge.get("source"),
        )

        unique_edges[key] = edge

    return visited, list(unique_edges.values())


# ============================================================
# INITIAL GRAPH
# ============================================================

initial_node_ids, initial_edges = get_neighborhood(
    DEFAULT_DISEASE,
    INITIAL_HOPS,
)

# Ensure disease itself exists
initial_node_ids.add(DEFAULT_DISEASE)

# Protect against accidentally rendering huge graphs
if len(initial_node_ids) > MAX_VISIBLE_NODES:

    print(
        f"Initial neighborhood has {len(initial_node_ids)} nodes."
    )

    print(
        f"Limiting to {MAX_VISIBLE_NODES} nodes."
    )

    initial_node_ids = set(
        list(initial_node_ids)[:MAX_VISIBLE_NODES]
    )

    initial_edges = [
        edge
        for edge in initial_edges
        if (
            edge.get("subject") in initial_node_ids
            and edge.get("object") in initial_node_ids
        )
    ]


print(f"Initial nodes: {len(initial_node_ids)}")
print(f"Initial edges: {len(initial_edges)}")


# ============================================================
# SERIALIZE DATA FOR JAVASCRIPT
# ============================================================

# ALL graph data goes into JS.
# This does NOT mean it gets rendered.
# JS dynamically selects what is visible.

all_nodes_for_js = []

for node in nodes:

    node_id = node.get("id")

    if not node_id:
        continue

    config = node_config(node)

    all_nodes_for_js.append(
        {
            "id": node_id,
            "label": node_label(node),
            "title": node_title(node),
            "group": node.get("type", "other"),
            "color": config["color"],
            "shape": config["shape"],
            "size": config["size"],
            "type": node.get("type", "other"),
            "source": (
                node.get("attrs", {}).get("source")
                or node.get("attrs", {}).get("source_name")
                or ""
            ),
        }
    )


all_edges_for_js = []

for index, edge in enumerate(edges):

    subject = edge.get("subject")
    obj = edge.get("object")

    if not subject or not obj:
        continue

    predicate = edge.get("predicate", "")

    quote = edge.get("quote") or ""

    source = edge.get("source") or ""

    evidence_type = edge.get("evidence_type") or ""

    confidence = edge.get("confidence")

    status = "verified"

    # Provisional edges
    if "provisional" in str(edge.get("status", "")).lower():
        status = "provisional"

    edge_title = (
        f"<b>{escape(str(predicate))}</b><br>"
        f"Evidence: {escape(str(evidence_type))}<br>"
        f"Source: {escape(str(source))}<br>"
        f"Status: {escape(str(status))}"
    )

    if confidence is not None:
        edge_title += (
            f"<br>Confidence: {escape(str(confidence))}"
        )

    if quote:
        edge_title += (
            "<br><br><b>Evidence</b><br>"
            + escape(str(quote))
        )

    all_edges_for_js.append(
        {
            "id": f"edge_{index}",
            "from": subject,
            "to": obj,
            "label": predicate,
            "title": edge_title,
            "predicate": predicate,
            "status": status,
            "evidence_type": evidence_type,
            "source": source,
            "arrows": "to",
        }
    )


initial_ids_for_js = list(initial_node_ids)


# ============================================================
# JSON ENCODING
# ============================================================

nodes_json = json.dumps(
    all_nodes_for_js,
    ensure_ascii=False,
)

edges_json = json.dumps(
    all_edges_for_js,
    ensure_ascii=False,
)

diseases_json = json.dumps(
    diseases,
    ensure_ascii=False,
)

initial_ids_json = json.dumps(
    initial_ids_for_js,
    ensure_ascii=False,
)


# ============================================================
# HTML
# ============================================================

html = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Rare Disease Knowledge Graph | Research Ecosystem</title>

<script
    src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js">
</script>

<style>

* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    background: #0f172a;
    color: #e2e8f0;
}

#app {
    width: 100%;
    height: 100%;
    display: flex;
}

#sidebar {
    width: 330px;
    min-width: 330px;
    background: #111827;
    border-right: 1px solid #334155;
    padding: 20px;
    overflow-y: auto;
}

#sidebar h1 {
    margin: 0 0 8px 0;
    font-size: 21px;
    color: #f8fafc;
}

.subtitle {
    color: #94a3b8;
    font-size: 13px;
    line-height: 1.5;
    margin-bottom: 20px;
}

.section {
    margin-top: 20px;
}

.section-title {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
    margin-bottom: 8px;
}

select,
button {
    width: 100%;
    border-radius: 8px;
    border: 1px solid #475569;
    background: #1e293b;
    color: #e2e8f0;
    padding: 10px;
    font-size: 14px;
}

button {
    cursor: pointer;
    margin-top: 8px;
}

button:hover {
    background: #334155;
}

button.primary {
    background: #2563eb;
    border-color: #2563eb;
}

button.primary:hover {
    background: #1d4ed8;
}

.stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}

.stat {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px;
}

.stat-number {
    font-size: 20px;
    font-weight: 700;
    color: #f8fafc;
}

.stat-label {
    font-size: 11px;
    color: #94a3b8;
    margin-top: 2px;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    margin: 7px 0;
}

.legend-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
}

.info {
    margin-top: 16px;
    padding: 10px;
    background: #172033;
    border-radius: 8px;
    border: 1px solid #334155;
    color: #94a3b8;
    font-size: 12px;
    line-height: 1.5;
}

#network-container {
    flex: 1;
    position: relative;
    min-width: 0;
}

#network {
    width: 100%;
    height: 100%;
}

#topbar {
    position: absolute;
    top: 15px;
    left: 15px;
    right: 15px;
    display: flex;
    justify-content: space-between;
    pointer-events: none;
}

#status {
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 9px 12px;
    font-size: 12px;
    color: #cbd5e1;
    pointer-events: auto;
}

#hint {
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 9px 12px;
    font-size: 12px;
    color: #94a3b8;
}

</style>

</head>

<body>

<div id="app">

    <aside id="sidebar">

        <h1>Rare Disease Knowledge Graph</h1>

        <div class="subtitle">
            Progressive exploration of diseases, genes,
            phenotypes, studies, papers, registries, organizations
            and research assets.
        </div>

        <div class="section">

            <div class="section-title">
                Select disease
            </div>

            <select id="diseaseSelect"></select>

            <button
                id="loadDisease"
                class="primary"
            >
                Load Disease
            </button>

            <button id="expandSelected">
                Expand Selected
            </button>

            <button id="resetGraph">
                Reset
            </button>

        </div>

        <div class="section">

            <div class="section-title">
                Current graph
            </div>

            <div class="stats">

                <div class="stat">
                    <div
                        class="stat-number"
                        id="nodeCount"
                    >
                        0
                    </div>

                    <div class="stat-label">
                        Visible nodes
                    </div>
                </div>

                <div class="stat">
                    <div
                        class="stat-number"
                        id="edgeCount"
                    >
                        0
                    </div>

                    <div class="stat-label">
                        Visible edges
                    </div>
                </div>

                <div class="stat">
                    <div
                        class="stat-number"
                        id="studyCount"
                    >
                        0
                    </div>

                    <div class="stat-label">
                        Studies / projects
                    </div>
                </div>

                <div class="stat">
                    <div
                        class="stat-number"
                        id="assetCount"
                    >
                        0
                    </div>

                    <div class="stat-label">
                        Registries / assets
                    </div>
                </div>

            </div>

        </div>

        <div class="section">

            <div class="section-title">
                Node types
            </div>

            <div class="legend-item">
                <span
                    class="legend-dot"
                    style="background:#ef4444"
                ></span>
                Disease
            </div>

            <div class="legend-item">
                <span
                    class="legend-dot"
                    style="background:#3b82f6"
                ></span>
                Gene
            </div>

            <div class="legend-item">
                <span
                    class="legend-dot"
                    style="background:#f59e0b"
                ></span>
                Phenotype
            </div>

            <div class="legend-item">
                <span
                    class="legend-dot"
                    style="background:#10b981"
                ></span>
                Mechanism
            </div>

            <div class="legend-item">
                <span
                    class="legend-dot"
                    style="background:#06b6d4"
                ></span>
                Study / NIH project
            </div>

            <div class="legend-item">
                <span
                    class="legend-dot"
                    style="background:#f97316"
                ></span>
                Organization
            </div>

            <div class="legend-item">
                <span
                    class="legend-dot"
                    style="background:#84cc16"
                ></span>
                Research asset / registry
            </div>

            <div class="legend-item">
                <span
                    class="legend-dot"
                    style="background:#64748b"
                ></span>
                Paper
            </div>

        </div>

        <div class="info">

            <b>How to explore</b>

            <br><br>

            1. Select a disease.

            <br>

            2. Click <b>Load Disease</b>.

            <br>

            3. Click a node.

            <br>

            4. Click <b>Expand Selected</b>.

            <br><br>

            The graph starts small instead of displaying
            the full graph at once. Expand NIH projects to see
            principal investigators and organizations, and expand
            a disease to reveal patient registries and studies.

        </div>

    </aside>

    <main id="network-container">

        <div id="network"></div>

        <div id="topbar">

            <div id="status">
                Loading...
            </div>

            <div id="hint">
                Click a node to select it
            </div>

        </div>

    </main>

</div>


<script>

/* ============================================================
   DATA
   ============================================================ */

const ALL_NODES = __ALL_NODES__;

const ALL_EDGES = __ALL_EDGES__;

const DISEASES = __DISEASES__;

const INITIAL_NODE_IDS = __INITIAL_NODE_IDS__;


/* ============================================================
   INDEX DATA
   ============================================================ */

const nodeMap = new Map();

ALL_NODES.forEach(function(node) {
    nodeMap.set(String(node.id), node);
});


const edgeMap = new Map();

ALL_EDGES.forEach(function(edge) {

    const subject = String(edge.from);
    const object = String(edge.to);

    if (!edgeMap.has(subject)) {
        edgeMap.set(subject, []);
    }

    if (!edgeMap.has(object)) {
        edgeMap.set(object, []);
    }

    edgeMap.get(subject).push(edge);
    edgeMap.get(object).push(edge);

});


/* ============================================================
   VISIBLE DATASETS
   ============================================================ */

const visibleNodes = new vis.DataSet([]);

const visibleEdges = new vis.DataSet([]);


/* ============================================================
   NETWORK
   ============================================================ */

const container = document.getElementById("network");

const networkOptions = {

    physics: {

        enabled: true,

        stabilization: {
            enabled: true,
            iterations: 300,
            fit: true
        },

        barnesHut: {
            gravitationalConstant: -6000,
            centralGravity: 0.15,
            springLength: 160,
            springConstant: 0.04,
            damping: 0.18
        }

    },

    interaction: {

        hover: true,

        navigationButtons: true,

        keyboard: true,

        tooltipDelay: 100

    },

    nodes: {

        font: {
            color: "#e2e8f0",
            size: 13
        },

        borderWidth: 2,

        shadow: true

    },

    edges: {

        color: {
            color: "#64748b",
            highlight: "#f8fafc",
            hover: "#cbd5e1"
        },

        width: 1.5,

        arrows: {
            to: {
                enabled: true,
                scaleFactor: 0.5
            }
        },

        font: {
            color: "#cbd5e1",
            size: 10,
            strokeWidth: 3,
            strokeColor: "#0f172a"
        },

        smooth: {
            enabled: true,
            type: "dynamic"
        }

    }

};


const network = new vis.Network(
    container,
    {
        nodes: visibleNodes,
        edges: visibleEdges
    },
    networkOptions
);


/* ============================================================
   HELPERS
   ============================================================ */

function updateStats() {

    const nodeCount =
        visibleNodes.get().length;

    const visibleNodeRows = visibleNodes.get();

    const edgeCount =
        visibleEdges.get().length;

    const studyCount =
        visibleNodeRows.filter(function(node) {
            return node.type === "study";
        }).length;

    const assetCount =
        visibleNodeRows.filter(function(node) {
            return node.type === "asset";
        }).length;

    document.getElementById("nodeCount").textContent =
        String(nodeCount);

    document.getElementById("edgeCount").textContent =
        String(edgeCount);

    document.getElementById("studyCount").textContent =
        String(studyCount);

    document.getElementById("assetCount").textContent =
        String(assetCount);

}


function setStatus(message) {

    document.getElementById("status").textContent =
        message;

}


function addNode(nodeId) {

    nodeId = String(nodeId);

    if (visibleNodes.get(nodeId) !== null) {
        return false;
    }

    const node = nodeMap.get(nodeId);

    if (!node) {
        return false;
    }

    visibleNodes.add(node);

    return true;
}


function addEdge(edge) {

    const edgeId = String(edge.id);

    if (visibleEdges.get(edgeId) !== null) {
        return false;
    }

    const subject = String(edge.from);
    const object = String(edge.to);

    if (
        visibleNodes.get(subject) === null ||
        visibleNodes.get(object) === null
    ) {
        return false;
    }

    visibleEdges.add(edge);

    return true;
}


function showNodes(nodeIds) {

    nodeIds.forEach(function(nodeId) {
        addNode(nodeId);
    });

    ALL_EDGES.forEach(function(edge) {

        const subject = String(edge.from);
        const object = String(edge.to);

        if (
            nodeIds.includes(subject) &&
            nodeIds.includes(object)
        ) {
            addEdge(edge);
        }

    });

    updateStats();

}


function clearGraph() {

    visibleEdges.clear();

    visibleNodes.clear();

    updateStats();

}


/* ============================================================
   LOAD DISEASE
   ============================================================ */

function loadDisease(diseaseId) {

    clearGraph();

    diseaseId = String(diseaseId);

    const result =
        getNeighborhood(diseaseId, 1);

    const nodeIds =
        Array.from(result.nodes);

    showNodes(nodeIds);

    if (visibleNodes.get(diseaseId) !== null) {

        network.selectNodes([diseaseId]);

        network.focus(
            diseaseId,
            {
                scale: 1.0,
                animation: {
                    duration: 600,
                    easingFunction: "easeInOutQuad"
                }
            }
        );

    }

    setStatus(
        "Loaded " +
        nodeIds.length +
        " nodes and " +
        visibleEdges.get().length +
        " edges"
    );

}


/* ============================================================
   NEIGHBORHOOD
   ============================================================ */

function getNeighborhood(rootId, hops) {

    const visited = new Set();

    const frontier = new Set();

    rootId = String(rootId);

    visited.add(rootId);

    frontier.add(rootId);

    for (
        let hop = 0;
        hop < hops;
        hop++
    ) {

        const next = new Set();

        frontier.forEach(function(current) {

            const incident =
                edgeMap.get(current) || [];

            incident.forEach(function(edge) {

                const subject =
                    String(edge.from);

                const object =
                    String(edge.to);

                const other =
                    subject === current
                        ? object
                        : subject;

                if (!visited.has(other)) {

                    visited.add(other);

                    next.add(other);

                }

            });

        });

        frontier.clear();

        next.forEach(function(id) {
            frontier.add(id);
        });

    }

    return {
        nodes: visited
    };

}


/* ============================================================
   EXPAND SELECTED
   ============================================================ */

function expandSelected() {

    const selected =
        network.getSelectedNodes();

    if (!selected.length) {

        setStatus(
            "Select a node first"
        );

        return;

    }

    const selectedId =
        String(selected[0]);

    const incident =
        edgeMap.get(selectedId) || [];

    let addedNodes = 0;
    let addedEdges = 0;

    incident.forEach(function(edge) {

        const subject =
            String(edge.from);

        const object =
            String(edge.to);

        const other =
            subject === selectedId
                ? object
                : subject;

        if (
            visibleNodes.get(other) === null &&
            visibleNodes.get().length < 250
        ) {

            if (addNode(other)) {
                addedNodes++;
            }

        }

    });


    incident.forEach(function(edge) {

        if (addEdge(edge)) {
            addedEdges++;
        }

    });


    updateStats();

    network.fit({
        animation: {
            duration: 500,
            easingFunction: "easeInOutQuad"
        }
    });


    setStatus(
        "Expanded " +
        selectedId +
        " | +" +
        addedNodes +
        " nodes, +" +
        addedEdges +
        " edges"
    );

}


/* ============================================================
   RESET
   ============================================================ */

function resetGraph() {

    const select =
        document.getElementById("diseaseSelect");

    const diseaseId =
        select.value || "__DEFAULT_DISEASE__";

    loadDisease(diseaseId);

}


/* ============================================================
   DISEASE DROPDOWN
   ============================================================ */

const diseaseSelect =
    document.getElementById("diseaseSelect");


DISEASES.forEach(function(disease) {

    const option =
        document.createElement("option");

    option.value =
        disease.id;

    option.textContent =
        disease.label +
        " (" +
        disease.id +
        ")";

    diseaseSelect.appendChild(option);

});


if (
    DISEASES.some(function(d) {
        return d.id === "__DEFAULT_DISEASE__";
    })
) {

    diseaseSelect.value =
        "__DEFAULT_DISEASE__";

}


/* ============================================================
   BUTTONS
   ============================================================ */

document
    .getElementById("loadDisease")
    .addEventListener(
        "click",
        function() {

            loadDisease(
                diseaseSelect.value
            );

        }
    );


document
    .getElementById("expandSelected")
    .addEventListener(
        "click",
        expandSelected
    );


document
    .getElementById("resetGraph")
    .addEventListener(
        "click",
        resetGraph
    );


/* ============================================================
   NODE CLICK
   ============================================================ */

network.on(
    "selectNode",
    function(params) {

        if (!params.nodes.length) {
            return;
        }

        const nodeId =
            String(params.nodes[0]);

        const node =
            nodeMap.get(nodeId);

        if (!node) {
            return;
        }

        const source =
            node.source ? " | " + node.source : "";

        setStatus(
            "Selected: " +
            (node.label || nodeId) +
            " [" +
            (node.type || "unknown") +
            "]" +
            source
        );

    }
);


/* ============================================================
   INITIAL LOAD
   ============================================================ */

showNodes(INITIAL_NODE_IDS);

if (
    visibleNodes.get(
        "__DEFAULT_DISEASE__"
    ) !== null
) {

    network.selectNodes(
        ["__DEFAULT_DISEASE__"]
    );

}

network.fit();

setStatus(
    "Showing disease neighborhood. Expand studies, projects, and registries to reveal the research ecosystem."
);

</script>

</body>
</html>
"""


# ============================================================
# REPLACE PLACEHOLDERS
# ============================================================

html = html.replace(
    "__ALL_NODES__",
    nodes_json,
)

html = html.replace(
    "__ALL_EDGES__",
    edges_json,
)

html = html.replace(
    "__DISEASES__",
    diseases_json,
)

html = html.replace(
    "__INITIAL_NODE_IDS__",
    initial_ids_json,
)

html = html.replace(
    "__DEFAULT_DISEASE__",
    DEFAULT_DISEASE,
)


# ============================================================
# WRITE HTML
# ============================================================

with open(
    OUTPUT,
    "w",
    encoding="utf-8",
) as f:

    f.write(html)


print("\n" + "=" * 60)
print("DONE")
print("=" * 60)

print(f"\nOutput:")
print(OUTPUT)

print(
    f"\nInitial visible nodes: {len(initial_node_ids)}"
)

print(
    f"Initial visible edges: {len(initial_edges)}"
)

print(
    f"Full graph nodes available to browser: {len(nodes)}"
)

print(
    f"Full graph edges available to browser: {len(edges)}"
)

print(
    "\nOpen this file:"
)

print(
    f"  {OUTPUT}"
)