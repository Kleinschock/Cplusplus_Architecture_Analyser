/**
 * C++ Architecture Analyser — Interactive Graph Visualization
 * Uses Cytoscape.js with dagre/cola layouts
 */

// ---- State ----
let cy = null;
let currentLayout = 'dagre';
let activeEdgeFilters = new Set(['contains', 'inherits', 'calls', 'uses_type']);
let selectedNodeId = null;
let contextMenuNodeId = null;

// ---- Cytoscape Style ----
const cyStyle = [
    // Base node style
    {
        selector: 'node',
        style: {
            'label': 'data(label)',
            'background-color': 'data(color)',
            'shape': 'data(shape)',
            'width': 'label',
            'height': 'label',
            'padding': '10px',
            'font-family': 'Inter, sans-serif',
            'font-size': '11px',
            'font-weight': '500',
            'color': '#e8e8f0',
            'text-valign': 'center',
            'text-halign': 'center',
            'text-wrap': 'wrap',
            'text-max-width': '120px',
            'border-width': 1,
            'border-color': 'data(color)',
            'border-opacity': 0.4,
            'background-opacity': 0.85,
            'text-outline-color': '#0a0a1a',
            'text-outline-width': 2,
            'transition-property': 'background-opacity, border-width, width, height',
            'transition-duration': '0.2s',
        }
    },
    // Seed nodes (highlighted)
    {
        selector: 'node.seed',
        style: {
            'border-width': 3,
            'border-opacity': 1,
            'background-opacity': 1,
            'font-weight': '700',
            'font-size': '13px',
            'shadow-blur': 15,
            'shadow-color': 'data(color)',
            'shadow-opacity': 0.6,
        }
    },
    // Unresolved nodes (dimmed)
    {
        selector: 'node.unresolved',
        style: {
            'border-style': 'dashed',
            'background-opacity': 0.4,
            'text-opacity': 0.6,
        }
    },
    // Hover
    {
        selector: 'node:active',
        style: {
            'overlay-opacity': 0.08,
        }
    },
    // Selected node
    {
        selector: 'node:selected',
        style: {
            'border-width': 3,
            'border-color': '#ffffff',
            'border-opacity': 0.8,
        }
    },
    // Base edge style
    {
        selector: 'edge',
        style: {
            'width': 1.5,
            'line-color': 'data(color)',
            'target-arrow-color': 'data(color)',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.8,
            'curve-style': 'bezier',
            'opacity': 0.6,
            'font-size': '9px',
            'color': '#9898b0',
            'text-background-color': '#0a0a1a',
            'text-background-opacity': 0.8,
            'text-background-padding': '2px',
            'transition-property': 'opacity, width',
            'transition-duration': '0.2s',
        }
    },
    // Edge types
    {
        selector: 'edge.inherits',
        style: {
            'width': 2.5,
            'line-style': 'solid',
            'target-arrow-shape': 'triangle-backcurve',
            'arrow-scale': 1.0,
            'opacity': 0.8,
        }
    },
    {
        selector: 'edge.calls',
        style: {
            'line-style': 'dashed',
            'line-dash-pattern': [6, 3],
        }
    },
    {
        selector: 'edge.uses_type',
        style: {
            'line-style': 'dotted',
            'line-dash-pattern': [2, 3],
        }
    },
    {
        selector: 'edge.contains',
        style: {
            'line-style': 'solid',
            'opacity': 0.4,
            'width': 1,
        }
    },
    // Highlighted edges (connected to selected node)
    {
        selector: 'edge.highlighted',
        style: {
            'opacity': 1,
            'width': 2.5,
            'label': 'data(label)',
        }
    },
    // Dimmed (non-highlighted)
    {
        selector: '.dimmed',
        style: {
            'opacity': 0.15,
        }
    },
    // Hidden (filtered)
    {
        selector: '.edge-hidden',
        style: {
            'display': 'none',
        }
    },
];


// ---- Initialize ----
document.addEventListener('DOMContentLoaded', () => {
    initCytoscape();
    bindEvents();
});


