"""
Graph exporter — exports AnalysisGraph to various formats:
- Cytoscape.js JSON (for interactive web visualization)
- DOT (for Graphviz static diagrams)
- Text summary (for CLI)
"""

import json
from typing import Optional

from .models import AnalysisGraph, SymbolType, EdgeType


# ---- Color scheme for symbol types ----
SYMBOL_COLORS = {
    SymbolType.CLASS: "#4A9EFF",
    SymbolType.STRUCT: "#5BA8FF",
    SymbolType.FUNCTION: "#47D185",
    SymbolType.METHOD: "#3BC478",
    SymbolType.MEMBER_VARIABLE: "#B07FE0",
    SymbolType.ENUM: "#FF8C42",
    SymbolType.ENUM_VALUE: "#FFB07A",
    SymbolType.NAMESPACE: "#26C6DA",
    SymbolType.TYPEDEF: "#FFD740",
    SymbolType.USING_ALIAS: "#FFE082",
    SymbolType.MACRO: "#EF5350",
    SymbolType.TEMPLATE_CLASS: "#42A5F5",
    SymbolType.TEMPLATE_FUNCTION: "#66BB6A",
    SymbolType.CONSTRUCTOR: "#81C784",
    SymbolType.DESTRUCTOR: "#E57373",
    SymbolType.GLOBAL_VARIABLE: "#CE93D8",
    SymbolType.PARAMETER: "#90A4AE",
    SymbolType.FORWARD_DECLARATION: "#78909C",
    SymbolType.INCLUDE: "#607D8B",
    SymbolType.UNKNOWN: "#9E9E9E",
}

SYMBOL_SHAPES = {
    SymbolType.CLASS: "round-rectangle",
    SymbolType.STRUCT: "round-rectangle",
    SymbolType.FUNCTION: "ellipse",
    SymbolType.METHOD: "ellipse",
    SymbolType.MEMBER_VARIABLE: "round-diamond",
    SymbolType.ENUM: "diamond",
    SymbolType.ENUM_VALUE: "tag",
    SymbolType.NAMESPACE: "hexagon",
    SymbolType.TYPEDEF: "round-tag",
    SymbolType.USING_ALIAS: "round-tag",
    SymbolType.CONSTRUCTOR: "ellipse",
    SymbolType.DESTRUCTOR: "ellipse",
    SymbolType.GLOBAL_VARIABLE: "round-diamond",
    SymbolType.INCLUDE: "rectangle",
}

EDGE_COLORS = {
    EdgeType.CONTAINS: "#546E7A",
    EdgeType.INHERITS: "#FF7043",
    EdgeType.CALLS: "#66BB6A",
    EdgeType.USES_TYPE: "#42A5F5",
    EdgeType.REFERENCES: "#9E9E9E",
    EdgeType.OVERRIDES: "#AB47BC",
    EdgeType.INCLUDES: "#78909C",
    EdgeType.INSTANTIATES: "#26C6DA",
    EdgeType.RETURNS_TYPE: "#FFA726",
    EdgeType.PARAMETER_TYPE: "#8D6E63",
}

EDGE_STYLES = {
    EdgeType.CONTAINS: "solid",
    EdgeType.INHERITS: "solid",
    EdgeType.CALLS: "dashed",
    EdgeType.USES_TYPE: "dotted",
    EdgeType.REFERENCES: "dotted",
    EdgeType.OVERRIDES: "solid",
    EdgeType.INCLUDES: "dashed",
}


