import os
import unittest
from analyzer.graph_builder import GraphBuilder
from analyzer.models import SymbolType, EdgeType

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), 'test_data')

class TestGraphBuilder(unittest.TestCase):

    def test_end_to_end_analysis(self):
        """
        Test the GraphBuilder pipeline with the test data.
        Search for 'NoiseGenerator' and expand by 2 depths.
        """
        builder = GraphBuilder(TEST_DATA_DIR)
        
        # We start with "NoiseGenerator". It's in NoiseTest.cpp
        # Depth 1: Just the files containing NoiseGenerator (NoiseTest.cpp)
        # Depth 2: Any related symbols... in this case, Noise is used.
        graph = builder.analyze(["NoiseGenerator"], depth=2)

        # 1. Verify Symbols Exist
        classes = [s.name for s in graph.symbols.values() if s.symbol_type == SymbolType.CLASS]
        self.assertIn("NoiseGenerator", classes)
        
        enums = [s.name for s in graph.symbols.values() if s.symbol_type == SymbolType.ENUM]
        self.assertIn("Noise", enums)

        # 2. Verify edges (NoiseGenerator::applyNoise -> Noise::Perlin)
        apply_noise_nodes = [s for s in graph.symbols.values() if s.name == 'applyNoise']
        self.assertTrue(len(apply_noise_nodes) > 0)
        apply_noise = apply_noise_nodes[0]

        refs = [e for e in graph.edges if e.source_id == apply_noise.id and e.edge_type == EdgeType.REFERENCES]
        ref_targets = [graph.get_symbol(e.target_id).qualified_name for e in refs]
        
        self.assertIn("Noise::Perlin", ref_targets)
        self.assertIn("Noise::Simplex", ref_targets)

    def test_place_maker_graph(self):
        """
        Test GraphBuilder resolves cross-references between cpp and h correctly.
        """
        builder = GraphBuilder(TEST_DATA_DIR)
        graph = builder.analyze(["PlaceMaker"], depth=1)

        pm_class = [s for s in graph.symbols.values() if s.name == "PlaceMaker" and s.symbol_type == SymbolType.CLASS]
        self.assertEqual(len(pm_class), 1, "GraphBuilder must yield exactly one PlaceMaker class.")

        members = [graph.get_symbol(e.target_id).name for e in graph.edges 
                   if e.source_id == pm_class[0].id and e.edge_type == EdgeType.CONTAINS]
        
        self.assertIn("doSomething", members)
        self.assertIn("m_value", members)

if __name__ == '__main__':
    unittest.main(verbosity=2)