function initCytoscape() {
    cy = cytoscape({
        container: document.getElementById('cy'),
        style: cyStyle,
        layout: { name: 'preset' },
        minZoom: 0.1,
        maxZoom: 5,
        wheelSensitivity: 0.3,
    });

    // Node click
    cy.on('tap', 'node', (e) => {
        const node = e.target;
        selectNode(node.id());
    });

    // Background click (deselect)
    cy.on('tap', (e) => {
        if (e.target === cy) {
            deselectAll();
        }
        hideContextMenu();
    });

    // Right-click context menu
    cy.on('cxttap', 'node', (e) => {
        const node = e.target;
        contextMenuNodeId = node.id();
        showContextMenu(e.originalEvent);
        e.originalEvent.preventDefault();
    });

    // Node hover tooltip
    cy.on('mouseover', 'node', (e) => {
        const node = e.target;
        const data = node.data();
        document.body.style.cursor = 'pointer';
    });

    cy.on('mouseout', 'node', () => {
        document.body.style.cursor = 'default';
    });
}


// ---- Event Binding ----
function bindEvents() {
    // Analyze button
    document.getElementById('analyze-btn').addEventListener('click', runAnalysis);

    // Enter key in inputs
    document.getElementById('symbol-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') runAnalysis();
    });
    document.getElementById('project-path').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') runAnalysis();
    });

    // Depth slider
    const depthSlider = document.getElementById('depth-slider');
    depthSlider.addEventListener('input', () => {
        document.getElementById('depth-value').textContent = depthSlider.value;
    });

    // Layout buttons
    document.querySelectorAll('[data-layout]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-layout]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentLayout = btn.dataset.layout;
            applyLayout();
        });
    });

    // Edge filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.classList.toggle('active');
            const edgeType = btn.dataset.edge;
            if (btn.classList.contains('active')) {
                activeEdgeFilters.add(edgeType);
            } else {
                activeEdgeFilters.delete(edgeType);
            }
            applyEdgeFilters();
        });
    });

    // Toolbar buttons
    document.getElementById('btn-fit').addEventListener('click', () => cy.fit(null, 40));
    document.getElementById('btn-export-png').addEventListener('click', exportPNG);
    document.getElementById('btn-export-dot').addEventListener('click', exportDOT);

    // Close detail panel
    document.getElementById('close-panel').addEventListener('click', () => {
        document.getElementById('detail-panel').classList.add('hidden');
        deselectAll();
    });

    // Context menu items
    document.querySelectorAll('.ctx-item').forEach(item => {
        item.addEventListener('click', () => {
            handleContextAction(item.dataset.action);
            hideContextMenu();
        });
    });

    // Click outside to close context menu
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#context-menu')) {
            hideContextMenu();
        }
    });
}


// ---- Analysis ----
async function runAnalysis() {
    const projectPath = document.getElementById('project-path').value.trim();
    const symbolInput = document.getElementById('symbol-input').value.trim();
    const depth = parseInt(document.getElementById('depth-slider').value);

    if (!projectPath) {
        showToast('Please enter a project path', 'error');
        return;
    }
    if (!symbolInput) {
        showToast('Please enter at least one symbol name', 'error');
        return;
    }

    const symbols = symbolInput.split(',').map(s => s.trim()).filter(Boolean);

    showLoading('Analyzing project...');
    document.getElementById('analyze-btn').disabled = true;

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_path: projectPath,
                symbols: symbols,
                depth: depth,
            })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Analysis failed');
        }

        const data = await response.json();
        loadGraph(data);
        showToast(`Found ${data.stats.total_nodes} symbols, ${data.stats.total_edges} relationships`, 'success');

    } catch (err) {
        showToast(err.message, 'error');
        console.error('Analysis error:', err);
    } finally {
        hideLoading();
        document.getElementById('analyze-btn').disabled = false;
    }
}


function loadGraph(data) {
    // Clear
    cy.elements().remove();
    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('toolbar').classList.remove('hidden');
    document.getElementById('legend').classList.remove('hidden');

    // Add elements
    cy.add(data.elements);

    // Apply layout
    applyLayout();
    applyEdgeFilters();

    // Update stats
    const badge = document.getElementById('stats-badge');
    badge.textContent = `${data.stats.total_nodes} nodes · ${data.stats.total_edges} edges`;
    badge.classList.remove('hidden');
}


