"""
Data models for the C++ Architecture Analyser.
Defines Symbol, Edge, and AnalysisGraph types used throughout the system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import json
import hashlib


class SymbolType(Enum):
    """Types of symbols that can be extracted from C++ code."""
    CLASS = "class"
    STRUCT = "struct"
    FUNCTION = "function"
    METHOD = "method"
    MEMBER_VARIABLE = "member_variable"
    ENUM = "enum"
    ENUM_VALUE = "enum_value"
    NAMESPACE = "namespace"
    TYPEDEF = "typedef"
    USING_ALIAS = "using_alias"
    MACRO = "macro"
    TEMPLATE_CLASS = "template_class"
    TEMPLATE_FUNCTION = "template_function"
    CONSTRUCTOR = "constructor"
    DESTRUCTOR = "destructor"
    GLOBAL_VARIABLE = "global_variable"
    PARAMETER = "parameter"
    FORWARD_DECLARATION = "forward_declaration"
    INCLUDE = "include"
    UNKNOWN = "unknown"


class EdgeType(Enum):
    """Types of relationships between symbols."""
    CONTAINS = "contains"             # class/namespace contains member
    INHERITS = "inherits"             # child → base class
    CALLS = "calls"                   # function calls function
    USES_TYPE = "uses_type"           # function/variable uses a type
    REFERENCES = "references"         # generic reference
    OVERRIDES = "overrides"           # method overrides base method
    INCLUDES = "includes"             # file includes file
    INSTANTIATES = "instantiates"     # creates an instance of a type
    RETURNS_TYPE = "returns_type"     # function returns a type
    PARAMETER_TYPE = "parameter_type" # function takes a type as parameter


class AccessSpecifier(Enum):
    """C++ access specifiers."""
    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    NONE = "none"  # for non-member symbols


class Language(Enum):
    """Programming languages supported by the analyser."""
    CPP = "cpp"
    PYTHON = "python"
    TCL = "tcl"
    UNKNOWN = "unknown"


@dataclass
class Parameter:
    """A function/method parameter."""
    name: str
    type_name: str
    default_value: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"name": self.name, "type": self.type_name}
        if self.default_value:
            d["default"] = self.default_value
        return d


@dataclass
class Symbol:
    """
    A code symbol (class, function, variable, etc.) with its metadata.
    """
    name: str
    symbol_type: SymbolType
    file_path: str
    line: int
    column: int = 0
    end_line: int = 0
    language: Language = Language.CPP
    qualified_name: str = ""
    signature: str = ""
    return_type: str = ""
    parameters: list[Parameter] = field(default_factory=list)
    access: AccessSpecifier = AccessSpecifier.NONE
    base_classes: list[str] = field(default_factory=list)
    template_params: list[str] = field(default_factory=list)
    is_virtual: bool = False
    is_static: bool = False
    is_const: bool = False
    is_override: bool = False
    is_pure_virtual: bool = False
    documentation: str = ""
    _id: str = ""

    def __post_init__(self):
        if not self.qualified_name:
            self.qualified_name = self.name
        if not self._id:
            # Generate unique ID from qualified name + file + line
            raw = f"{self.qualified_name}:{self.file_path}:{self.line}"
            self._id = hashlib.md5(raw.encode()).hexdigest()[:12]

    @property
    def id(self) -> str:
        return self._id

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        if self.signature:
            return self.signature
        if self.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD,
                                 SymbolType.CONSTRUCTOR, SymbolType.DESTRUCTOR):
            params = ", ".join(f"{p.type_name} {p.name}" for p in self.parameters)
            ret = f"{self.return_type} " if self.return_type else ""
            return f"{ret}{self.name}({params})"
        return self.name

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "type": self.symbol_type.value,
            "file": self.file_path,
            "line": self.line,
            "end_line": self.end_line,
            "column": self.column,
            "language": self.language.value,
            "signature": self.signature,
            "display_name": self.display_name,
            "return_type": self.return_type,
            "parameters": [p.to_dict() for p in self.parameters],
            "access": self.access.value,
            "base_classes": self.base_classes,
            "template_params": self.template_params,
            "is_virtual": self.is_virtual,
            "is_static": self.is_static,
            "is_const": self.is_const,
            "is_override": self.is_override,
            "is_pure_virtual": self.is_pure_virtual,
            "documentation": self.documentation,
        }


@dataclass
class Edge:
    """A relationship between two symbols."""
    source_id: str
    target_id: str
    edge_type: EdgeType
    file_path: str = ""
    line: int = 0
    label: str = ""

    @property
    def id(self) -> str:
        raw = f"{self.source_id}:{self.target_id}:{self.edge_type.value}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source_id,
            "target": self.target_id,
            "type": self.edge_type.value,
            "file": self.file_path,
            "line": self.line,
            "label": self.label or self.edge_type.value,
        }


class AnalysisGraph:
    """
    The complete analysis graph containing symbols and their relationships.
    Provides methods for querying and manipulation.
    """

    def __init__(self):
        self.symbols: dict[str, Symbol] = {}
        self.edges: list[Edge] = []
        self._edge_set: set[str] = set()  # for dedup

    def add_symbol(self, symbol: Symbol) -> str:
        """Add a symbol to the graph. Returns the symbol ID."""
        self.symbols[symbol.id] = symbol
        return symbol.id

    def add_edge(self, edge: Edge) -> bool:
        """Add an edge. Returns False if duplicate."""
        edge_key = f"{edge.source_id}:{edge.target_id}:{edge.edge_type.value}"
        if edge_key in self._edge_set:
            return False
        self._edge_set.add(edge_key)
        self.edges.append(edge)
        return True

    def get_symbol(self, symbol_id: str) -> Optional[Symbol]:
        return self.symbols.get(symbol_id)

    def find_symbols_by_name(self, name: str, exact: bool = False) -> list[Symbol]:
        """Find symbols matching a name pattern."""
        results = []
        name_lower = name.lower()
        for sym in self.symbols.values():
            if exact:
                if sym.name == name or sym.qualified_name == name:
                    results.append(sym)
            else:
                if (name_lower in sym.name.lower() or
                        name_lower in sym.qualified_name.lower()):
                    results.append(sym)
        return results

    def find_symbols_by_type(self, symbol_type: SymbolType) -> list[Symbol]:
        return [s for s in self.symbols.values() if s.symbol_type == symbol_type]

    def get_edges_from(self, symbol_id: str,
                       edge_type: Optional[EdgeType] = None) -> list[Edge]:
        """Get all edges originating from a symbol."""
        return [e for e in self.edges
                if e.source_id == symbol_id and
                (edge_type is None or e.edge_type == edge_type)]

    def get_edges_to(self, symbol_id: str,
                     edge_type: Optional[EdgeType] = None) -> list[Edge]:
        """Get all edges pointing to a symbol."""
        return [e for e in self.edges
                if e.target_id == symbol_id and
                (edge_type is None or e.edge_type == edge_type)]

    def get_connected_symbols(self, symbol_id: str) -> set[str]:
        """Get IDs of all symbols connected to the given symbol."""
        connected = set()
        for e in self.edges:
            if e.source_id == symbol_id:
                connected.add(e.target_id)
            if e.target_id == symbol_id:
                connected.add(e.source_id)
        return connected

    def get_subgraph(self, symbol_ids: set[str]) -> "AnalysisGraph":
        """Extract a subgraph containing only the specified symbols."""
        sub = AnalysisGraph()
        for sid in symbol_ids:
            if sid in self.symbols:
                sub.add_symbol(self.symbols[sid])
        for edge in self.edges:
            if edge.source_id in symbol_ids and edge.target_id in symbol_ids:
                sub.add_edge(edge)
        return sub

    @property
    def node_count(self) -> int:
        return len(self.symbols)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def to_dict(self) -> dict:
        return {
            "nodes": [s.to_dict() for s in self.symbols.values()],
            "edges": [e.to_dict() for e in self.edges],
            "stats": {
                "total_nodes": self.node_count,
                "total_edges": self.edge_count,
                "node_types": self._count_by_type(),
                "edge_types": self._count_edge_types(),
            }
        }

    def _count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.symbols.values():
            t = s.symbol_type.value
            counts[t] = counts.get(t, 0) + 1
        return counts

    def _count_edge_types(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.edges:
            t = e.edge_type.value
            counts[t] = counts.get(t, 0) + 1
        return counts

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, file_path: str):
        """Save graph to JSON file."""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, file_path: str) -> "AnalysisGraph":
        """Load graph from JSON file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.loads(f.read())
        graph = cls()
        for node_data in data.get("nodes", []):
            params = [Parameter(**p) for p in node_data.get("parameters", [])]
            sym = Symbol(
                name=node_data["name"],
                symbol_type=SymbolType(node_data["type"]),
                file_path=node_data["file"],
                line=node_data["line"],
                column=node_data.get("column", 0),
                end_line=node_data.get("end_line", 0),
                language=Language(node_data.get("language", "cpp")),
                qualified_name=node_data.get("qualified_name", ""),
                signature=node_data.get("signature", ""),
                return_type=node_data.get("return_type", ""),
                parameters=params,
                access=AccessSpecifier(node_data.get("access", "none")),
                base_classes=node_data.get("base_classes", []),
                template_params=node_data.get("template_params", []),
                is_virtual=node_data.get("is_virtual", False),
                is_static=node_data.get("is_static", False),
                is_const=node_data.get("is_const", False),
                is_override=node_data.get("is_override", False),
                is_pure_virtual=node_data.get("is_pure_virtual", False),
                documentation=node_data.get("documentation", ""),
            )
            graph.add_symbol(sym)
        for edge_data in data.get("edges", []):
            edge = Edge(
                source_id=edge_data["source"],
                target_id=edge_data["target"],
                edge_type=EdgeType(edge_data["type"]),
                file_path=edge_data.get("file", ""),
                line=edge_data.get("line", 0),
                label=edge_data.get("label", ""),
            )
            graph.add_edge(edge)
        return graph
