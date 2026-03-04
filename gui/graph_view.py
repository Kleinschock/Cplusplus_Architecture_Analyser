import math
import networkx as nx
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem,
                               QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsPolygonItem,
                               QGraphicsSimpleTextItem, QGraphicsPathItem)
from PySide6.QtCore import Qt, QPointF, QTimer, QRectF
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath, QTransform, QFont

from analyzer.models import AnalysisGraph, SymbolType, EdgeType

# Color definitions matching our theme
SYMBOL_COLORS = {
    SymbolType.CLASS: QColor("#4A9EFF"),
    SymbolType.STRUCT: QColor("#5BA8FF"),
    SymbolType.FUNCTION: QColor("#47D185"),
    SymbolType.METHOD: QColor("#3BC478"),
    SymbolType.MEMBER_VARIABLE: QColor("#B07FE0"),
    SymbolType.ENUM: QColor("#FF8C42"),
    SymbolType.ENUM_VALUE: QColor("#FFB07A"),
    SymbolType.NAMESPACE: QColor("#26C6DA"),
    SymbolType.TYPEDEF: QColor("#FFD740"),
    SymbolType.UNKNOWN: QColor("#9E9E9E"),
}

EDGE_COLORS = {
    EdgeType.CONTAINS: QColor("#546E7A"),
    EdgeType.INHERITS: QColor("#FF7043"),
    EdgeType.CALLS: QColor("#66BB6A"),
    EdgeType.USES_TYPE: QColor("#42A5F5"),
    EdgeType.REFERENCES: QColor("#9E9E9E"),
}

class NodeItem(QGraphicsItem):
    def __init__(self, symbol_id: str, label: str, symbol_type: SymbolType, is_seed: bool):
        super().__init__()
        self.symbol_id = symbol_id
        self.label = label
        self.symbol_type = symbol_type
        self.is_seed = is_seed
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.radius = 20 if not is_seed else 25
        
        self.color = SYMBOL_COLORS.get(symbol_type, QColor("#9E9E9E"))
        if is_seed:
            self.color = self.color.lighter(120)

        # Compute text bounding rect to size the node
        self.font = QFont("Inter", 9)
        if is_seed:
            self.font.setBold(True)

    def boundingRect(self):
        return QRectF(-self.radius - 5, -self.radius - 5, self.radius * 2 + 10, self.radius * 2 + 25)

    def paint(self, painter, option, widget):
        painter.setRenderHint(painter.Antialiasing)
        
        # Draw shape
        bg_color = self.color
        if self.isSelected():
            painter.setPen(QPen(Qt.white, 3))
        else:
            painter.setPen(QPen(bg_color.darker(150), 1))
            
        painter.setBrush(QBrush(bg_color))
        
        if self.symbol_type in (SymbolType.CLASS, SymbolType.STRUCT):
            painter.drawRoundedRect(-self.radius, -self.radius*0.7, self.radius*2, self.radius*1.4, 5, 5)
        elif self.symbol_type == SymbolType.NAMESPACE:
            path = QPainterPath()
            w, h = self.radius, self.radius * 0.8
            path.moveTo(0, -h)
            path.lineTo(w, -h*0.5)
            path.lineTo(w, h*0.5)
            path.lineTo(0, h)
            path.lineTo(-w, h*0.5)
            path.lineTo(-w, -h*0.5)
            path.closeSubpath()
            painter.drawPath(path)
        elif self.symbol_type == SymbolType.ENUM:
            path = QPainterPath()
            path.moveTo(0, -self.radius)
            path.lineTo(self.radius, 0)
            path.lineTo(0, self.radius)
            path.lineTo(-self.radius, 0)
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.drawEllipse(QPointF(0, 0), self.radius, self.radius)

        # Draw label
        painter.setFont(self.font)
        painter.setPen(QPen(Qt.white))
        
        # Truncate label if too long
        display_label = self.label
        if len(display_label) > 20:
            display_label = display_label[:17] + "..."
            
        metrics = painter.fontMetrics()
        rect = metrics.boundingRect(display_label)
        painter.drawText(-rect.width() / 2, self.radius + 15, display_label)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            if self.scene():
                self.scene().update_edges()
        return super().itemChange(change, value)