// ---- Layout ----
function applyLayout() {
    if (cy.nodes().length === 0) return;

    const options = {
        dagre: {
            name: 'dagre',
            rankDir: 'TB',
            nodeSep: 40,
            rankSep: 60,
            edgeSep: 20,
            animate: true,
            animationDuration: 500,
            fit: true,
            padding: 40,
        },
        cola: {
            name: 'cola',
            animate: true,
            maxSimulationTime: 3000,
            fit: true,
            padding: 40,
            nodeSpacing: 25,
            edgeLength: 120,
            convergenceThreshold: 0.01,
        },
        circle: {
            name: 'circle',
            animate: true,
            animationDuration: 500,
            fit: true,
            padding: 40,
        },
    };

    const layout = cy.layout(options[currentLayout] || options.dagre);
    layout.run();
}


// ---- Selection ----
function selectNode(nodeId) {
    selectedNodeId = nodeId;

    // Highlight connected
    const node = cy.getElementById(nodeId);
    const connectedEdges = node.connectedEdges();
    const connectedNodes = connectedEdges.connectedNodes();

    // Dim all
    cy.elements().addClass('dimmed');

    // Highlight selected + connected
    node.removeClass('dimmed');
    connectedNodes.removeClass('dimmed');
    connectedEdges.removeClass('dimmed').addClass('highlighted');

    // Show detail panel
    fetchAndShowDetails(nodeId);
}

function deselectAll() {
    selectedNodeId = null;
    cy.elements().removeClass('dimmed').removeClass('highlighted');
    document.getElementById('detail-panel').classList.add('hidden');
}