def to_cytoscape_json(graph: AnalysisGraph,
                      seed_ids: Optional[set[str]] = None) -> dict:
    """
    Export graph to Cytoscape.js compatible JSON format.

    Args:
        graph: The analysis graph to export
        seed_ids: Optional set of seed symbol IDs (for highlighting)

    Returns:
        Dict with 'elements', 'style', and 'stats' keys
    """
    elements = []

    # Nodes
    for sym in graph.symbols.values():
        # Skip include nodes by default (too many)
        if sym.symbol_type == SymbolType.INCLUDE:
            continue

        is_seed = seed_ids and sym.id in seed_ids
        node_data = {
            "data": {
                "id": sym.id,
                "label": sym.name,
                "qualified_name": sym.qualified_name,
                "type": sym.symbol_type.value,
                "file": sym.file_path,
                "line": sym.line,
                "end_line": sym.end_line,
                "language": sym.language.value,
                "signature": sym.signature,
                "display_name": sym.display_name,
                "return_type": sym.return_type,
                "parameters": [p.to_dict() for p in sym.parameters],
                "access": sym.access.value,
                "base_classes": sym.base_classes,
                "is_virtual": sym.is_virtual,
                "is_static": sym.is_static,
                "is_const": sym.is_const,
                "is_override": sym.is_override,
                "is_pure_virtual": sym.is_pure_virtual,
                "is_seed": is_seed,
                "is_unresolved": sym.file_path == "<unresolved>",
                "color": SYMBOL_COLORS.get(sym.symbol_type, "#9E9E9E"),
                "shape": SYMBOL_SHAPES.get(sym.symbol_type, "ellipse"),
            },
            "classes": sym.symbol_type.value +
                       (" seed" if is_seed else "") +
                       (" unresolved" if sym.file_path == "<unresolved>" else ""),
        }
        elements.append(node_data)

    # Edges
    for edge in graph.edges:
        # Skip edges to/from include nodes
        src = graph.get_symbol(edge.source_id)
        tgt = graph.get_symbol(edge.target_id)
        if not src or not tgt:
            continue
        if src.symbol_type == SymbolType.INCLUDE or \
           tgt.symbol_type == SymbolType.INCLUDE:
            continue

        edge_data = {
            "data": {
                "id": edge.id,
                "source": edge.source_id,
                "target": edge.target_id,
                "type": edge.edge_type.value,
                "label": edge.edge_type.value,
                "color": EDGE_COLORS.get(edge.edge_type, "#9E9E9E"),
                "line_style": EDGE_STYLES.get(edge.edge_type, "solid"),
            },
            "classes": edge.edge_type.value,
        }
        elements.append(edge_data)

    return {
        "elements": elements,
        "stats": graph.to_dict()["stats"],
    }


def to_dot(graph: AnalysisGraph, title: str = "Architecture Graph") -> str:
    """
    Export graph to Graphviz DOT format.
    """
    lines = [
        f'digraph "{title}" {{',
        '  rankdir=TB;',
        '  node [fontname="Inter", fontsize=10, style="filled,rounded"];',
        '  edge [fontname="Inter", fontsize=8];',
        '  bgcolor="#0a0a1a";',
        '',
    ]

    # DOT shape mapping
    dot_shapes = {
        SymbolType.CLASS: "record",
        SymbolType.STRUCT: "record",
        SymbolType.FUNCTION: "ellipse",
        SymbolType.METHOD: "ellipse",
        SymbolType.ENUM: "diamond",
        SymbolType.NAMESPACE: "hexagon",
        SymbolType.MEMBER_VARIABLE: "box",
    }

    for sym in graph.symbols.values():
        if sym.symbol_type == SymbolType.INCLUDE:
            continue

        shape = dot_shapes.get(sym.symbol_type, "box")
        color = SYMBOL_COLORS.get(sym.symbol_type, "#9E9E9E")
        label = sym.display_name.replace('"', '\\"').replace('\n', '\\n')

        # Truncate long labels
        if len(label) > 60:
            label = label[:57] + "..."

        lines.append(
            f'  "{sym.id}" ['
            f'label="{label}", '
            f'shape={shape}, '
            f'fillcolor="{color}", '
            f'fontcolor="white"'
            f'];'
        )

    lines.append('')

    for edge in graph.edges:
        src = graph.get_symbol(edge.source_id)
        tgt = graph.get_symbol(edge.target_id)
        if not src or not tgt:
            continue
        if src.symbol_type == SymbolType.INCLUDE or \
           tgt.symbol_type == SymbolType.INCLUDE:
            continue

        color = EDGE_COLORS.get(edge.edge_type, "#9E9E9E")
        style = "dashed" if edge.edge_type in (EdgeType.CALLS, EdgeType.INCLUDES) \
                else "dotted" if edge.edge_type in (EdgeType.USES_TYPE, EdgeType.REFERENCES) \
                else "solid"

        lines.append(
            f'  "{edge.source_id}" -> "{edge.target_id}" ['
            f'label="{edge.edge_type.value}", '
            f'color="{color}", '
            f'fontcolor="{color}", '
            f'style={style}'
            f'];'
        )

    lines.append('}')
    return '\n'.join(lines)