class EdgeItem(QGraphicsItem):
    def __init__(self, source_node: NodeItem, target_node: NodeItem, edge_type: EdgeType):
        super().__init__()
        self.source_node = source_node
        self.target_node = target_node
        self.edge_type = edge_type
        self.setZValue(-1) # Draw behind nodes
        
        self.color = EDGE_COLORS.get(edge_type, QColor("#9E9E9E"))

    def boundingRect(self):
        return QRectF(self.source_node.pos(), self.target_node.pos()).normalized().adjusted(-10, -10, 10, 10)

    def paint(self, painter, option, widget):
        painter.setRenderHint(painter.Antialiasing)
        
        p1 = self.source_node.pos()
        p2 = self.target_node.pos()
        
        # Calculate line
        line = QPainterPath()
        line.moveTo(p1)
        line.lineTo(p2)
        
        pen = QPen(self.color, 2)
        if self.edge_type in (EdgeType.CALLS, EdgeType.USES_TYPE, EdgeType.REFERENCES):
            pen.setStyle(Qt.DashLine if self.edge_type == EdgeType.CALLS else Qt.DotLine)
            pen.setWidth(1)
            
        painter.setPen(pen)
        painter.drawPath(line)
        
        # Draw arrow head
        angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
        dest_x = p2.x() - self.target_node.radius * math.cos(angle)
        dest_y = p2.y() - self.target_node.radius * math.sin(angle)
        
        arrow_size = 10
        arrow_p1 = QPointF(dest_x - arrow_size * math.cos(angle - math.pi / 6),
                           dest_y - arrow_size * math.sin(angle - math.pi / 6))
        arrow_p2 = QPointF(dest_x - arrow_size * math.cos(angle + math.pi / 6),
                           dest_y - arrow_size * math.sin(angle + math.pi / 6))
        
        arrow_head = QPainterPath()
        arrow_head.moveTo(QPointF(dest_x, dest_y))
        arrow_head.lineTo(arrow_p1)
        arrow_head.lineTo(arrow_p2)
        arrow_head.closeSubpath()
        
        painter.setBrush(QBrush(self.color))
        painter.setPen(QPen(self.color, 1, Qt.SolidLine))
        painter.drawPath(arrow_head)


class InteractiveGraphScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.setBackgroundBrush(QBrush(QColor("#0a0a1a")))
        
        self.node_items = {} # id -> NodeItem
        self.edge_items = []
        
        self.nx_graph = nx.DiGraph()
        self.pos = {}
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.step_physics)
        
        # Physics params
        self.k = 100.0 # Spring length / ideal distance
        self.iterations_per_frame = 2
        self.physics_enabled = False
        
    def set_graph(self, analysis_graph: AnalysisGraph, seed_ids: set[str] = None):
        self.clear()
        self.node_items.clear()
        self.edge_items.clear()
        self.nx_graph.clear()
        self.pos.clear()
        
        if seed_ids is None:
            seed_ids = set()
            
        # Add nodes
        for sym in analysis_graph.symbols.values():
            if sym.symbol_type == SymbolType.INCLUDE: continue
            
            node_item = NodeItem(sym.id, sym.name, sym.symbol_type, sym.id in seed_ids)
            self.addItem(node_item)
            self.node_items[sym.id] = node_item
            self.nx_graph.add_node(sym.id)
            
        # Add edges
        for edge in analysis_graph.edges:
            if edge.source_id not in self.node_items or edge.target_id not in self.node_items:
                continue
                
            src_item = self.node_items[edge.source_id]
            tgt_item = self.node_items[edge.target_id]
            
            edge_item = EdgeItem(src_item, tgt_item, edge.edge_type)
            self.addItem(edge_item)
            self.edge_items.append(edge_item)
            
            # NetworkX for physics (undirected representation for spring layout works best)
            weight = 1.0
            if edge.edge_type == EdgeType.CONTAINS: weight = 3.0
            elif edge.edge_type == EdgeType.INHERITS: weight = 2.0
            elif edge.edge_type == EdgeType.CALLS: weight = 0.5
            
            self.nx_graph.add_edge(edge.source_id, edge.target_id, weight=weight)
            
        # Initial layout
        if self.nx_graph.number_of_nodes() > 0:
            self.pos = nx.spring_layout(self.nx_graph, k=self.k, iterations=50, scale=400)
            self.apply_positions()
            
    def apply_positions(self):
        for node_id, p in self.pos.items():
            if node_id in self.node_items:
                # If node is being dragged by user, don't update its position from physics
                item = self.node_items[node_id]
                if not item.isUnderMouse(): 
                    item.setPos(p[0], p[1])
        self.update_edges()
        
    def update_edges(self):
        for edge in self.edge_items:
            edge.prepareGeometryChange()
            # The edge itself will redraw in new pos

    def step_physics(self):
        if not self.nx_graph.nodes: return
        
        # Fix nodes being dragged
        fixed_nodes = [nid for nid, item in self.node_items.items() if item.isUnderMouse()]
        
        # Read current positions back from items (user might have dragged them)
        for nid, item in self.node_items.items():
            self.pos[nid] = (item.x(), item.y())
            
        # Run 1 iteration of spring layout
        try:
            self.pos = nx.spring_layout(self.nx_graph, pos=self.pos, fixed=fixed_nodes if fixed_nodes else None, 
                                        k=self.k, iterations=self.iterations_per_frame)
            self.apply_positions()
        except Exception:
            pass # Handle isolated nodes edge cases etc
            
    def start_physics(self):
        self.physics_enabled = True
        self.timer.start(30) # ~30 fps
        
    def stop_physics(self):
        self.physics_enabled = False
        self.timer.stop()


class GraphView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = InteractiveGraphScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        
    def wheelEvent(self, event):
        zoomInFactor = 1.15
        zoomOutFactor = 1 / zoomInFactor

        # Zoom
        if event.angleDelta().y() > 0:
            zoomFactor = zoomInFactor
        else:
            zoomFactor = zoomOutFactor
            
        self.scale(zoomFactor, zoomFactor)
        
    def set_graph(self, graph: AnalysisGraph, seed_ids: set[str] = None):
        self.scene.set_graph(graph, seed_ids)
        self.scene.start_physics()