// ---- Detail Panel ----
async function fetchAndShowDetails(nodeId) {
    const panel = document.getElementById('detail-panel');
    const content = document.getElementById('detail-content');
    const title = document.getElementById('detail-title');

    const nodeData = cy.getElementById(nodeId).data();

    // Set title
    title.textContent = nodeData.label;

    // Build content
    let html = '';

    // Type & file info
    html += '<div class="detail-section">';
    html += '<div class="detail-section-title">Info</div>';
    html += `<div class="detail-field"><span class="field-label">Type</span><span class="detail-tag tag-type">${nodeData.type}</span></div>`;
    html += `<div class="detail-field"><span class="field-label">Qualified</span><span class="field-value">${nodeData.qualified_name || '-'}</span></div>`;
    if (nodeData.file && nodeData.file !== '<unresolved>') {
        const shortFile = nodeData.file.split(/[/\\]/).slice(-2).join('/');
        html += `<div class="detail-field"><span class="field-label">File</span><span class="field-value">${shortFile}:${nodeData.line}</span></div>`;
    }
    if (nodeData.language) {
        html += `<div class="detail-field"><span class="field-label">Language</span><span class="field-value">${nodeData.language}</span></div>`;
    }
    html += '</div>';

    // Tags
    const tags = [];
    if (nodeData.access && nodeData.access !== 'none') {
        tags.push({ label: nodeData.access, cls: `tag-access-${nodeData.access}` });
    }
    if (nodeData.is_virtual) tags.push({ label: 'virtual', cls: 'tag-virtual' });
    if (nodeData.is_static) tags.push({ label: 'static', cls: 'tag-static' });
    if (nodeData.is_const) tags.push({ label: 'const', cls: 'tag-const' });
    if (nodeData.is_override) tags.push({ label: 'override', cls: 'tag-virtual' });
    if (nodeData.is_pure_virtual) tags.push({ label: 'pure virtual', cls: 'tag-virtual' });

    if (tags.length > 0) {
        html += '<div class="detail-section">';
        html += '<div class="detail-section-title">Qualifiers</div>';
        tags.forEach(t => { html += `<span class="detail-tag ${t.cls}">${t.label}</span>`; });
        html += '</div>';
    }

    // Signature
    if (nodeData.signature || nodeData.display_name) {
        html += '<div class="detail-section">';
        html += '<div class="detail-section-title">Signature</div>';
        html += `<div class="field-value" style="font-size: 11px; word-break: break-all;">${nodeData.signature || nodeData.display_name}</div>`;
        html += '</div>';
    }

    // Parameters
    if (nodeData.parameters && nodeData.parameters.length > 0) {
        html += '<div class="detail-section">';
        html += '<div class="detail-section-title">Parameters</div>';
        html += '<ul class="member-list">';
        nodeData.parameters.forEach(p => {
            const def = p.default ? ` = ${p.default}` : '';
            html += `<li><span class="member-icon" style="background:#42A5F530;color:#42A5F5">P</span>${p.type} ${p.name}${def}</li>`;
        });
        html += '</ul></div>';
    }

    // Return type
    if (nodeData.return_type) {
        html += '<div class="detail-section">';
        html += `<div class="detail-field"><span class="field-label">Returns</span><span class="field-value">${nodeData.return_type}</span></div>`;
        html += '</div>';
    }

    // Base classes
    if (nodeData.base_classes && nodeData.base_classes.length > 0) {
        html += '<div class="detail-section">';
        html += '<div class="detail-section-title">Inherits From</div>';
        html += '<ul class="member-list">';
        nodeData.base_classes.forEach(b => {
            html += `<li><span class="member-icon" style="background:#FF704330;color:#FF7043">▲</span>${b}</li>`;
        });
        html += '</ul></div>';
    }

    // Connected edges
    const node = cy.getElementById(nodeId);
    const outEdges = node.connectedEdges(`[source = "${nodeId}"]`);
    const inEdges = node.connectedEdges(`[target = "${nodeId}"]`);

    // Members (outgoing CONTAINS)
    const members = outEdges.filter('[type = "contains"]');
    if (members.length > 0) {
        html += '<div class="detail-section">';
        html += `<div class="detail-section-title">Members (${members.length})</div>`;
        html += '<ul class="member-list">';
        members.forEach(e => {
            const target = cy.getElementById(e.data('target'));
            if (target.length) {
                const d = target.data();
                const icon = getTypeIcon(d.type);
                html += `<li onclick="selectNode('${d.id}')">${icon}${d.label}</li>`;
            }
        });
        html += '</ul></div>';
    }

    // Callers (incoming CALLS)
    const callers = inEdges.filter('[type = "calls"]');
    if (callers.length > 0) {
        html += '<div class="detail-section">';
        html += `<div class="detail-section-title">Called By (${callers.length})</div>`;
        html += '<ul class="member-list">';
        callers.forEach(e => {
            const source = cy.getElementById(e.data('source'));
            if (source.length) {
                const d = source.data();
                const icon = getTypeIcon(d.type);
                html += `<li onclick="selectNode('${d.id}')">${icon}${d.label}</li>`;
            }
        });
        html += '</ul></div>';
    }

    // Callees (outgoing CALLS)
    const callees = outEdges.filter('[type = "calls"]');
    if (callees.length > 0) {
        html += '<div class="detail-section">';
        html += `<div class="detail-section-title">Calls (${callees.length})</div>`;
        html += '<ul class="member-list">';
        callees.forEach(e => {
            const target = cy.getElementById(e.data('target'));
            if (target.length) {
                const d = target.data();
                const icon = getTypeIcon(d.type);
                html += `<li onclick="selectNode('${d.id}')">${icon}${d.label}</li>`;
            }
        });
        html += '</ul></div>';
    }

    // Inheritance (incoming/outgoing INHERITS)
    const inheritsFrom = outEdges.filter('[type = "inherits"]');
    const inheritedBy = inEdges.filter('[type = "inherits"]');
    if (inheritsFrom.length > 0 || inheritedBy.length > 0) {
        html += '<div class="detail-section">';
        html += '<div class="detail-section-title">Inheritance</div>';
        html += '<ul class="member-list">';
        inheritsFrom.forEach(e => {
            const t = cy.getElementById(e.data('target'));
            if (t.length) {
                html += `<li onclick="selectNode('${t.data('id')}')"><span class="member-icon" style="background:#FF704330;color:#FF7043">▲</span>extends ${t.data('label')}</li>`;
            }
        });
        inheritedBy.forEach(e => {
            const s = cy.getElementById(e.data('source'));
            if (s.length) {
                html += `<li onclick="selectNode('${s.data('id')}')"><span class="member-icon" style="background:#AB47BC30;color:#AB47BC">▼</span>${s.data('label')} extends this</li>`;
            }
        });
        html += '</ul></div>';
    }

    content.innerHTML = html;
    panel.classList.remove('hidden');
}


