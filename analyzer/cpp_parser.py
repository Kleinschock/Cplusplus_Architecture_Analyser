"""
C++ parser using tree-sitter for structural analysis.
Extracts classes, functions, enums, namespaces, variables, and their relationships.
"""

import os
from typing import Optional
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser, Node

from .models import (
    Symbol, Edge, SymbolType, EdgeType, AccessSpecifier,
    Language as Lang, Parameter, AnalysisGraph,
)

# ---- Initialize tree-sitter ----
CPP_LANGUAGE = Language(tscpp.language())


def _create_parser() -> Parser:
    parser = Parser(CPP_LANGUAGE)
    return parser


def _get_text(node: Node, source: bytes) -> str:
    """Extract text content of an AST node."""
    return source[node.start_byte:node.end_byte].decode('utf-8', errors='replace')


def _find_children_by_type(node: Node, type_name: str) -> list[Node]:
    """Find all direct children of a given type."""
    return [c for c in node.children if c.type == type_name]


def _find_child_by_type(node: Node, type_name: str) -> Optional[Node]:
    """Find first direct child of a given type."""
    for c in node.children:
        if c.type == type_name:
            return c
    return None


def _find_descendants_by_type(node: Node, type_name: str) -> list[Node]:
    """Find all descendants of a given type (recursive)."""
    results = []
    for c in node.children:
        if c.type == type_name:
            results.append(c)
        results.extend(_find_descendants_by_type(c, type_name))
    return results


def _determine_access(node: Node, source: bytes) -> AccessSpecifier:
    """Determine the access specifier for a member by looking at preceding siblings."""
    current = node.prev_named_sibling
    while current:
        if current.type == 'access_specifier':
            text = _get_text(current, source).rstrip(':').strip()
            try:
                return AccessSpecifier(text)
            except ValueError:
                pass
        current = current.prev_named_sibling
    return AccessSpecifier.PRIVATE  # C++ default for classes


