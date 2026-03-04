import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLineEdit, QPushButton, QLabel, QSlider, QSplitter,
                               QCheckBox, QFileDialog, QMessageBox, QSpinBox)
from PySide6.QtCore import Qt

from analyzer.scanner import discover_files
from analyzer.graph_builder import GraphBuilder
from analyzer.exporter import to_gexf
from .graph_view import GraphView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("C++ Architecture Analyser")
        self.resize(1200, 800)
        self.setStyleSheet("background-color: #1a1a2e; color: white; font-family: Inter;")
        
        self.builder = GraphBuilder()
        self.current_graph = None

        self.setup_ui()

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # Left Panel (Controls)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignTop)
        
        # Inputs
        left_layout.addWidget(QLabel("<b>Target Project / Directory</b>"))
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("/path/to/cpp_project")
        self.path_input.setStyleSheet("background-color: #0a0a1a; border: 1px solid #4A9EFF; padding: 5px;")
        left_layout.addWidget(self.path_input)
        
        left_layout.addWidget(QLabel("<b>Seed Symbols (comma separated)</b>"))
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("e.g. NoiseEffect, RenderPass")
        self.symbol_input.setStyleSheet("background-color: #0a0a1a; border: 1px solid #4A9EFF; padding: 5px;")
        left_layout.addWidget(self.symbol_input)
        
        left_layout.addWidget(QLabel("<b>Expansion Depth</b>"))
        self.depth_input = QSpinBox()
        self.depth_input.setRange(1, 10)
        self.depth_input.setValue(2)
        self.depth_input.setStyleSheet("background-color: #0a0a1a; border: 1px solid #4A9EFF; padding: 5px;")
        left_layout.addWidget(self.depth_input)
        
        self.analyze_btn = QPushButton("Analyze Architecture")
        self.analyze_btn.setStyleSheet("background-color: #4A9EFF; padding: 10px; font-weight: bold; border-radius: 5px;")
        self.analyze_btn.clicked.connect(self.on_analyze)
        left_layout.addWidget(self.analyze_btn)
        
        left_layout.addSpacing(20)
        
        # Physics Controls
        left_layout.addWidget(QLabel("<b>Live Physics Layout</b>"))
        self.physics_cb = QCheckBox("Enable Physics")
        self.physics_cb.setChecked(True)
        self.physics_cb.stateChanged.connect(self.toggle_physics)
        left_layout.addWidget(self.physics_cb)
        
        left_layout.addWidget(QLabel("Spring Length (k)"))
        self.spring_slider = QSlider(Qt.Horizontal)
        self.spring_slider.setRange(10, 500)
        self.spring_slider.setValue(100)
        self.spring_slider.valueChanged.connect(self.update_physics_params)
        left_layout.addWidget(self.spring_slider)
        
        left_layout.addStretch()
        
        # Export
        self.export_gexf_btn = QPushButton("Export to Gephi (GEXF)")
        self.export_gexf_btn.setStyleSheet("background-color: #B07FE0; padding: 10px; border-radius: 5px;")
        self.export_gexf_btn.clicked.connect(self.export_gexf)
        left_layout.addWidget(self.export_gexf_btn)
        
        # Right Panel (Graph)
        self.graph_view = GraphView()
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.graph_view)
        splitter.setSizes([300, 900])
        
        main_layout.addWidget(splitter)
        
    def update_physics_params(self):
        self.graph_view.scene.k = self.spring_slider.value()
        
    def toggle_physics(self, state):
        if state == Qt.Checked:
            self.graph_view.scene.start_physics()
        else:
            self.graph_view.scene.stop_physics()

    def on_analyze(self):
        path = self.path_input.text().strip()
        symbols_text = self.symbol_input.text().strip()
        depth = self.depth_input.value()
        
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Invalid project path.")
            return
            
        if not symbols_text:
            QMessageBox.warning(self, "Error", "Please enter at least one seed symbol.")
            return
            
        seeds = [s.strip() for s in symbols_text.split(",") if s.strip()]
        
        self.analyze_btn.setText("Analyzing...")
        self.analyze_btn.setEnabled(False)
        self.repaint() # Force UI update
        
        try:
            # Instantiate builder and run full pipeline
            self.builder = GraphBuilder(path)
            self.current_graph = self.builder.analyze(seeds, depth=depth)
            
            seed_ids = set()
            for s in seeds:
                founds = self.builder.index.search(s, exact=False)
                seed_ids.update(f.id for f in founds)
                
            self.graph_view.set_graph(self.current_graph, seed_ids)
            
        except Exception as e:
            QMessageBox.critical(self, "Analysis Error", str(e))
        finally:
            self.analyze_btn.setText("Analyze Architecture")
            self.analyze_btn.setEnabled(True)

    def export_gexf(self):
        if not self.current_graph:
            QMessageBox.warning(self, "Error", "No graph to export. Please analyze first.")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Save GEXF", "", "GEXF Files (*.gexf)")
        if file_path:
            gexf_data = to_gexf(self.current_graph)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(gexf_data)
            QMessageBox.information(self, "Success", f"Exported to {file_path}")
