import os
import unittest

from analyzer.cpp_parser import CppParser, parse_project_files
from analyzer.models import AnalysisGraph, SymbolType, EdgeType

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), 'test_data')

class TestCppParserFeatures(unittest.TestCase):

    def setUp(self):
        self.parser = CppParser()

    def test_deduplication(self):
        """
        Test that a class defined across a header and a source file 
        results in a single Symbol in the index instead of two distinct ones.
        """
        graph = parse_project_files([
            os.path.join(TEST_DATA_DIR, 'PlaceMaker.h'),
            os.path.join(TEST_DATA_DIR, 'PlaceMaker.cpp')
        ])

        # We should only have ONE class 'PlaceMaker'
        classes = [s for s in graph.symbols.values() if s.symbol_type == SymbolType.CLASS and s.name == 'PlaceMaker']
        self.assertEqual(len(classes), 1, "PlaceMaker class should be deduplicated into a single symbol.")
        
        pm = classes[0]
        
        # We should also only have ONE method 'doSomething'
        methods = [s for s in graph.symbols.values() if s.symbol_type == SymbolType.METHOD and s.name == 'doSomething']
        self.assertEqual(len(methods), 1, "doSomething method should be deduplicated.")

        # The class should contain 'doSomething' and 'm_value'
        members = [graph.get_symbol(e.target_id) for e in graph.edges if e.source_id == pm.id and e.edge_type == EdgeType.CONTAINS]
        member_names = [m.name for m in members if m]
        
        self.assertIn('doSomething', member_names)
        self.assertIn('m_value', member_names)
        self.assertIn('getValue', member_names)

        # Check references: doSomething -> m_value
        do_something = methods[0]
        m_value = [m for m in members if m.name == 'm_value'][0]
        
        refs = [e for e in graph.edges if e.source_id == do_something.id and e.edge_type == EdgeType.REFERENCES]
        ref_target_names = [graph.get_symbol(e.target_id).name for e in refs]
        self.assertIn('m_value', ref_target_names, "doSomething should reference m_value")


    def test_switch_case_reference(self):
        """
        Test that an Enum value used inside a switch case creates a REFERENCE edge.
        """
        graph = parse_project_files([
            os.path.join(TEST_DATA_DIR, 'NoiseTest.cpp')
        ])

        # Find applyNoise method
        methods = [s for s in graph.symbols.values() if s.name == 'applyNoise']
        self.assertEqual(len(methods), 1)
        apply_noise = methods[0]

        # Find references from applyNoise
        refs = [e for e in graph.edges if e.source_id == apply_noise.id and e.edge_type == EdgeType.REFERENCES]
        ref_targets = [graph.get_symbol(e.target_id) for e in refs]
        
        ref_qualified_names = [t.qualified_name for t in ref_targets]
        
        # It should have found Noise::Perlin, Noise::Simplex, Noise::White
        self.assertIn('Noise::Perlin', ref_qualified_names)
        self.assertIn('Noise::Simplex', ref_qualified_names)
        self.assertIn('Noise::White', ref_qualified_names)


if __name__ == '__main__':
    unittest.main(verbosity=2)