function getTypeIcon(type) {
    const icons = {
        'class': '<span class="member-icon" style="background:#4A9EFF30;color:#4A9EFF">C</span>',
        'struct': '<span class="member-icon" style="background:#5BA8FF30;color:#5BA8FF">S</span>',
        'function': '<span class="member-icon" style="background:#47D18530;color:#47D185">F</span>',
        'method': '<span class="member-icon" style="background:#3BC47830;color:#3BC478">M</span>',
        'member_variable': '<span class="member-icon" style="background:#B07FE030;color:#B07FE0">V</span>',
        'enum': '<span class="member-icon" style="background:#FF8C4230;color:#FF8C42">E</span>',
        'enum_value': '<span class="member-icon" style="background:#FFB07A30;color:#FFB07A">e</span>',
        'namespace': '<span class="member-icon" style="background:#26C6DA30;color:#26C6DA">N</span>',
        'constructor': '<span class="member-icon" style="background:#81C78430;color:#81C784">+</span>',
        'destructor': '<span class="member-icon" style="background:#E5737330;color:#E57373">~</span>',
    };
    return icons[type] || '<span class="member-icon" style="background:#9E9E9E30;color:#9E9E9E">?</span>';
}


// ---- Edge Filtering ----
function applyEdgeFilters() {
    cy.edges().forEach(edge => {
        const type = edge.data('type');
        if (activeEdgeFilters.has(type)) {
            edge.removeClass('edge-hidden');
        } else {
            edge.addClass('edge-hidden');
        }
    });
}


// ---- Context Menu ----
function showContextMenu(event) {
    const menu = document.getElementById('context-menu');
    menu.style.left = event.pageX + 'px';
    menu.style.top = event.pageY + 'px';
    menu.classList.remove('hidden');
}

function hideContextMenu() {
    document.getElementById('context-menu').classList.add('hidden');
    contextMenuNodeId = null;
}

async function handleContextAction(action) {
    if (!contextMenuNodeId) return;

    switch (action) {
        case 'expand':
            await expandNode(contextMenuNodeId);
            break;
        case 'members':
            selectNode(contextMenuNodeId);
            break;
        case 'hierarchy':
            selectNode(contextMenuNodeId);
            break;
        case 'callers':
            selectNode(contextMenuNodeId);
            break;
        case 'callees':
            selectNode(contextMenuNodeId);
            break;
        case 'remove':
            removeNode(contextMenuNodeId);
            break;
    }
}

async function expandNode(nodeId) {
    showLoading('Expanding connections...');
    try {
        const response = await fetch('/api/expand', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol_id: nodeId, depth: 1 }),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error);
        }

        const data = await response.json();

        // Add new elements
        const existingIds = new Set(cy.nodes().map(n => n.id()));
        const newElements = data.elements.filter(el => {
            if (el.data.source) {
                // Edge
                return !cy.getElementById(el.data.id).length;
            }
            // Node
            return !existingIds.has(el.data.id);
        });

        if (newElements.length > 0) {
            cy.add(newElements);
            applyLayout();
            applyEdgeFilters();
            showToast(`Added ${newElements.length} elements`, 'success');
        } else {
            showToast('No new connections found', 'success');
        }
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        hideLoading();
    }
}

function removeNode(nodeId) {
    cy.getElementById(nodeId).remove();
    if (selectedNodeId === nodeId) {
        deselectAll();
    }
}


// ---- Export ----
function exportPNG() {
    const png = cy.png({
        output: 'blob',
        bg: '#0a0a1a',
        scale: 2,
        full: true,
    });

    const url = URL.createObjectURL(png);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'architecture_graph.png';
    a.click();
    URL.revokeObjectURL(url);
    showToast('PNG exported!', 'success');
}

async function exportDOT() {
    try {
        const response = await fetch('/api/export/dot');
        if (!response.ok) throw new Error('Export failed');
        const dot = await response.text();

        const blob = new Blob([dot], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'architecture_graph.dot';
        a.click();
        URL.revokeObjectURL(url);
        showToast('DOT exported!', 'success');
    } catch (err) {
        showToast(err.message, 'error');
    }
}


// ---- Loading ----
function showLoading(text) {
    document.getElementById('loading-text').textContent = text || 'Loading...';
    document.getElementById('loading-overlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
}


// ---- Toast ----
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
