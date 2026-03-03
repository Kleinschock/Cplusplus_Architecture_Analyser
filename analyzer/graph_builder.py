"""
Graph builder — implements the 'seed and expand' algorithm.
Starts from user-provided symbol names and builds a focused subgraph.
"""

import os
import sys
from typing import Optional

from .models import AnalysisGraph, Symbol, Edge, SymbolType, EdgeType
from .scanner import discover_files, search_text, CPP_EXTENSIONS
from .cpp_parser import CppParser, parse_project_files
from .symbol_index import SymbolIndex


class GraphBuilder:
    """
    Builds an analysis graph using the 'seed and expand' strategy:
    1. Scan project for files containing the seed symbol names
    2. Parse those files to extract semantic info
    3. Expand the graph by following relationships
    4. Resolve cross-references between files
    """

    def __init__(self, project_path: str, extensions: Optional[set[str]] = None):
        self.project_path = os.path.abspath(project_path)
        self.extensions = extensions or CPP_EXTENSIONS
        self.index = SymbolIndex()
        self.parser = CppParser()
        self._parsed_files: set[str] = set()
        self._all_files: Optional[list[str]] = None

    def _get_all_files(self) -> list[str]:
        """Get all source files in the project (cached)."""
        if self._all_files is None:
            self._all_files = discover_files(self.project_path, self.extensions)
        return self._all_files

    def _parse_file(self, file_path: str):
        """Parse a file if not already parsed."""
        norm_path = os.path.normpath(os.path.abspath(file_path))
        if norm_path in self._parsed_files:
            return
        self._parsed_files.add(norm_path)
        file_graph = self.parser.parse_file(norm_path)
        self.index.merge_graph(file_graph)

    def analyze(
        self,
        seed_symbols: list[str],
        depth: int = 2,
        progress_callback=None,
    ) -> AnalysisGraph:
        """
        Full analysis pipeline:
        1. Find files containing seed symbols
        2. Parse those files
        3. Expand to related files (up to 'depth' levels)
        4. Resolve cross-references
        5. Build focused subgraph

        Args:
            seed_symbols: List of symbol names to search for
            depth: Number of hops to expand (1 = only direct, 2+ = transitive)
            progress_callback: Optional callback(stage, detail) for progress

        Returns:
            AnalysisGraph containing the focused subgraph
        """
        def progress(stage: str, detail: str = ""):
            if progress_callback:
                progress_callback(stage, detail)
            print(f"  [{stage}] {detail}", file=sys.stderr)

        all_files = self._get_all_files()
        progress("scan", f"Found {len(all_files)} source files in project")

        # Phase 1: Find files containing seed symbols
        relevant_files: set[str] = set()
        for sym_name in seed_symbols:
            progress("search", f"Searching for '{sym_name}'...")
            matches = search_text(sym_name, all_files, whole_word=True)
            matched_files = set(m.file_path for m in matches)
            progress("search", f"  Found '{sym_name}' in {len(matched_files)} files")
            relevant_files.update(matched_files)

        progress("parse", f"Parsing {len(relevant_files)} files...")
        for i, fp in enumerate(sorted(relevant_files)):
            if (i + 1) % 50 == 0:
                progress("parse", f"  {i + 1}/{len(relevant_files)}")
            self._parse_file(fp)

        # Phase 2: Expand graph by following relationships
        for hop in range(depth - 1):
            progress("expand", f"Expansion hop {hop + 1}/{depth - 1}...")
            new_files = self._find_related_files(seed_symbols, all_files)
            new_count = 0
            for fp in new_files:
                norm = os.path.normpath(os.path.abspath(fp))
                if norm not in self._parsed_files:
                    self._parse_file(norm)
                    new_count += 1
            progress("expand", f"  Parsed {new_count} additional files")
            if new_count == 0:
                break

        # Phase 3: Resolve cross-references
        resolved = self.index.resolve_unresolved()
        progress("resolve", f"Resolved {resolved} cross-references")

        # Phase 4: Build focused subgraph
        progress("build", "Building focused subgraph...")
        subgraph = self._build_seed_subgraph(seed_symbols, depth)

        stats = self.index.get_stats()
        progress("done", f"Graph: {subgraph.node_count} nodes, "
                         f"{subgraph.edge_count} edges "
                         f"(index: {stats['total_symbols']} symbols total)")

        return subgraph

    def index_full_project(self, progress_callback=None) -> SymbolIndex:
        """
        Parse ALL files in the project. Use for pre-building a complete index.
        """
        def progress(stage, detail=""):
            if progress_callback:
                progress_callback(stage, detail)
            print(f"  [{stage}] {detail}", file=sys.stderr)

        all_files = self._get_all_files()
        progress("index", f"Indexing {len(all_files)} files...")

        for i, fp in enumerate(all_files):
            if (i + 1) % 100 == 0:
                progress("index", f"  {i + 1}/{len(all_files)}")
            self._parse_file(fp)

        resolved = self.index.resolve_unresolved()
        progress("resolve", f"Resolved {resolved} cross-references")

        stats = self.index.get_stats()
        progress("done", f"Index complete: {stats['total_symbols']} symbols, "
                         f"{stats['total_edges']} edges")

        return self.index

    def _find_related_files(self, seed_symbols: list[str],
                            all_files: list[str]) -> set[str]:
        """Find files containing symbols related to the seeds."""
        related_names: set[str] = set()

        for seed_name in seed_symbols:
            # Find matching symbols in current index
            matches = self.index.search(seed_name)
            for sym in matches:
                # Collect base classes
                related_names.update(sym.base_classes)
                # Collect type names from members
                members = self.index.get_members(sym.id)
                for member in members:
                    if member.return_type and member.return_type != "unknown":
                        clean = member.return_type.replace('const ', '')\
                                .replace('&', '').replace('*', '').strip()
                        if clean:
                            related_names.add(clean)
                # Collect callee names
                callees = self.index.get_callees(sym.id)
                for callee in callees:
                    related_names.add(callee.name)

        # Search for those related names
        new_files: set[str] = set()
        for name in related_names:
            if len(name) < 3:  # skip short/ambiguous names
                continue
            matches = search_text(name, all_files, whole_word=True)
            for m in matches:
                new_files.add(m.file_path)

        return new_files

    def _build_seed_subgraph(self, seed_symbols: list[str],
                             depth: int) -> AnalysisGraph:
        """
        Build a subgraph centered on the seed symbols,
        expanding 'depth' hops along all edge types.
        """
        # Find seed symbol IDs
        seed_ids: set[str] = set()
        for name in seed_symbols:
            matches = self.index.search(name)
            for sym in matches:
                # Skip unresolved placeholders
                if sym.file_path != '<unresolved>':
                    seed_ids.add(sym.id)

        if not seed_ids:
            # If no resolved matches, include unresolved too
            for name in seed_symbols:
                matches = self.index.search(name)
                for sym in matches:
                    seed_ids.add(sym.id)

        # BFS expansion
        included_ids: set[str] = set(seed_ids)
        frontier: set[str] = set(seed_ids)

        for _ in range(depth):
            next_frontier: set[str] = set()
            for sid in frontier:
                connected = self.index.graph.get_connected_symbols(sid)
                for cid in connected:
                    if cid not in included_ids:
                        included_ids.add(cid)
                        next_frontier.add(cid)
            frontier = next_frontier
            if not frontier:
                break

        return self.index.graph.get_subgraph(included_ids)
