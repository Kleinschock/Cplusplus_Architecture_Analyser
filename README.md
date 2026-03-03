# C++ Architecture Analyser

Semantische Analyse und interaktive Visualisierung von C++ Codebases. Gibt dir eine navigierbare Landkarte aller Symbole und deren Beziehungen.

## Features

- **Seed & Expand**: Symbolnamen eingeben → vollständigen Abhängigkeitsgraph bauen
- **C++ Parser**: tree-sitter basiert — braucht keinen Build, keine `compile_commands.json`
- **Symboltypen**: Klassen, Structs, Funktionen, Methoden, Member-Variablen, Enums, Namespaces, Typedefs
- **Beziehungen**: Contains, Inherits, Calls, Uses Type, References
- **Interaktive Web-UI**: Cytoscape.js mit Dagre/Cola/Circle Layouts
- **Detail-Panel**: Klick auf einen Node → volle Symbol-Details, Member-Liste, Caller/Callees
- **Export**: PNG und DOT (Graphviz)

## Quick Start

```bash
# Dependencies installieren
pip install -r requirements.txt

# Web-UI starten
python run.py serve --port 8080
# → Browser öffnen: http://localhost:8080

# CLI: Direkte Analyse
python run.py analyze --project /pfad/zum/projekt --symbols "Noise,ShaderType" --depth 2
```

## Usage

### Web-UI
1. Starte den Server: `python run.py serve`
2. Öffne `http://localhost:8080`
3. Gib den Projektpfad und die Symbolnamen ein
4. Klicke "Analyze"
5. Nutze den Graph: klicke Nodes, filtere Kanten, wechsle Layouts, erweitere per Rechtsklick

### CLI
```bash
# Text-Ausgabe
python run.py analyze -p /pfad/zum/projekt -s "MyClass" -d 3

# JSON-Ausgabe (Cytoscape-kompatibel)
python run.py analyze -p /pfad/zum/projekt -s "MyClass" -f json -o graph.json

# DOT-Ausgabe (für Graphviz)
python run.py analyze -p /pfad/zum/projekt -s "MyClass" -f dot -o graph.dot

# Vollständigen Index erstellen
python run.py index -p /pfad/zum/projekt -o index.json
```

## Architektur

```
analyzer/
  models.py          Datenmodell (Symbol, Edge, Graph)
  scanner.py         File-Discovery + Text-Suche
  cpp_parser.py      tree-sitter C++ Parser
  symbol_index.py    Symbol-Datenbank + Queries
  graph_builder.py   Seed-and-Expand Algorithmus
  exporter.py        Export (Cytoscape.js JSON, DOT, Text)
web/
  index.html         Web-UI
  css/style.css      Dark Theme
  js/app.js          Cytoscape.js Graph-Viewer
server.py            Flask API Server
run.py               CLI Entry Point
```