def to_gexf(graph: AnalysisGraph) -> str:
    """
    Export graph to GEXF format (for Gephi).
    """
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    gexf = ET.Element('gexf', {'xmlns': 'http://www.gexf.net/1.2draft', 'version': '1.2'})
    meta = ET.SubElement(gexf, 'meta')
    creator = ET.SubElement(meta, 'creator')
    creator.text = 'C++ Architecture Analyser'

    graph_el = ET.SubElement(gexf, 'graph', {'mode': 'static', 'defaultedgetype': 'directed'})
    
    # Define node attributes
    attributes = ET.SubElement(graph_el, 'attributes', {'class': 'node'})
    ET.SubElement(attributes, 'attribute', {'id': 'type', 'title': 'Type', 'type': 'string'})
    ET.SubElement(attributes, 'attribute', {'id': 'file', 'title': 'File', 'type': 'string'})
    ET.SubElement(attributes, 'attribute', {'id': 'language', 'title': 'Language', 'type': 'string'})

    nodes_el = ET.SubElement(graph_el, 'nodes')
    for sym in graph.symbols.values():
        if sym.symbol_type == SymbolType.INCLUDE:
            continue
            
        node_el = ET.SubElement(nodes_el, 'node', {'id': sym.id, 'label': sym.name})
        attvalues = ET.SubElement(node_el, 'attvalues')
        ET.SubElement(attvalues, 'attvalue', {'for': 'type', 'value': sym.symbol_type.value})
        ET.SubElement(attvalues, 'attvalue', {'for': 'file', 'value': sym.file_path})
        ET.SubElement(attvalues, 'attvalue', {'for': 'language', 'value': sym.language.value})

    edges_el = ET.SubElement(graph_el, 'edges')
    for edge in graph.edges:
        src = graph.get_symbol(edge.source_id)
        tgt = graph.get_symbol(edge.target_id)
        if not src or not tgt:
            continue
        if src.symbol_type == SymbolType.INCLUDE or tgt.symbol_type == SymbolType.INCLUDE:
            continue
            
        ET.SubElement(edges_el, 'edge', {
            'id': edge.id,
            'source': edge.source_id,
            'target': edge.target_id,
            'label': edge.edge_type.value
        })

    rough_string = ET.tostring(gexf, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def to_summary_text(graph: AnalysisGraph, seed_names: list[str] = None) -> str:
    """
    Generate a human-readable text summary of the graph.
    """
    lines = ["=" * 60]
    lines.append("  C++ Architecture Analysis Report")
    lines.append("=" * 60)

    if seed_names:
        lines.append(f"\n  Seed symbols: {', '.join(seed_names)}")

    stats = graph.to_dict()["stats"]
    lines.append(f"\n  Total nodes: {stats['total_nodes']}")
    lines.append(f"  Total edges: {stats['total_edges']}")

    lines.append("\n  Node types:")
    for t, count in sorted(stats['node_types'].items(), key=lambda x: -x[1]):
        lines.append(f"    {t:25s} {count:>5d}")

    lines.append("\n  Edge types:")
    for t, count in sorted(stats['edge_types'].items(), key=lambda x: -x[1]):
        lines.append(f"    {t:25s} {count:>5d}")

    # List classes with inheritance
    classes = [s for s in graph.symbols.values()
               if s.symbol_type in (SymbolType.CLASS, SymbolType.STRUCT)
               and s.file_path != '<unresolved>']
    if classes:
        lines.append(f"\n{'─' * 60}")
        lines.append("  Classes & Structs")
        lines.append(f"{'─' * 60}")
        for cls in sorted(classes, key=lambda c: c.qualified_name):
            lines.append(f"\n  ● {cls.qualified_name} ({cls.symbol_type.value})")
            lines.append(f"    File: {cls.file_path}:{cls.line}")
            if cls.base_classes:
                lines.append(f"    Bases: {', '.join(cls.base_classes)}")

            # Members
            members = [s for s in graph.symbols.values()
                       if any(e.source_id == cls.id and e.target_id == s.id
                              and e.edge_type == EdgeType.CONTAINS
                              for e in graph.edges)]
            if members:
                methods = [m for m in members if m.symbol_type in
                           (SymbolType.METHOD, SymbolType.CONSTRUCTOR,
                            SymbolType.DESTRUCTOR)]
                fields = [m for m in members if m.symbol_type ==
                          SymbolType.MEMBER_VARIABLE]
                enums = [m for m in members if m.symbol_type ==
                         SymbolType.ENUM]
                if fields:
                    lines.append("    Fields:")
                    for f in fields:
                        acc = f.access.value if f.access != AccessSpecifier.NONE else ""
                        lines.append(f"      {acc:>10s} {f.return_type} {f.name}")
                if methods:
                    lines.append("    Methods:")
                    for m in methods:
                        acc = m.access.value if m.access != AccessSpecifier.NONE else ""
                        virt = " [virtual]" if m.is_virtual else ""
                        lines.append(f"      {acc:>10s} {m.display_name}{virt}")
                if enums:
                    lines.append("    Enums:")
                    for e in enums:
                        lines.append(f"              {e.name}")

    lines.append(f"\n{'=' * 60}")
    return '\n'.join(lines)


# Import here to avoid issues
from .models import AccessSpecifier
