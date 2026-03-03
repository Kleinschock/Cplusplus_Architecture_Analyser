"""
CLI entry point for the C++ Architecture Analyser.
"""

import argparse
import json
import os
import sys


def cmd_serve(args):
    """Start the web server."""
    from server import run_server
    run_server(host=args.host, port=args.port, debug=args.debug)


def cmd_analyze(args):
    """Run analysis from command line."""
    from analyzer.graph_builder import GraphBuilder
    from analyzer.exporter import to_cytoscape_json, to_dot, to_summary_text

    if not os.path.isdir(args.project):
        print(f"Error: Directory not found: {args.project}", file=sys.stderr)
        sys.exit(1)

    symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
    if not symbols:
        print("Error: No symbols specified", file=sys.stderr)
        sys.exit(1)

    print(f"\n  C++ Architecture Analyser")
    print(f"  ========================")
    print(f"  Project: {args.project}")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Depth:   {args.depth}")
    print()

    builder = GraphBuilder(args.project)
    graph = builder.analyze(symbols, depth=args.depth)

    # Output
    if args.format == 'json':
        seed_ids = set()
        for name in symbols:
            for sym in graph.find_symbols_by_name(name):
                seed_ids.add(sym.id)
        result = to_cytoscape_json(graph, seed_ids=seed_ids)
        output = json.dumps(result, indent=2)
    elif args.format == 'dot':
        output = to_dot(graph, title=f"Analysis: {', '.join(symbols)}")
    else:  # text
        output = to_summary_text(graph, symbols)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"\n  Output saved to: {args.output}")
    else:
        print(output)


def cmd_index(args):
    """Pre-build a full project index."""
    from analyzer.graph_builder import GraphBuilder

    if not os.path.isdir(args.project):
        print(f"Error: Directory not found: {args.project}", file=sys.stderr)
        sys.exit(1)

    print(f"\n  C++ Architecture Analyser — Full Index")
    print(f"  =======================================")
    print(f"  Project: {args.project}")
    print()

    builder = GraphBuilder(args.project)
    index = builder.index_full_project()

    output_path = args.output or os.path.join(args.project, '.arch_index.json')
    index.save(output_path)
    print(f"\n  Index saved to: {output_path}")

    stats = index.get_stats()
    print(f"  Symbols: {stats['total_symbols']}")
    print(f"  Edges:   {stats['total_edges']}")


def main():
    parser = argparse.ArgumentParser(
        prog='C++ Architecture Analyser',
        description='Semantic analysis and visualization of C++ codebases',
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # serve
    serve_parser = subparsers.add_parser('serve', help='Start the web UI server')
    serve_parser.add_argument('--host', default='127.0.0.1', help='Host (default: 127.0.0.1)')
    serve_parser.add_argument('--port', type=int, default=8080, help='Port (default: 8080)')
    serve_parser.add_argument('--debug', action='store_true', help='Debug mode')

    # analyze
    analyze_parser = subparsers.add_parser('analyze', help='Analyze symbols in a project')
    analyze_parser.add_argument('--project', '-p', required=True, help='Project root directory')
    analyze_parser.add_argument('--symbols', '-s', required=True,
                                help='Comma-separated symbol names to analyze')
    analyze_parser.add_argument('--depth', '-d', type=int, default=2,
                                help='Expansion depth (default: 2)')
    analyze_parser.add_argument('--output', '-o', help='Output file path')
    analyze_parser.add_argument('--format', '-f', choices=['json', 'dot', 'text'],
                                default='text', help='Output format (default: text)')

    # index
    index_parser = subparsers.add_parser('index', help='Build a full project index')
    index_parser.add_argument('--project', '-p', required=True, help='Project root directory')
    index_parser.add_argument('--output', '-o', help='Output file path')

    args = parser.parse_args()

    if args.command == 'serve':
        cmd_serve(args)
    elif args.command == 'analyze':
        cmd_analyze(args)
    elif args.command == 'index':
        cmd_index(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
