"""
Flask API server for the C++ Architecture Analyser.
Serves the web UI and provides REST API endpoints.
"""

import json
import os
import sys
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from analyzer.graph_builder import GraphBuilder
from analyzer.exporter import to_cytoscape_json, to_dot, to_summary_text
from analyzer.models import AnalysisGraph

# ---- App setup ----
BASE_DIR = Path(__file__).parent
WEB_DIR = BASE_DIR / "web"

app = Flask(__name__, static_folder=str(WEB_DIR))
CORS(app)

# Global state
_builder: GraphBuilder | None = None
_current_graph: AnalysisGraph | None = None
_current_seeds: list[str] = []


# ---- Static file serving ----

@app.route('/')
def index():
    return send_from_directory(str(WEB_DIR), 'index.html')


@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(str(WEB_DIR / 'css'), filename)


@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(str(WEB_DIR / 'js'), filename)


# ---- API endpoints ----

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """
    Analyze a project for given symbol names.
    Body: { "project_path": "...", "symbols": ["Noise", ...], "depth": 2 }
    """
    global _builder, _current_graph, _current_seeds

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    project_path = data.get('project_path', '')
    symbols = data.get('symbols', [])
    depth = data.get('depth', 2)

    if not project_path:
        return jsonify({"error": "project_path is required"}), 400
    if not symbols:
        return jsonify({"error": "symbols list is required"}), 400
    if not os.path.isdir(project_path):
        return jsonify({"error": f"Directory not found: {project_path}"}), 400

    try:
        _builder = GraphBuilder(project_path)
        _current_seeds = symbols
        _current_graph = _builder.analyze(symbols, depth=depth)

        # Get seed IDs for highlighting
        seed_ids = set()
        for name in symbols:
            for sym in _current_graph.find_symbols_by_name(name):
                seed_ids.add(sym.id)

        result = to_cytoscape_json(_current_graph, seed_ids=seed_ids)
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/expand', methods=['POST'])
def expand():
    """
    Expand the graph from a specific symbol.
    Body: { "symbol_id": "...", "depth": 1 }
    """
    global _builder, _current_graph

    if not _builder:
        return jsonify({"error": "No project analyzed yet. Call /api/analyze first."}), 400

    data = request.get_json()
    symbol_id = data.get('symbol_id', '')
    depth = data.get('depth', 1)

    if not symbol_id:
        return jsonify({"error": "symbol_id is required"}), 400

    try:
        sym = _builder.index.get_symbol(symbol_id)
        if not sym:
            return jsonify({"error": f"Symbol not found: {symbol_id}"}), 404

        # Expand from this symbol
        included = {symbol_id}
        frontier = {symbol_id}

        for _ in range(depth):
            next_f = set()
            for sid in frontier:
                connected = _builder.index.graph.get_connected_symbols(sid)
                for cid in connected:
                    if cid not in included:
                        included.add(cid)
                        next_f.add(cid)
            frontier = next_f

        subgraph = _builder.index.graph.get_subgraph(included)

        # Merge into current graph
        if _current_graph:
            for s in subgraph.symbols.values():
                _current_graph.add_symbol(s)
            for e in subgraph.edges:
                _current_graph.add_edge(e)

        seed_ids = set()
        for name in _current_seeds:
            for s in _current_graph.find_symbols_by_name(name):
                seed_ids.add(s.id)

        result = to_cytoscape_json(_current_graph, seed_ids=seed_ids)
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/symbol/<symbol_id>', methods=['GET'])
def get_symbol(symbol_id):
    """Get detailed info about a symbol."""
    if not _builder:
        return jsonify({"error": "No project analyzed yet"}), 400

    sym = _builder.index.get_symbol(symbol_id)
    if not sym:
        return jsonify({"error": "Symbol not found"}), 404

    result = sym.to_dict()

    # Add relationship info
    result["members"] = [s.to_dict() for s in _builder.index.get_members(sym.id)]
    result["callers"] = [s.to_dict() for s in _builder.index.get_callers(sym.id)]
    result["callees"] = [s.to_dict() for s in _builder.index.get_callees(sym.id)]

    hierarchy = _builder.index.get_hierarchy(sym.id)
    result["base_classes_resolved"] = [s.to_dict() for s in hierarchy["bases"]]
    result["derived_classes"] = [s.to_dict() for s in hierarchy["derived"]]

    return jsonify(result)


@app.route('/api/search', methods=['GET'])
def search_symbols():
    """Search for symbols by name."""
    if not _builder:
        return jsonify({"error": "No project analyzed yet"}), 400

    query = request.args.get('q', '')
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    results = _builder.index.search(query)
    # Limit results
    results = results[:50]

    return jsonify({
        "query": query,
        "count": len(results),
        "results": [s.to_dict() for s in results],
    })


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get index statistics."""
    if not _builder:
        return jsonify({"error": "No project analyzed yet"}), 400

    return jsonify(_builder.index.get_stats())


@app.route('/api/export/dot', methods=['GET'])
def export_dot():
    """Export current graph as DOT format."""
    if not _current_graph:
        return jsonify({"error": "No graph available"}), 400

    dot = to_dot(_current_graph, title="Architecture Analysis")
    return dot, 200, {'Content-Type': 'text/plain'}


@app.route('/api/export/summary', methods=['GET'])
def export_summary():
    """Export current graph as text summary."""
    if not _current_graph:
        return jsonify({"error": "No graph available"}), 400

    text = to_summary_text(_current_graph, _current_seeds)
    return text, 200, {'Content-Type': 'text/plain'}


def run_server(host: str = '127.0.0.1', port: int = 8080, debug: bool = False):
    """Start the Flask server."""
    print(f"\n  C++ Architecture Analyser")
    print(f"  ========================")
    print(f"  Server: http://{host}:{port}")
    print(f"  Web UI: http://{host}:{port}/")
    print(f"  API:    http://{host}:{port}/api/")
    print()
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    run_server(debug=True)
