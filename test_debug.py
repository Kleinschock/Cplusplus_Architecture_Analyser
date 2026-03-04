from analyzer.graph_builder import GraphBuilder
b = GraphBuilder('tests/test_data')
b._parse_file('tests/test_data/NoiseTest.cpp')
print("--- PRE RESOLVE ---")
for s in b.index.graph.symbols.values():
    if 'Noise' in s.name:
        print(s.name, s.symbol_type.value, s.file_path)

b.index.resolve_unresolved()
print("--- POST RESOLVE ---")
for s in b.index.graph.symbols.values():
    if 'Noise' in s.name:
        print(s.name, s.symbol_type.value, s.file_path)

print("--- EDGES AFTER RESOLVE ---")
apply_noise = [s for s in b.index.graph.symbols.values() if s.name == 'applyNoise'][0]
for e in b.index.graph.edges:
    if e.source_id == apply_noise.id or e.target_id == apply_noise.id:
        print(f"{b.index.graph.get_symbol(e.source_id).name} -> {b.index.graph.get_symbol(e.target_id).name} [{e.edge_type.value}]")

print("--- SUBGRAPH ---")
g = b.analyze(['NoiseGenerator'], depth=2)
for s in g.symbols.values():
    if s.symbol_type.value == 'enum':
        print("FOUND ENUM:", s.name)
