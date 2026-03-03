"""
Symbol index — in-memory storage and querying of extracted symbols.
Supports serialization for caching between runs.
"""

import json
import os
from typing import Optional

from .models import (
    Symbol, Edge, AnalysisGraph, SymbolType, EdgeType,
    AccessSpecifier, Language, Parameter,
)


class SymbolIndex:
    """
    In-memory symbol database wrapping an AnalysisGraph.
    Provides efficient querying and persistence.
    """

    def __init__(self):
        self.graph = AnalysisGraph()
        self._name_index: dict[str, list[str]] = {}  # name -> [symbol_ids]

    def add_symbol(self, symbol: Symbol) -> str:
        """Add a symbol and update indices."""
        sid = self.graph.add_symbol(symbol)
        name_lower = symbol.name.lower()
        if name_lower not in self._name_index:
            self._name_index[name_lower] = []
        if sid not in self._name_index[name_lower]:
            self._name_index[name_lower].append(sid)
        return sid

    def add_edge(self, edge: Edge) -> bool:
        return self.graph.add_edge(edge)

    def merge_graph(self, other: AnalysisGraph):
        """Merge another graph into this index."""
        for sym in other.symbols.values():
            self.add_symbol(sym)
        for edge in other.edges:
            self.add_edge(edge)

    def search(self, pattern: str, exact: bool = False) -> list[Symbol]:
        """Search for symbols by name."""
        if exact:
            pattern_lower = pattern.lower()
            ids = self._name_index.get(pattern_lower, [])
            return [self.graph.symbols[sid] for sid in ids
                    if sid in self.graph.symbols]
        else:
            results = []
            pattern_lower = pattern.lower()
            for name, ids in self._name_index.items():
                if pattern_lower in name:
                    for sid in ids:
                        if sid in self.graph.symbols:
                            results.append(self.graph.symbols[sid])
            return results

    def get_symbol(self, symbol_id: str) -> Optional[Symbol]:
        return self.graph.get_symbol(symbol_id)

    def get_references(self, symbol_id: str) -> list[Edge]:
        """Get all edges involving a symbol (as source or target)."""
        edges = self.graph.get_edges_from(symbol_id)
        edges.extend(self.graph.get_edges_to(symbol_id))
        return edges

    def get_hierarchy(self, symbol_id: str) -> dict:
        """
        Get full inheritance hierarchy for a class.
        Returns { "bases": [...], "derived": [...] }
        """
        bases = []
        derived = []

        # Find base classes (INHERITS edges where this is source)
        for edge in self.graph.get_edges_from(symbol_id, EdgeType.INHERITS):
            base = self.graph.get_symbol(edge.target_id)
            if base:
                bases.append(base)

        # Find derived classes (INHERITS edges where this is target)
        for edge in self.graph.get_edges_to(symbol_id, EdgeType.INHERITS):
            child = self.graph.get_symbol(edge.source_id)
            if child:
                derived.append(child)

        return {"bases": bases, "derived": derived}

    def get_members(self, symbol_id: str) -> list[Symbol]:
        """Get all members contained by a class/namespace."""
        members = []
        for edge in self.graph.get_edges_from(symbol_id, EdgeType.CONTAINS):
            member = self.graph.get_symbol(edge.target_id)
            if member:
                members.append(member)
        return members

    def get_callers(self, symbol_id: str) -> list[Symbol]:
        """Get all functions that call this symbol."""
        callers = []
        for edge in self.graph.get_edges_to(symbol_id, EdgeType.CALLS):
            caller = self.graph.get_symbol(edge.source_id)
            if caller:
                callers.append(caller)
        return callers

    def get_callees(self, symbol_id: str) -> list[Symbol]:
        """Get all functions called by this symbol."""
        callees = []
        for edge in self.graph.get_edges_from(symbol_id, EdgeType.CALLS):
            callee = self.graph.get_symbol(edge.target_id)
            if callee:
                callees.append(callee)
        return callees

    def resolve_unresolved(self):
        """
        Try to resolve placeholder symbols (file_path == '<unresolved>')
        by matching them to real definitions in the index.
        """
        unresolved = {sid: sym for sid, sym in self.graph.symbols.items()
                      if sym.file_path == '<unresolved>'}

        resolved_map: dict[str, str] = {}  # old_id -> real_id

        for uid, usym in unresolved.items():
            # Search for real definitions with the same name
            candidates = [
                s for s in self.search(usym.name, exact=True)
                if s.file_path != '<unresolved>' and s.id != uid
            ]
            if candidates:
                # Pick the best match (prefer same type, then first found)
                best = None
                for c in candidates:
                    if c.symbol_type == usym.symbol_type:
                        best = c
                        break
                if not best:
                    # Try matching by qualified name suffix
                    name_parts = usym.name.split('::')
                    for c in candidates:
                        if c.name == name_parts[-1]:
                            best = c
                            break
                if not best:
                    best = candidates[0]

                resolved_map[uid] = best.id

        # Remap edges
        if resolved_map:
            new_edges = []
            for edge in self.graph.edges:
                new_source = resolved_map.get(edge.source_id, edge.source_id)
                new_target = resolved_map.get(edge.target_id, edge.target_id)
                new_edge = Edge(
                    source_id=new_source,
                    target_id=new_target,
                    edge_type=edge.edge_type,
                    file_path=edge.file_path,
                    line=edge.line,
                    label=edge.label,
                )
                new_edges.append(new_edge)

            # Rebuild edge list
            self.graph.edges = []
            self.graph._edge_set = set()
            for e in new_edges:
                self.graph.add_edge(e)

            # Remove resolved placeholders
            for uid in resolved_map:
                if uid in self.graph.symbols:
                    del self.graph.symbols[uid]

        return len(resolved_map)

    def get_stats(self) -> dict:
        """Get index statistics."""
        unresolved = sum(1 for s in self.graph.symbols.values()
                         if s.file_path == '<unresolved>')
        return {
            "total_symbols": self.graph.node_count,
            "total_edges": self.graph.edge_count,
            "unresolved_symbols": unresolved,
            "resolved_symbols": self.graph.node_count - unresolved,
            "symbol_types": self.graph._count_by_type(),
            "edge_types": self.graph._count_edge_types(),
        }

    def save(self, file_path: str):
        """Save index to JSON file."""
        self.graph.save(file_path)

    def load(self, file_path: str):
        """Load index from JSON file."""
        self.graph = AnalysisGraph.load(file_path)
        # Rebuild name index
        self._name_index.clear()
        for sym in self.graph.symbols.values():
            name_lower = sym.name.lower()
            if name_lower not in self._name_index:
                self._name_index[name_lower] = []
            self._name_index[name_lower].append(sym.id)