class CppParser:
    """
    Parses C++ source files using tree-sitter and extracts symbols and edges.
    """

    def __init__(self):
        self.parser = _create_parser()

    def parse_file(self, file_path: str, graph: Optional[AnalysisGraph] = None) -> AnalysisGraph:
        """
        Parse a C++ source file and extract all symbols and relationships.

        Args:
            file_path: Path to the .cpp/.h file
            graph: Existing graph to add to (or creates a new one)

        Returns:
            AnalysisGraph with extracted symbols and edges
        """
        if graph is None:
            graph = AnalysisGraph()

        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                source_code = f.read()
        except (OSError, PermissionError):
            return graph

        source_bytes = source_code.encode('utf-8')
        tree = self.parser.parse(source_bytes)
        root = tree.root_node

        # Normalize file path
        file_path = os.path.normpath(os.path.abspath(file_path))

        # Extract includes
        self._extract_includes(root, source_bytes, file_path, graph)

        # Walk top-level declarations
        self._extract_from_node(root, source_bytes, file_path, graph,
                                namespace_stack=[], parent_symbol=None)

        return graph

    def _extract_from_node(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        graph: AnalysisGraph,
        namespace_stack: list[str],
        parent_symbol: Optional[Symbol],
    ):
        """Recursively extract symbols from AST nodes."""
        for child in node.children:
            if child.type == 'namespace_definition':
                self._extract_namespace(child, source, file_path, graph,
                                        namespace_stack, parent_symbol)
            elif child.type in ('class_specifier', 'struct_specifier'):
                self._extract_class(child, source, file_path, graph,
                                    namespace_stack, parent_symbol)
            elif child.type == 'enum_specifier':
                self._extract_enum(child, source, file_path, graph,
                                   namespace_stack, parent_symbol)
            elif child.type == 'function_definition':
                self._extract_function(child, source, file_path, graph,
                                       namespace_stack, parent_symbol, is_definition=True)
            elif child.type == 'declaration':
                self._extract_declaration(child, source, file_path, graph,
                                          namespace_stack, parent_symbol)
            elif child.type == 'template_declaration':
                self._extract_template(child, source, file_path, graph,
                                       namespace_stack, parent_symbol)
            elif child.type == 'type_definition':
                self._extract_typedef(child, source, file_path, graph,
                                      namespace_stack, parent_symbol)
            elif child.type == 'using_declaration' or child.type == 'alias_declaration':
                self._extract_using(child, source, file_path, graph,
                                    namespace_stack, parent_symbol)

    def _extract_includes(self, root: Node, source: bytes, file_path: str,
                          graph: AnalysisGraph):
        """Extract #include directives."""
        for node in _find_descendants_by_type(root, 'preproc_include'):
            path_node = _find_child_by_type(node, 'string_literal') or \
                        _find_child_by_type(node, 'system_lib_string')
            if path_node:
                include_path = _get_text(path_node, source).strip('"<>')
                sym = Symbol(
                    name=include_path,
                    symbol_type=SymbolType.INCLUDE,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                    column=node.start_point[1],
                    language=Lang.CPP,
                    qualified_name=include_path,
                )
                graph.add_symbol(sym)

    def _extract_namespace(self, node: Node, source: bytes, file_path: str,
                           graph: AnalysisGraph, namespace_stack: list[str],
                           parent_symbol: Optional[Symbol]):
        """Extract a namespace definition."""
        name_node = _find_child_by_type(node, 'namespace_identifier') or \
                    _find_child_by_type(node, 'identifier')
        if name_node is None:
            # Anonymous namespace
            name = "<anonymous>"
        else:
            name = _get_text(name_node, source)

        qualified = "::".join(namespace_stack + [name]) if name != "<anonymous>" else \
                    "::".join(namespace_stack + [name])

        sym = Symbol(
            name=name,
            symbol_type=SymbolType.NAMESPACE,
            file_path=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            column=node.start_point[1],
            language=Lang.CPP,
            qualified_name=qualified,
        )
        graph.add_symbol(sym)

        if parent_symbol:
            graph.add_edge(Edge(
                source_id=parent_symbol.id,
                target_id=sym.id,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            ))

        # Process namespace body
        body = _find_child_by_type(node, 'declaration_list')
        if body:
            new_stack = namespace_stack + [name] if name != "<anonymous>" else namespace_stack
            self._extract_from_node(body, source, file_path, graph,
                                    new_stack, sym)

    def _extract_class(self, node: Node, source: bytes, file_path: str,
                       graph: AnalysisGraph, namespace_stack: list[str],
                       parent_symbol: Optional[Symbol]):
        """Extract a class or struct definition with members."""
        is_struct = node.type == 'struct_specifier'

        # Get class name
        name_node = _find_child_by_type(node, 'type_identifier')
        if name_node is None:
            # Anonymous class/struct, skip
            return

        name = _get_text(name_node, source)
        qualified = "::".join(namespace_stack + [name])

        sym_type = SymbolType.STRUCT if is_struct else SymbolType.CLASS

        # Extract base classes
        base_classes = []
        base_clause = _find_child_by_type(node, 'base_class_clause')
        if base_clause:
            for base_spec in base_clause.children:
                if base_spec.type == 'base_class_specifier':
                    type_node = _find_child_by_type(base_spec, 'type_identifier') or \
                                _find_child_by_type(base_spec, 'qualified_identifier')
                    if type_node:
                        base_classes.append(_get_text(type_node, source))

        sym = Symbol(
            name=name,
            symbol_type=sym_type,
            file_path=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            column=node.start_point[1],
            language=Lang.CPP,
            qualified_name=qualified,
            base_classes=base_classes,
            access=AccessSpecifier.NONE,
        )
        graph.add_symbol(sym)

        # Link to parent
        if parent_symbol:
            graph.add_edge(Edge(
                source_id=parent_symbol.id,
                target_id=sym.id,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            ))

        # Create INHERITS edges (target will be resolved later if base class
        # is in the index, for now we create a placeholder symbol)
        for base_name in base_classes:
            base_sym = Symbol(
                name=base_name,
                symbol_type=SymbolType.CLASS,
                file_path="<unresolved>",
                line=0,
                language=Lang.CPP,
                qualified_name=base_name,
            )
            base_id = graph.add_symbol(base_sym)
            graph.add_edge(Edge(
                source_id=sym.id,
                target_id=base_id,
                edge_type=EdgeType.INHERITS,
                file_path=file_path,
                line=node.start_point[0] + 1,
                label=f"inherits {base_name}",
            ))

        # Process class body (field_declaration_list)
        body = _find_child_by_type(node, 'field_declaration_list')
        if body:
            default_access = AccessSpecifier.PUBLIC if is_struct else AccessSpecifier.PRIVATE
            self._extract_class_members(body, source, file_path, graph,
                                        namespace_stack + [name], sym,
                                        default_access)

    def _extract_class_members(self, body: Node, source: bytes, file_path: str,
                                graph: AnalysisGraph, namespace_stack: list[str],
                                class_symbol: Symbol, default_access: AccessSpecifier):
        """Extract members from a class body."""
        current_access = default_access

        for child in body.children:
            if child.type == 'access_specifier':
                text = _get_text(child, source).rstrip(':').strip()
                try:
                    current_access = AccessSpecifier(text)
                except ValueError:
                    pass
                continue

            if child.type == 'field_declaration':
                self._extract_field(child, source, file_path, graph,
                                    namespace_stack, class_symbol, current_access)
            elif child.type == 'function_definition':
                self._extract_method(child, source, file_path, graph,
                                     namespace_stack, class_symbol, current_access,
                                     is_definition=True)
            elif child.type == 'declaration':
                # Could be a method declaration or a static member
                self._extract_class_declaration(child, source, file_path, graph,
                                                namespace_stack, class_symbol,
                                                current_access)
            elif child.type in ('class_specifier', 'struct_specifier'):
                self._extract_class(child, source, file_path, graph,
                                    namespace_stack, class_symbol)
            elif child.type == 'enum_specifier':
                self._extract_enum(child, source, file_path, graph,
                                   namespace_stack, class_symbol)
            elif child.type == 'template_declaration':
                self._extract_template(child, source, file_path, graph,
                                       namespace_stack, class_symbol)
            elif child.type == 'type_definition':
                self._extract_typedef(child, source, file_path, graph,
                                      namespace_stack, class_symbol)
            elif child.type == 'using_declaration' or child.type == 'alias_declaration':
                self._extract_using(child, source, file_path, graph,
                                    namespace_stack, class_symbol)
            elif child.type == 'friend_declaration':
                pass  # Skip friend declarations for now

    def _extract_field(self, node: Node, source: bytes, file_path: str,
                       graph: AnalysisGraph, namespace_stack: list[str],
                       class_symbol: Symbol, access: AccessSpecifier):
        """Extract a member variable (field_declaration)."""
        # Check if this is actually a method declaration (has a function_declarator)
        func_declarator = _find_descendants_by_type(node, 'function_declarator')
        if func_declarator:
            self._extract_method_from_field(node, source, file_path, graph,
                                            namespace_stack, class_symbol,
                                            access)
            return

        # Type
        type_node = _find_child_by_type(node, 'type_identifier') or \
                    _find_child_by_type(node, 'primitive_type') or \
                    _find_child_by_type(node, 'qualified_identifier') or \
                    _find_child_by_type(node, 'template_type') or \
                    _find_child_by_type(node, 'sized_type_specifier')
        type_name = _get_text(type_node, source) if type_node else "unknown"

        # Handle static
        is_static = False
        for c in node.children:
            if c.type == 'storage_class_specifier' and _get_text(c, source) == 'static':
                is_static = True

        # Declarators (there can be multiple: int a, b;)
        declarators = _find_children_by_type(node, 'field_identifier')
        if not declarators:
            # Try finding in nested declarators (pointers, references, etc.)
            for decl in node.children:
                if decl.type in ('pointer_declarator', 'reference_declarator',
                                 'init_declarator'):
                    ids = _find_descendants_by_type(decl, 'field_identifier')
                    declarators.extend(ids)

        for decl in declarators:
            field_name = _get_text(decl, source)
            qualified = "::".join(namespace_stack + [field_name])

            sym = Symbol(
                name=field_name,
                symbol_type=SymbolType.MEMBER_VARIABLE,
                file_path=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                column=decl.start_point[1],
                language=Lang.CPP,
                qualified_name=qualified,
                return_type=type_name,
                access=access,
                is_static=is_static,
            )
            sym_id = graph.add_symbol(sym)

            # CONTAINS edge
            graph.add_edge(Edge(
                source_id=class_symbol.id,
                target_id=sym_id,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            ))

            # USES_TYPE edge
            if type_name != "unknown":
                self._add_type_usage_edge(graph, sym, type_name, file_path,
                                          node.start_point[0] + 1)

    def _extract_method_from_field(self, node: Node, source: bytes, file_path: str,
                                    graph: AnalysisGraph, namespace_stack: list[str],
                                    class_symbol: Symbol, access: AccessSpecifier):
        """Extract a method declaration from a field_declaration node."""
        # Return type
        type_node = _find_child_by_type(node, 'type_identifier') or \
                    _find_child_by_type(node, 'primitive_type') or \
                    _find_child_by_type(node, 'qualified_identifier') or \
                    _find_child_by_type(node, 'template_type')
        return_type = _get_text(type_node, source) if type_node else ""

        # Check for virtual/static/const
        full_text = _get_text(node, source)
        is_virtual = 'virtual' in full_text.split('(')[0]
        is_static = 'static' in full_text.split('(')[0]
        is_override = 'override' in full_text
        is_pure_virtual = '= 0' in full_text
        is_const = ') const' in full_text or ')const' in full_text

        # Find the function declarator
        func_decls = _find_descendants_by_type(node, 'function_declarator')
        if not func_decls:
            return

        func_decl = func_decls[0]

        # Method name
        name_node = _find_child_by_type(func_decl, 'field_identifier') or \
                    _find_child_by_type(func_decl, 'identifier') or \
                    _find_child_by_type(func_decl, 'destructor_name') or \
                    _find_child_by_type(func_decl, 'operator_name') or \
                    _find_child_by_type(func_decl, 'qualified_identifier')
        if not name_node:
            return

        name = _get_text(name_node, source)

        # Determine symbol type
        if name.startswith('~'):
            sym_type = SymbolType.DESTRUCTOR
        elif name == class_symbol.name:
            sym_type = SymbolType.CONSTRUCTOR
            return_type = ""
        else:
            sym_type = SymbolType.METHOD

        # Parameters
        params = self._extract_parameters(func_decl, source)

        qualified = "::".join(namespace_stack + [name])
        param_sig = ", ".join(f"{p.type_name} {p.name}" for p in params)
        signature = f"{return_type + ' ' if return_type else ''}{qualified}({param_sig})"
        if is_const:
            signature += " const"
        if is_pure_virtual:
            signature += " = 0"

        sym = Symbol(
            name=name,
            symbol_type=sym_type,
            file_path=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            column=node.start_point[1],
            language=Lang.CPP,
            qualified_name=qualified,
            signature=signature,
            return_type=return_type,
            parameters=params,
            access=access,
            is_virtual=is_virtual,
            is_static=is_static,
            is_const=is_const,
            is_override=is_override,
            is_pure_virtual=is_pure_virtual,
        )
        sym_id = graph.add_symbol(sym)

        graph.add_edge(Edge(
            source_id=class_symbol.id,
            target_id=sym_id,
            edge_type=EdgeType.CONTAINS,
            file_path=file_path,
            line=node.start_point[0] + 1,
        ))

    def _extract_method(self, node: Node, source: bytes, file_path: str,
                        graph: AnalysisGraph, namespace_stack: list[str],
                        class_symbol: Symbol, access: AccessSpecifier,
                        is_definition: bool = True):
        """Extract a method definition from within a class body."""
        # Get declarator
        declarator = _find_child_by_type(node, 'function_declarator')
        if not declarator:
            return

        # Return type
        type_node = _find_child_by_type(node, 'type_identifier') or \
                    _find_child_by_type(node, 'primitive_type') or \
                    _find_child_by_type(node, 'qualified_identifier') or \
                    _find_child_by_type(node, 'template_type')
        return_type = _get_text(type_node, source) if type_node else ""

        # Method name
        name_node = _find_child_by_type(declarator, 'field_identifier') or \
                    _find_child_by_type(declarator, 'identifier') or \
                    _find_child_by_type(declarator, 'destructor_name') or \
                    _find_child_by_type(declarator, 'qualified_identifier')
        if not name_node:
            return

        name = _get_text(name_node, source)

        # Determine type
        if name.startswith('~'):
            sym_type = SymbolType.DESTRUCTOR
        elif name == class_symbol.name:
            sym_type = SymbolType.CONSTRUCTOR
            return_type = ""
        else:
            sym_type = SymbolType.METHOD

        # Check qualifiers
        full_text = _get_text(node, source)
        is_virtual = any(
            c.type == 'virtual' or
            (c.type == 'type_qualifier' and _get_text(c, source) == 'virtual')
            for c in node.children
        ) or 'virtual ' in full_text.split(name)[0]
        is_static = any(
            c.type == 'storage_class_specifier' and _get_text(c, source) == 'static'
            for c in node.children
        )
        is_const = ') const' in full_text
        is_override = 'override' in full_text

        params = self._extract_parameters(declarator, source)
        qualified = "::".join(namespace_stack + [name])

        param_sig = ", ".join(f"{p.type_name} {p.name}" for p in params)
        signature = f"{return_type + ' ' if return_type else ''}{qualified}({param_sig})"
        if is_const:
            signature += " const"

        sym = Symbol(
            name=name,
            symbol_type=sym_type,
            file_path=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            column=node.start_point[1],
            language=Lang.CPP,
            qualified_name=qualified,
            signature=signature,
            return_type=return_type,
            parameters=params,
            access=access,
            is_virtual=is_virtual,
            is_static=is_static,
            is_const=is_const,
            is_override=is_override,
        )
        sym_id = graph.add_symbol(sym)

        graph.add_edge(Edge(
            source_id=class_symbol.id,
            target_id=sym_id,
            edge_type=EdgeType.CONTAINS,
            file_path=file_path,
            line=node.start_point[0] + 1,
        ))

        # Extract references from the function body
        body = _find_child_by_type(node, 'compound_statement')
        if body:
            self._extract_references(body, source, file_path, graph, sym)

    def _extract_function(self, node: Node, source: bytes, file_path: str,
                          graph: AnalysisGraph, namespace_stack: list[str],
                          parent_symbol: Optional[Symbol],
                          is_definition: bool = True):
        """Extract a free function definition."""
        declarator = _find_child_by_type(node, 'function_declarator')
        if not declarator:
            return

        # Return type
        type_node = _find_child_by_type(node, 'type_identifier') or \
                    _find_child_by_type(node, 'primitive_type') or \
                    _find_child_by_type(node, 'qualified_identifier') or \
                    _find_child_by_type(node, 'template_type')
        return_type = _get_text(type_node, source) if type_node else ""

        # Function name (could be qualified for out-of-class definitions)
        name_node = _find_child_by_type(declarator, 'identifier') or \
                    _find_child_by_type(declarator, 'qualified_identifier') or \
                    _find_child_by_type(declarator, 'field_identifier') or \
                    _find_child_by_type(declarator, 'destructor_name')
        if not name_node:
            return

        name = _get_text(name_node, source)

        # Check if it's an out-of-class method definition (e.g., MyClass::method)
        if '::' in name:
            sym_type = SymbolType.METHOD
        else:
            sym_type = SymbolType.FUNCTION

        is_static = any(
            c.type == 'storage_class_specifier' and _get_text(c, source) == 'static'
            for c in node.children
        )

        params = self._extract_parameters(declarator, source)
        qualified = "::".join(namespace_stack + [name]) if namespace_stack else name

        param_sig = ", ".join(f"{p.type_name} {p.name}" for p in params)
        signature = f"{return_type + ' ' if return_type else ''}{qualified}({param_sig})"

        sym = Symbol(
            name=name,
            symbol_type=sym_type,
            file_path=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            column=node.start_point[1],
            language=Lang.CPP,
            qualified_name=qualified,
            signature=signature,
            return_type=return_type,
            parameters=params,
            access=AccessSpecifier.NONE,
            is_static=is_static,
        )
        sym_id = graph.add_symbol(sym)

        if parent_symbol:
            graph.add_edge(Edge(
                source_id=parent_symbol.id,
                target_id=sym_id,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            ))

        # Extract references
        body = _find_child_by_type(node, 'compound_statement')
        if body:
            self._extract_references(body, source, file_path, graph, sym)

    def _extract_enum(self, node: Node, source: bytes, file_path: str,
                      graph: AnalysisGraph, namespace_stack: list[str],
                      parent_symbol: Optional[Symbol]):
        """Extract an enum definition with its values."""
        name_node = _find_child_by_type(node, 'type_identifier')
        if not name_node:
            return  # anonymous enum

        name = _get_text(name_node, source)
        qualified = "::".join(namespace_stack + [name])

        sym = Symbol(
            name=name,
            symbol_type=SymbolType.ENUM,
            file_path=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            column=node.start_point[1],
            language=Lang.CPP,
            qualified_name=qualified,
        )
        sym_id = graph.add_symbol(sym)

        if parent_symbol:
            graph.add_edge(Edge(
                source_id=parent_symbol.id,
                target_id=sym_id,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            ))

        # Extract enum values
        body = _find_child_by_type(node, 'enumerator_list')
        if body:
            for enumerator in _find_children_by_type(body, 'enumerator'):
                val_name_node = _find_child_by_type(enumerator, 'identifier')
                if val_name_node:
                    val_name = _get_text(val_name_node, source)
                    val_qualified = "::".join(namespace_stack + [name, val_name])
                    val_sym = Symbol(
                        name=val_name,
                        symbol_type=SymbolType.ENUM_VALUE,
                        file_path=file_path,
                        line=enumerator.start_point[0] + 1,
                        column=enumerator.start_point[1],
                        language=Lang.CPP,
                        qualified_name=val_qualified,
                    )
                    val_id = graph.add_symbol(val_sym)

                    graph.add_edge(Edge(
                        source_id=sym_id,
                        target_id=val_id,
                        edge_type=EdgeType.CONTAINS,
                        file_path=file_path,
                        line=enumerator.start_point[0] + 1,
                    ))

    def _extract_declaration(self, node: Node, source: bytes, file_path: str,
                             graph: AnalysisGraph, namespace_stack: list[str],
                             parent_symbol: Optional[Symbol]):
        """Extract a top-level declaration (function decl, variable, etc.)."""
        # Check for class/struct/enum inside declaration
        for child in node.children:
            if child.type in ('class_specifier', 'struct_specifier'):
                self._extract_class(child, source, file_path, graph,
                                    namespace_stack, parent_symbol)
                return
            if child.type == 'enum_specifier':
                self._extract_enum(child, source, file_path, graph,
                                   namespace_stack, parent_symbol)
                return

        # Check if this is a function declaration
        func_declarators = _find_descendants_by_type(node, 'function_declarator')
        if func_declarators:
            self._extract_function_declaration(node, source, file_path, graph,
                                               namespace_stack, parent_symbol)
            return

        # Otherwise it might be a variable declaration
        # (we only extract globals / namespace-level variables)
        if parent_symbol is None or parent_symbol.symbol_type == SymbolType.NAMESPACE:
            self._extract_variable_declaration(node, source, file_path, graph,
                                               namespace_stack, parent_symbol)

    def _extract_function_declaration(self, node: Node, source: bytes, file_path: str,
                                       graph: AnalysisGraph, namespace_stack: list[str],
                                       parent_symbol: Optional[Symbol]):
        """Extract a function forward declaration."""
        type_node = _find_child_by_type(node, 'type_identifier') or \
                    _find_child_by_type(node, 'primitive_type') or \
                    _find_child_by_type(node, 'qualified_identifier') or \
                    _find_child_by_type(node, 'template_type')
        return_type = _get_text(type_node, source) if type_node else ""

        func_decl = _find_descendants_by_type(node, 'function_declarator')
        if not func_decl:
            return
        func_decl = func_decl[0]

        name_node = _find_child_by_type(func_decl, 'identifier') or \
                    _find_child_by_type(func_decl, 'qualified_identifier') or \
                    _find_child_by_type(func_decl, 'field_identifier')
        if not name_node:
            return

        name = _get_text(name_node, source)
        params = self._extract_parameters(func_decl, source)
        qualified = "::".join(namespace_stack + [name]) if namespace_stack else name

        param_sig = ", ".join(f"{p.type_name} {p.name}" for p in params)
        signature = f"{return_type + ' ' if return_type else ''}{qualified}({param_sig})"

        sym_type = SymbolType.METHOD if '::' in name else SymbolType.FUNCTION

        sym = Symbol(
            name=name,
            symbol_type=sym_type,
            file_path=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            column=node.start_point[1],
            language=Lang.CPP,
            qualified_name=qualified,
            signature=signature,
            return_type=return_type,
            parameters=params,
        )
        sym_id = graph.add_symbol(sym)

        if parent_symbol:
            graph.add_edge(Edge(
                source_id=parent_symbol.id,
                target_id=sym_id,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            ))

    def _extract_variable_declaration(self, node: Node, source: bytes, file_path: str,
                                       graph: AnalysisGraph, namespace_stack: list[str],
                                       parent_symbol: Optional[Symbol]):
        """Extract global/namespace-level variable declarations."""
        type_node = _find_child_by_type(node, 'type_identifier') or \
                    _find_child_by_type(node, 'primitive_type') or \
                    _find_child_by_type(node, 'qualified_identifier') or \
                    _find_child_by_type(node, 'template_type')
        type_name = _get_text(type_node, source) if type_node else "unknown"

        for child in node.children:
            if child.type == 'init_declarator':
                id_node = _find_child_by_type(child, 'identifier')
                if id_node:
                    var_name = _get_text(id_node, source)
                    qualified = "::".join(namespace_stack + [var_name]) \
                                if namespace_stack else var_name
                    sym = Symbol(
                        name=var_name,
                        symbol_type=SymbolType.GLOBAL_VARIABLE,
                        file_path=file_path,
                        line=node.start_point[0] + 1,
                        column=child.start_point[1],
                        language=Lang.CPP,
                        qualified_name=qualified,
                        return_type=type_name,
                    )
                    sym_id = graph.add_symbol(sym)
                    if parent_symbol:
                        graph.add_edge(Edge(
                            source_id=parent_symbol.id,
                            target_id=sym_id,
                            edge_type=EdgeType.CONTAINS,
                            file_path=file_path,
                            line=node.start_point[0] + 1,
                        ))

    def _extract_template(self, node: Node, source: bytes, file_path: str,
                          graph: AnalysisGraph, namespace_stack: list[str],
                          parent_symbol: Optional[Symbol]):
        """Extract a template declaration (wraps a class or function)."""
        # Just recurse into the inner declaration
        for child in node.children:
            if child.type in ('class_specifier', 'struct_specifier'):
                self._extract_class(child, source, file_path, graph,
                                    namespace_stack, parent_symbol)
            elif child.type == 'function_definition':
                self._extract_function(child, source, file_path, graph,
                                       namespace_stack, parent_symbol)
            elif child.type == 'declaration':
                self._extract_declaration(child, source, file_path, graph,
                                          namespace_stack, parent_symbol)

    def _extract_typedef(self, node: Node, source: bytes, file_path: str,
                         graph: AnalysisGraph, namespace_stack: list[str],
                         parent_symbol: Optional[Symbol]):
        """Extract a typedef."""
        text = _get_text(node, source)
        # Get the declared name (last identifier before semicolon)
        declarators = _find_descendants_by_type(node, 'type_identifier')
        if len(declarators) >= 1:
            name = _get_text(declarators[-1], source)
            qualified = "::".join(namespace_stack + [name]) if namespace_stack else name
            sym = Symbol(
                name=name,
                symbol_type=SymbolType.TYPEDEF,
                file_path=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1],
                language=Lang.CPP,
                qualified_name=qualified,
                signature=text.strip().rstrip(';'),
            )
            sym_id = graph.add_symbol(sym)
            if parent_symbol:
                graph.add_edge(Edge(
                    source_id=parent_symbol.id,
                    target_id=sym_id,
                    edge_type=EdgeType.CONTAINS,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                ))

    def _extract_using(self, node: Node, source: bytes, file_path: str,
                       graph: AnalysisGraph, namespace_stack: list[str],
                       parent_symbol: Optional[Symbol]):
        """Extract a using declaration or alias."""
        text = _get_text(node, source).strip().rstrip(';')
        name_node = _find_child_by_type(node, 'type_identifier') or \
                    _find_child_by_type(node, 'identifier')
        if name_node:
            name = _get_text(name_node, source)
            qualified = "::".join(namespace_stack + [name]) if namespace_stack else name
            sym = Symbol(
                name=name,
                symbol_type=SymbolType.USING_ALIAS,
                file_path=file_path,
                line=node.start_point[0] + 1,
                column=node.start_point[1],
                language=Lang.CPP,
                qualified_name=qualified,
                signature=text,
            )
            sym_id = graph.add_symbol(sym)
            if parent_symbol:
                graph.add_edge(Edge(
                    source_id=parent_symbol.id,
                    target_id=sym_id,
                    edge_type=EdgeType.CONTAINS,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                ))

    def _extract_class_declaration(self, node: Node, source: bytes, file_path: str,
                                    graph: AnalysisGraph, namespace_stack: list[str],
                                    class_symbol: Symbol, access: AccessSpecifier):
        """Extract a declaration inside a class (method decl or static member)."""
        # Check for embedded class/struct/enum
        for child in node.children:
            if child.type in ('class_specifier', 'struct_specifier'):
                self._extract_class(child, source, file_path, graph,
                                    namespace_stack, class_symbol)
                return
            if child.type == 'enum_specifier':
                self._extract_enum(child, source, file_path, graph,
                                   namespace_stack, class_symbol)
                return

        func_declarators = _find_descendants_by_type(node, 'function_declarator')
        if func_declarators:
            # Method declaration
            type_node = _find_child_by_type(node, 'type_identifier') or \
                        _find_child_by_type(node, 'primitive_type') or \
                        _find_child_by_type(node, 'qualified_identifier') or \
                        _find_child_by_type(node, 'template_type')
            return_type = _get_text(type_node, source) if type_node else ""

            func_decl = func_declarators[0]
            name_node = _find_child_by_type(func_decl, 'field_identifier') or \
                        _find_child_by_type(func_decl, 'identifier') or \
                        _find_child_by_type(func_decl, 'destructor_name') or \
                        _find_child_by_type(func_decl, 'qualified_identifier')
            if not name_node:
                return

            name = _get_text(name_node, source)
            full_text = _get_text(node, source)
            is_virtual = 'virtual' in full_text.split('(')[0]
            is_static = 'static' in full_text.split('(')[0]
            is_const = ') const' in full_text
            is_override = 'override' in full_text
            is_pure_virtual = '= 0' in full_text

            if name.startswith('~'):
                sym_type = SymbolType.DESTRUCTOR
            elif name == class_symbol.name:
                sym_type = SymbolType.CONSTRUCTOR
                return_type = ""
            else:
                sym_type = SymbolType.METHOD

            params = self._extract_parameters(func_decl, source)
            qualified = "::".join(namespace_stack + [name])
            param_sig = ", ".join(f"{p.type_name} {p.name}" for p in params)
            signature = f"{return_type + ' ' if return_type else ''}{qualified}({param_sig})"
            if is_const:
                signature += " const"
            if is_pure_virtual:
                signature += " = 0"

            sym = Symbol(
                name=name,
                symbol_type=sym_type,
                file_path=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                column=node.start_point[1],
                language=Lang.CPP,
                qualified_name=qualified,
                signature=signature,
                return_type=return_type,
                parameters=params,
                access=access,
                is_virtual=is_virtual,
                is_static=is_static,
                is_const=is_const,
                is_override=is_override,
                is_pure_virtual=is_pure_virtual,
            )
            sym_id = graph.add_symbol(sym)
            graph.add_edge(Edge(
                source_id=class_symbol.id,
                target_id=sym_id,
                edge_type=EdgeType.CONTAINS,
                file_path=file_path,
                line=node.start_point[0] + 1,
            ))
        else:
            # Static member variable or other declaration
            type_node = _find_child_by_type(node, 'type_identifier') or \
                        _find_child_by_type(node, 'primitive_type') or \
                        _find_child_by_type(node, 'qualified_identifier') or \
                        _find_child_by_type(node, 'template_type')
            type_name = _get_text(type_node, source) if type_node else "unknown"

            is_static = any(
                c.type == 'storage_class_specifier' and _get_text(c, source) == 'static'
                for c in node.children
            )

            for child in node.children:
                if child.type == 'init_declarator':
                    id_node = _find_child_by_type(child, 'identifier')
                    if id_node:
                        field_name = _get_text(id_node, source)
                        qualified = "::".join(namespace_stack + [field_name])
                        sym = Symbol(
                            name=field_name,
                            symbol_type=SymbolType.MEMBER_VARIABLE,
                            file_path=file_path,
                            line=node.start_point[0] + 1,
                            column=child.start_point[1],
                            language=Lang.CPP,
                            qualified_name=qualified,
                            return_type=type_name,
                            access=access,
                            is_static=is_static,
                        )
                        sym_id = graph.add_symbol(sym)
                        graph.add_edge(Edge(
                            source_id=class_symbol.id,
                            target_id=sym_id,
                            edge_type=EdgeType.CONTAINS,
                            file_path=file_path,
                            line=node.start_point[0] + 1,
                        ))

    def _extract_parameters(self, func_declarator: Node,
                            source: bytes) -> list[Parameter]:
        """Extract parameters from a function declarator."""
        params = []
        param_list = _find_child_by_type(func_declarator, 'parameter_list')
        if not param_list:
            return params

        for param in param_list.children:
            if param.type == 'parameter_declaration':
                # Type
                type_parts = []
                for c in param.children:
                    if c.type in ('type_identifier', 'primitive_type',
                                  'qualified_identifier', 'template_type',
                                  'sized_type_specifier', 'type_qualifier'):
                        type_parts.append(_get_text(c, source))
                    elif c.type in ('pointer_declarator', 'reference_declarator',
                                    'abstract_pointer_declarator',
                                    'abstract_reference_declarator'):
                        type_parts.append('*' if 'pointer' in c.type else '&')

                param_type = ' '.join(type_parts) if type_parts else 'unknown'

                # Name
                name_node = _find_child_by_type(param, 'identifier') or \
                            _find_descendants_by_type(param, 'identifier')
                if isinstance(name_node, list):
                    name_node = name_node[0] if name_node else None
                param_name = _get_text(name_node, source) if name_node else ""

                # Default value
                default_node = _find_child_by_type(param, 'default_value')
                default_val = _get_text(default_node, source).lstrip('= ') \
                              if default_node else None

                params.append(Parameter(
                    name=param_name,
                    type_name=param_type,
                    default_value=default_val,
                ))
            elif param.type == 'variadic_parameter_declaration':
                params.append(Parameter(name="...", type_name="..."))

        return params

    def _extract_references(self, body: Node, source: bytes, file_path: str,
                            graph: AnalysisGraph, parent_symbol: Symbol):
        """Extract function/method calls and generic symbol references from a function body."""
        seen_calls: set[str] = set()

        # 1. Extract Calls
        call_exprs = _find_descendants_by_type(body, 'call_expression')
        for call in call_exprs:
            callee = call.children[0] if call.children else None
            if not callee:
                continue

            callee_name = _get_text(callee, source)
            if callee_name in seen_calls:
                continue
            seen_calls.add(callee_name)

            callee_sym = Symbol(
                name=callee_name,
                symbol_type=SymbolType.FUNCTION,
                file_path="<unresolved>",
                line=0,
                language=Lang.CPP,
                qualified_name=callee_name,
            )
            callee_id = graph.add_symbol(callee_sym)

            graph.add_edge(Edge(
                source_id=parent_symbol.id,
                target_id=callee_id,
                edge_type=EdgeType.CALLS,
                file_path=file_path,
                line=call.start_point[0] + 1,
                label=f"calls {callee_name}",
            ))

        # 2. Extract General References (identifiers, scoped identifiers)
        seen_refs: set[str] = set(seen_calls) # Don't double-count calls
        
        ignore = {'int', 'float', 'double', 'char', 'bool', 'void', 'long', 'short', 
                  'unsigned', 'signed', 'auto', 'size_t', 'string', 'wstring', 
                  'return', 'if', 'else', 'for', 'while', 'do', 'switch', 'case', 
                  'default', 'break', 'continue', 'true', 'false', 'nullptr', 'this',
                  'std', 'cout', 'cin', 'endl', 'printf'}

        # Find scoped identifiers (e.g. MyEnum::Value)
        scoped_ids = _find_descendants_by_type(body, 'qualified_identifier')
        for sid in scoped_ids:
            name = _get_text(sid, source)
            if name in seen_refs or name in ignore: continue
            seen_refs.add(name)
            self._add_reference_edge(graph, parent_symbol, name, file_path, sid.start_point[0] + 1)
            
        # Find raw identifiers
        identifiers = _find_descendants_by_type(body, 'identifier')
        for id_node in identifiers:
            name = _get_text(id_node, source)
            # Basic filtering
            if len(name) < 2 or name in seen_refs or name in ignore: continue
            seen_refs.add(name)
            self._add_reference_edge(graph, parent_symbol, name, file_path, id_node.start_point[0] + 1)

    def _add_reference_edge(self, graph: AnalysisGraph, symbol: Symbol,
                            ref_name: str, file_path: str, line: int):
        """Add a REFERENCES edge to an unresolved symbol."""
        ref_sym = Symbol(
            name=ref_name.split('::')[-1],
            symbol_type=SymbolType.UNKNOWN,
            file_path="<unresolved>",
            line=0,
            language=Lang.CPP,
            qualified_name=ref_name,
        )
        ref_id = graph.add_symbol(ref_sym)
        graph.add_edge(Edge(
            source_id=symbol.id,
            target_id=ref_id,
            edge_type=EdgeType.REFERENCES,
            file_path=file_path,
            line=line,
            label=f"refs {ref_name}",
        ))

    def _add_type_usage_edge(self, graph: AnalysisGraph, symbol: Symbol,
                             type_name: str, file_path: str, line: int):
        """Add a USES_TYPE edge from a symbol to a type."""
        # Skip primitive types
        primitives = {'int', 'float', 'double', 'char', 'bool', 'void',
                      'long', 'short', 'unsigned', 'signed', 'auto',
                      'size_t', 'string', 'wstring', 'unknown'}
        clean_type = type_name.replace('const ', '').replace('&', '').replace('*', '').strip()
        if clean_type.lower() in primitives:
            return

        type_sym = Symbol(
            name=clean_type,
            symbol_type=SymbolType.CLASS,
            file_path="<unresolved>",
            line=0,
            language=Lang.CPP,
            qualified_name=clean_type,
        )
        type_id = graph.add_symbol(type_sym)

        graph.add_edge(Edge(
            source_id=symbol.id,
            target_id=type_id,
            edge_type=EdgeType.USES_TYPE,
            file_path=file_path,
            line=line,
        ))


def parse_project_files(file_paths: list[str],
                        graph: Optional[AnalysisGraph] = None) -> AnalysisGraph:
    """
    Parse multiple C++ files and build a combined graph.

    Args:
        file_paths: List of C++ source file paths
        graph: Existing graph to add to

    Returns:
        Combined AnalysisGraph
    """
    if graph is None:
        graph = AnalysisGraph()

    parser = CppParser()
    for fp in file_paths:
        parser.parse_file(fp, graph)

    return graph
