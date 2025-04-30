import dash
from dash import dcc, html, Input, Output, State, callback, ctx, no_update
import dash_cytoscape as cyto
import networkx as nx
import uuid
import enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime
import json # For serializing complex objects in node attributes if needed

# --- Data Classes and DialogueGraph (from dialogue_node_classes_nx_v1) ---

@dataclass
class Speaker:
    """Base class for representing who is speaking."""
    pass

@dataclass
class SpecificSpeaker(Speaker):
    """Represents a specifically named character."""
    name: str
    def __str__(self): return self.name
    def to_dict(self): return {'type': 'specific', 'name': self.name}
    @classmethod
    def from_dict(cls, data):
        if data and data.get('type') == 'specific':
            return cls(name=data['name'])
        return None


@dataclass
class GenericSpeaker(Speaker):
    """Represents a generic dialogue participant (e.g., Player, NPC 1)."""
    identifier: str
    def __str__(self): return self.identifier
    def to_dict(self): return {'type': 'generic', 'identifier': self.identifier}
    @classmethod
    def from_dict(cls, data):
        if data and data.get('type') == 'generic':
            return cls(identifier=data['identifier'])
        return None

def speaker_from_dict(data):
    """Helper to reconstruct speaker objects."""
    if isinstance(data, dict):
        if data.get('type') == 'specific':
            return SpecificSpeaker.from_dict(data)
        elif data.get('type') == 'generic':
            return GenericSpeaker.from_dict(data)
    elif isinstance(data, Speaker):
        return data
    return None

class NodeType(enum.Enum):
    NPC_LINE = "NPC_LINE"
    PLAYER_CHOICE = "PLAYER_CHOICE"

@dataclass
class TextVersion:
    text: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = "manual"
    metadata: Optional[Dict[str, Any]] = None
    def to_dict(self):
        return {
            'text': self.text,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source,
            'metadata': self.metadata
        }
    @classmethod
    def from_dict(cls, data):
        return cls(
            text=data['text'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            source=data['source'],
            metadata=data.get('metadata')
        )

@dataclass
class DialogueNode:
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    node_type: NodeType = NodeType.NPC_LINE
    speaker: Optional[Speaker] = None
    text_history: List[TextVersion] = field(default_factory=list)
    generation_metadata: Optional[Dict[str, Any]] = field(default_factory=dict)
    custom_metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def add_text_version(self, text: str, source: str = "manual", metadata: Optional[Dict[str, Any]] = None):
        version = TextVersion(text=text, source=source, metadata=metadata)
        self.text_history.append(version)

    @property
    def current_text(self) -> Optional[str]:
        if not self.text_history: return None
        return self.text_history[-1].text

    def set_current_text(self, text: str, source: str = "manual_edit", metadata: Optional[Dict[str, Any]] = None):
        self.add_text_version(text=text, source=source, metadata=metadata)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_type": self.node_type.value,
            "speaker": self.speaker.to_dict() if self.speaker else None,
            "text_history": [th.to_dict() for th in self.text_history],
            "generation_metadata": self.generation_metadata,
            "custom_metadata": self.custom_metadata,
        }

    @classmethod
    def from_dict(cls, node_id: str, data: Dict[str, Any]) -> 'DialogueNode':
        try:
             node_type_val = data.get("node_type")
             node_type = NodeType(node_type_val) if node_type_val else NodeType.NPC_LINE
             speaker_data = data.get("speaker")
             speaker = speaker_from_dict(speaker_data)
             history_data = data.get("text_history", [])
             # Ensure history_data is a list before iterating
             if not isinstance(history_data, list):
                  history_data = []
             text_history = [TextVersion.from_dict(th_data) for th_data in history_data]
             return cls(
                 node_id=node_id,
                 node_type=node_type,
                 speaker=speaker,
                 text_history=text_history,
                 generation_metadata=data.get("generation_metadata", {}),
                 custom_metadata=data.get("custom_metadata", {})
             )
        except Exception as e:
             print(f"Error reconstructing DialogueNode {node_id} from dict: {e}")
             # Provide a more informative error node
             return cls(node_id=node_id, text_history=[TextVersion(text=f"Error loading node data: {e}", source="error")])


class DialogueGraph:
    def __init__(self, graph_data=None):
        if graph_data:
            # Ensure data is valid before attempting to load
            if isinstance(graph_data, dict) and 'nodes' in graph_data and 'links' in graph_data:
                 try:
                     self.graph = nx.node_link_graph(graph_data, directed=True, multigraph=False)
                 except Exception as e:
                      print(f"Error loading graph from data: {e}. Initializing empty graph.")
                      self.graph = nx.DiGraph()
            else:
                 print("Invalid graph data format provided. Initializing empty graph.")
                 self.graph = nx.DiGraph()
        else:
            self.graph = nx.DiGraph()

    def to_dict(self):
        # Ensure graph exists before trying to serialize
        return nx.node_link_data(self.graph) if self.graph else {'nodes': [], 'links': []}

    def add_node(self, node_data: DialogueNode):
        if not self.graph: self.graph = nx.DiGraph() # Ensure graph exists
        if node_data.node_id in self.graph:
            print(f"Warning: Node {node_data.node_id} already exists. Updating attributes.")
        self.graph.add_node(node_data.node_id, **node_data.to_dict())

    def get_node_data(self, node_id: str) -> Optional[DialogueNode]:
        if not self.graph or node_id not in self.graph: return None # Check graph exists
        try:
            # Check if node data exists before accessing
            node_attrs = self.graph.nodes.get(node_id)
            if node_attrs is None:
                 print(f"Warning: Node {node_id} found in graph but has no attributes.")
                 return None
            return DialogueNode.from_dict(node_id, node_attrs)
        except Exception as e:
            print(f"Error reconstructing node {node_id}: {e}")
            return None

    def update_node_data(self, node_data: DialogueNode):
        if not self.graph or node_data.node_id not in self.graph: # Check graph exists
             raise ValueError(f"Node {node_data.node_id} does not exist in the graph.")
        node_attrs = node_data.to_dict()
        # Update attributes safely
        nx.set_node_attributes(self.graph, {node_data.node_id: node_attrs})


    def add_edge(self, parent_id: str, child_id: str, **kwargs) -> bool:
        if not self.graph: self.graph = nx.DiGraph() # Ensure graph exists
        if parent_id not in self.graph or child_id not in self.graph:
            print(f"Error: Node {parent_id} or {child_id} not in graph.")
            return False
        if self.is_reachable(child_id, parent_id):
            print(f"Error: Adding edge {parent_id} -> {child_id} would create a cycle.")
            return False
        self.graph.add_edge(parent_id, child_id, **kwargs)
        return True

    # --- Added remove_edge method ---
    def remove_edge(self, parent_id: str, child_id: str):
         """Removes an edge between two nodes if it exists."""
         if not self.graph: return # Check graph exists
         if self.graph.has_edge(parent_id, child_id):
             self.graph.remove_edge(parent_id, child_id)
             print(f"Removed edge {parent_id} -> {child_id}")
         else:
              print(f"Warning: Edge {parent_id} -> {child_id} does not exist.")

    def get_children(self, node_id: str) -> List[str]:
        if not self.graph or node_id not in self.graph: return [] # Check graph exists
        return list(self.graph.successors(node_id))

    def get_parents(self, node_id: str) -> List[str]:
        if not self.graph or node_id not in self.graph: return [] # Check graph exists
        return list(self.graph.predecessors(node_id))

    def get_siblings(self, node_id: str) -> List[str]:
        siblings = set()
        parents = self.get_parents(node_id) # Checks graph existence
        if not parents: return []
        first_parent = parents[0]
        for child in self.get_children(first_parent): # Checks graph existence
            if child != node_id: siblings.add(child)
        return list(siblings)

    def get_path(self, start_id: str, end_id: str) -> Optional[List[str]]:
        if not self.graph or start_id not in self.graph or end_id not in self.graph: return None # Check graph exists
        try:
            return nx.shortest_path(self.graph, source=start_id, target=end_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            try:
                 paths = list(nx.all_simple_paths(self.graph, source=start_id, target=end_id))
                 return paths[0] if paths else None
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                 return None

    def is_reachable(self, start_id: str, end_id: str) -> bool:
        """Checks if end_id is reachable from start_id using NetworkX."""
        if not self.graph or start_id not in self.graph or end_id not in self.graph: # Check graph exists
            return False
        if start_id == end_id:
            return True
        try:
            return nx.has_path(self.graph, start_id, end_id)
        except nx.NodeNotFound:
            return False

    def get_all_node_ids(self) -> List[str]:
        return list(self.graph.nodes) if self.graph else [] # Check graph exists

    def get_root_nodes(self) -> List[str]:
        return [node for node, degree in self.graph.in_degree() if degree == 0] if self.graph else [] # Check graph exists

# --- Helper Functions ---

def setup_initial_graph() -> DialogueGraph:
    """Creates a simple initial graph for demonstration."""
    dg = DialogueGraph()
    player = GenericSpeaker(identifier="Player")
    npc = SpecificSpeaker(name="Mysterious Guide")

    root_node = DialogueNode(node_type=NodeType.NPC_LINE, speaker=npc)
    root_node.add_text_version("You stand at a crossroads. Which path will you choose?", source="initial")
    dg.add_node(root_node)

    choice_node = DialogueNode(node_type=NodeType.PLAYER_CHOICE)
    dg.add_node(choice_node)
    dg.add_edge(root_node.node_id, choice_node.node_id)

    path1_node = DialogueNode(node_type=NodeType.NPC_LINE, speaker=player)
    path1_node.add_text_version("I'll take the path through the forest.", source="initial")
    dg.add_node(path1_node)
    dg.add_edge(choice_node.node_id, path1_node.node_id, choice_label="Forest")

    path1_followup = DialogueNode(node_type=NodeType.NPC_LINE, speaker=npc)
    path1_followup.add_text_version("The forest is dark and deep. Be wary.", source="initial")
    dg.add_node(path1_followup)
    dg.add_edge(path1_node.node_id, path1_followup.node_id)

    path2_node = DialogueNode(node_type=NodeType.NPC_LINE, speaker=player)
    path2_node.add_text_version("The mountain pass seems more direct.", source="initial")
    dg.add_node(path2_node)
    dg.add_edge(choice_node.node_id, path2_node.node_id, choice_label="Mountain")

    path2_followup = DialogueNode(node_type=NodeType.NPC_LINE, speaker=npc)
    path2_followup.add_text_version("The winds howl fiercely on the pass. Tread carefully.", source="initial")
    dg.add_node(path2_followup)
    dg.add_edge(path2_node.node_id, path2_followup.node_id)

    deep_node = DialogueNode(node_type=NodeType.NPC_LINE, speaker=npc)
    deep_node.add_text_version("You found a hidden spring!", source="initial")
    dg.add_node(deep_node)
    dg.add_edge(path1_followup.node_id, deep_node.node_id)

    return dg

def build_chat_history_display(dg: DialogueGraph, path: List[str]) -> List[html.Div]:
    """Constructs Dash HTML components for chat history."""
    history_elements = []
    if not path:
        return [html.P("Dialogue history is empty.")]

    for node_id in path:
        node_data = dg.get_node_data(node_id)
        if node_data and node_data.node_type != NodeType.PLAYER_CHOICE:
            speaker_name = str(node_data.speaker) if node_data.speaker else "Narrator"
            text = node_data.current_text or "[No text]"
            style = {'padding': '8px', 'margin': '4px 0', 'borderRadius': '5px', 'maxWidth': '80%'}
            # Use global player variable defined later in __main__
            if isinstance(node_data.speaker, GenericSpeaker) and node_data.speaker.identifier == player.identifier:
                 style.update({'backgroundColor': '#e0f0ff', 'marginLeft': 'auto', 'textAlign': 'right'})
            else:
                 style.update({'backgroundColor': '#f0f0f0', 'marginRight': 'auto'})

            history_elements.append(
                html.Div([
                    html.Strong(f"{speaker_name}:"),
                    html.P(text, style={'margin': '2px 0 0 0'})
                ], style=style)
            )
    return history_elements

def networkx_to_cytoscape(dg: DialogueGraph, current_node_id: Optional[str]) -> List[Dict[str, Any]]:
    """Converts NetworkX graph to Cytoscape elements format."""
    elements = []
    if not dg or not dg.graph: return []

    for node_id in dg.graph.nodes:
        node_data = dg.get_node_data(node_id)
        label = f"{node_id[:6]}..."
        node_class = 'npc-node'

        if node_data:
            if node_data.node_type == NodeType.PLAYER_CHOICE:
                label = "Choice"
                node_class = 'choice-node'
            elif node_data.current_text:
                label = node_data.current_text[:20] + ('...' if len(node_data.current_text) > 20 else '')
                if isinstance(node_data.speaker, GenericSpeaker) and node_data.speaker.identifier == player.identifier:
                     node_class = 'player-node'

        cy_node = {
            'data': {'id': node_id, 'label': label},
            'classes': node_class
        }
        elements.append(cy_node)

    for source, target, edge_data in dg.graph.edges(data=True):
        elements.append({
            'data': {
                'source': source,
                'target': target,
                'label': edge_data.get('choice_label', '')
            }
        })
    return elements

# --- Dash App Setup ---

app = dash.Dash(__name__, suppress_callback_exceptions=True)
server = app.server

player = GenericSpeaker(identifier="Player") # Define player globally

initial_dg = setup_initial_graph()
initial_roots = initial_dg.get_root_nodes()
initial_start_node_id = initial_roots[0] if initial_roots else None
initial_path = [initial_start_node_id] if initial_start_node_id else []

default_stylesheet = [
    {'selector': 'node', 'style': {'label': 'data(label)', 'background-color': '#ccc', 'shape': 'round-rectangle', 'width': 'label', 'height': 'label', 'padding': '10px', 'text-wrap': 'wrap', 'text-max-width': '80px'}},
    {'selector': 'edge', 'style': {'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'label': 'data(label)', 'font-size': '10px', 'text-rotation': 'autorotate'}},
    {'selector': '.choice-node', 'style': {'background-color': '#ffcc00', 'shape': 'diamond'}},
    {'selector': '.player-node', 'style': {'background-color': '#e0f0ff'}},
    {'selector': '.npc-node', 'style': {'background-color': '#f0f0f0'}},
]


# --- App Layout ---
app.layout = html.Div([
    html.H1("Dialogue DAG Editor (Dash + NetworkX + Cytoscape)"),

    # Stores
    dcc.Store(id='graph-store', data=initial_dg.to_dict()),
    dcc.Store(id='current-node-store', data=initial_start_node_id),
    dcc.Store(id='current-path-store', data=initial_path),
    dcc.Store(id='status-message-store', data="Graph loaded."),

    html.Div([ # Main container
        # Left Panel
        html.Div([
            html.H3("Dialogue Flow"),
            html.Div(id='chat-history-display', style={'height': '300px', 'overflowY': 'scroll', 'border': '1px solid #ccc', 'marginBottom': '10px', 'padding': '5px'}), # Reduced height

            html.H4("Current Node Info"),
            html.Pre(id='current-node-info', style={'border': '1px solid #eee', 'padding': '5px', 'minHeight': '50px', 'whiteSpace': 'pre-wrap', 'marginBottom': '10px'}),

            # --- Edit Area ---
            html.H4("Edit Node Text"),
            dcc.Textarea(
                id='edit-node-textarea',
                style={'width': '100%', 'height': 80, 'marginBottom': '5px'},
                disabled=True # Disabled initially
            ),
            html.Button('Save Text Edit', id='save-edit-btn', n_clicks=0, disabled=True, style={'marginBottom': '15px'}),
            # --- End Edit Area ---

            html.Div(id='choice-button-container', style={'marginBottom': '10px'}),

            html.H4("Navigation & Actions"),
            html.Button('<- Prev Sibling', id='prev-sibling-btn', n_clicks=0, style={'marginRight': '5px'}),
            html.Button('Next Sibling ->', id='next-sibling-btn', n_clicks=0, style={'marginRight': '5px'}),
            html.Button('Go Up', id='go-up-btn', n_clicks=0, style={'marginRight': '15px'}),

            html.Button('Add New Child (Placeholder)', id='add-child-btn', n_clicks=0, style={'marginRight': '5px'}),

            dcc.Dropdown(id='link-child-dropdown', placeholder="Select node to link as child...", style={'display': 'inline-block', 'width': '250px', 'marginRight': '5px', 'verticalAlign': 'middle'}),
            html.Button('Link Selected Child', id='link-child-btn', n_clicks=0, style={'verticalAlign': 'middle'}),

            # --- Remove Child Area ---
            html.H4("Manage Children", style={'marginTop': '15px'}),
            dcc.Dropdown(id='remove-child-dropdown', placeholder="Select child to remove...", style={'display': 'inline-block', 'width': '250px', 'marginRight': '5px', 'verticalAlign': 'middle'}),
            html.Button('Remove Selected Child', id='remove-child-btn', n_clicks=0, style={'verticalAlign': 'middle'}),
            # --- End Remove Child Area ---

            html.Div(id='status-display', style={'marginTop': '15px', 'color': 'grey'}),

        ], style={'width': '48%', 'paddingRight': '2%', 'display': 'inline-block', 'verticalAlign': 'top'}), # End Left Panel

        # Right Panel
        html.Div([
            html.H3("Graph Visualization"),
            cyto.Cytoscape(
                id='cytoscape-graph',
                layout={'name': 'breadthfirst',
                        'roots': f'[id = "{initial_start_node_id}"]' if initial_start_node_id else None,
                        'directed': True,
                        'padding': 10},
                style={'width': '100%', 'height': '750px', 'border': '1px solid black'}, # Increased height
                elements=networkx_to_cytoscape(initial_dg, initial_start_node_id),
                stylesheet=default_stylesheet
            )
        ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'}) # End Right Panel

    ]) # End Main Container

])

# --- Callbacks ---

# Combined callback to update UI elements based on current state
@callback(
    # Existing Outputs
    Output('chat-history-display', 'children'),
    Output('current-node-info', 'children'),
    Output('choice-button-container', 'children'),
    Output('prev-sibling-btn', 'disabled'),
    Output('next-sibling-btn', 'disabled'),
    Output('go-up-btn', 'disabled'),
    Output('add-child-btn', 'disabled'),
    Output('link-child-dropdown', 'options'),
    Output('link-child-dropdown', 'value'),
    Output('link-child-btn', 'disabled'),
    Output('status-display', 'children'),
    # New Outputs for Edit/Remove
    Output('edit-node-textarea', 'value'),
    Output('edit-node-textarea', 'disabled'),
    Output('save-edit-btn', 'disabled'),
    Output('remove-child-dropdown', 'options'),
    Output('remove-child-dropdown', 'value'),
    Output('remove-child-btn', 'disabled'),
    # Inputs
    Input('current-node-store', 'data'),
    Input('current-path-store', 'data'),
    Input('graph-store', 'data'),
    State('status-message-store', 'data')
)
def update_main_ui(current_node_id, current_path, graph_data, status_msg):
    # Default values for outputs in case of error
    default_outputs = {
        'chat-history-display': ["No node selected."],
        'current-node-info': "N/A",
        'choice-button-container': [],
        'prev-sibling-btn': True, 'next-sibling-btn': True, 'go-up-btn': True,
        'add-child-btn': True,
        'link-child-dropdown-opts': [], 'link-child-dropdown-val': None, 'link-child-btn': True,
        'status-display': "Error: Invalid state.",
        'edit-textarea-val': "", 'edit-textarea-disabled': True, 'save-edit-btn': True,
        'remove-child-opts': [], 'remove-child-val': None, 'remove-child-btn': True
    }
    # Helper function to return all outputs
    def make_output(updates):
        # Order must match the Output list
        return (
            updates.get('chat-history-display', default_outputs['chat-history-display']),
            updates.get('current-node-info', default_outputs['current-node-info']),
            updates.get('choice-button-container', default_outputs['choice-button-container']),
            updates.get('prev-sibling-btn', default_outputs['prev-sibling-btn']),
            updates.get('next-sibling-btn', default_outputs['next-sibling-btn']),
            updates.get('go-up-btn', default_outputs['go-up-btn']),
            updates.get('add-child-btn', default_outputs['add-child-btn']),
            updates.get('link-child-dropdown-opts', default_outputs['link-child-dropdown-opts']),
            updates.get('link-child-dropdown-val', default_outputs['link-child-dropdown-val']),
            updates.get('link-child-btn', default_outputs['link-child-btn']),
            updates.get('status-display', default_outputs['status-display']),
            updates.get('edit-textarea-val', default_outputs['edit-textarea-val']),
            updates.get('edit-textarea-disabled', default_outputs['edit-textarea-disabled']),
            updates.get('save-edit-btn', default_outputs['save-edit-btn']),
            updates.get('remove-child-opts', default_outputs['remove-child-opts']),
            updates.get('remove-child-val', default_outputs['remove-child-val']),
            updates.get('remove-child-btn', default_outputs['remove-child-btn'])
        )

    if not current_node_id or not graph_data:
        dg_check = DialogueGraph(graph_data)
        roots_check = dg_check.get_root_nodes()
        if roots_check:
             current_node_id = roots_check[0]
             current_path = [current_node_id]
             status_msg = "Resetting to root node."
        else:
             return make_output({'status-display': "Error: Invalid state or empty graph."})


    dg = DialogueGraph(graph_data)
    current_node = dg.get_node_data(current_node_id)

    if not current_node:
         roots = dg.get_root_nodes()
         if roots:
             current_node_id = roots[0]
             current_path = [current_node_id]
             current_node = dg.get_node_data(current_node_id)
             status_msg = f"Error: Node not found, reset to root {current_node_id[:6]}."
             if not current_node:
                  return make_output({'status-display': "Fatal Error: Cannot load root node."})
         else:
              return make_output({'status-display': "Error: Cannot find valid node."})

    # --- Calculate UI values ---
    outputs = {} # Dictionary to hold calculated outputs

    # 1. Chat History
    outputs['chat-history-display'] = build_chat_history_display(dg, current_path)

    # 2. Node Info
    node_info_text = f"ID: {current_node.node_id}\nType: {current_node.node_type.name}\n"
    if current_node.speaker: node_info_text += f"Speaker: {current_node.speaker}\n"
    # Add text history count
    node_info_text += f"Text Versions: {len(current_node.text_history)}\n"
    if current_node.current_text: node_info_text += f"\nCurrent Text: {current_node.current_text}"
    elif current_node.node_type == NodeType.PLAYER_CHOICE: node_info_text += "Player makes a choice."
    outputs['current-node-info'] = node_info_text

    # 3. Choice Buttons
    choice_buttons = []
    if current_node.node_type == NodeType.PLAYER_CHOICE:
        children = dg.get_children(current_node_id)
        for i, child_id in enumerate(children):
            child_node = dg.get_node_data(child_id)
            edge_data = dg.graph.get_edge_data(current_node_id, child_id, default={})
            choice_text = edge_data.get('choice_label')
            if not choice_text: choice_text = child_node.current_text if child_node and child_node.current_text else f"Option {i+1}"
            choice_buttons.append(html.Button(choice_text, id={'type': 'choice-btn', 'index': child_id}, n_clicks=0, style={'marginRight': '5px', 'marginBottom': '5px'}))
    outputs['choice-button-container'] = choice_buttons

    # 4. Button States (Navigation)
    parents = dg.get_parents(current_node_id)
    outputs['go-up-btn'] = not bool(parents)
    can_go_prev = False
    can_go_next = False
    if parents:
        first_parent_children = dg.get_children(parents[0])
        if current_node_id in first_parent_children:
            try:
                current_index = first_parent_children.index(current_node_id)
                can_go_prev = current_index > 0
                can_go_next = current_index < len(first_parent_children) - 1
            except ValueError: pass
    outputs['prev-sibling-btn'] = not can_go_prev
    outputs['next-sibling-btn'] = not can_go_next

    # 5. Button States (Actions) & Dropdowns
    # Disable editing/adding/linking/removing from PLAYER_CHOICE nodes
    is_choice_node = current_node.node_type == NodeType.PLAYER_CHOICE
    outputs['add-child-btn'] = is_choice_node
    outputs['link-child-btn'] = is_choice_node
    outputs['edit-textarea-disabled'] = is_choice_node or not current_node.current_text # Disable if no text
    outputs['save-edit-btn'] = is_choice_node or not current_node.current_text

    all_nodes = dg.get_all_node_ids()
    outputs['link-child-dropdown-opts'] = [{'label': f"{nid[:6]}... ({dg.get_node_data(nid).current_text[:15] if dg.get_node_data(nid) and dg.get_node_data(nid).current_text else 'Choice/Empty'}...)", 'value': nid}
                                            for nid in all_nodes if nid != current_node_id and not dg.is_reachable(nid, current_node_id)]
    outputs['link-child-dropdown-val'] = None

    current_children = dg.get_children(current_node_id)
    outputs['remove-child-opts'] = [{'label': f"{cid[:6]}... ({dg.get_node_data(cid).current_text[:15] if dg.get_node_data(cid) and dg.get_node_data(cid).current_text else 'Choice/Empty'}...)", 'value': cid}
                                     for cid in current_children]
    outputs['remove-child-val'] = None
    outputs['remove-child-btn'] = not bool(current_children) # Disable if no children

    # 6. Edit Text Area Value
    outputs['edit-textarea-val'] = current_node.current_text if not is_choice_node and current_node.current_text else ""

    # 7. Status Display
    outputs['status-display'] = status_msg

    return make_output(outputs)


# Callback to update Cytoscape graph elements
@callback(
    Output('cytoscape-graph', 'elements'),
    Input('graph-store', 'data'),
    State('current-node-store', 'data')
)
def update_cytoscape_elements(graph_data, current_node_id):
    if not graph_data: return []
    dg = DialogueGraph(graph_data)
    return networkx_to_cytoscape(dg, current_node_id)

# Callback to update Cytoscape stylesheet for selection
@callback(
    Output('cytoscape-graph', 'stylesheet'),
    Input('current-node-store', 'data'),
)
def update_cytoscape_style(current_node_id):
    new_stylesheet = default_stylesheet[:]
    if current_node_id:
        new_stylesheet.append({
            'selector': f'node[id = "{current_node_id}"]',
            'style': {'border-width': '3px', 'border-color': '#337ab7', 'border-style': 'solid'}
        })
    return new_stylesheet


# Callback for navigation buttons
@callback(
    Output('current-node-store', 'data', allow_duplicate=True),
    Output('current-path-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('prev-sibling-btn', 'n_clicks'),
    Input('next-sibling-btn', 'n_clicks'),
    Input('go-up-btn', 'n_clicks'),
    State('graph-store', 'data'),
    State('current-node-store', 'data'),
    State('current-path-store', 'data'),
    prevent_initial_call=True
)
def handle_navigation(prev_clicks, next_clicks, up_clicks, graph_data, current_node_id, current_path):
    triggered_id = ctx.triggered_id
    if not triggered_id or not graph_data or not current_node_id:
        return no_update, no_update, "Navigation Error: Invalid state."

    dg = DialogueGraph(graph_data)
    node = dg.get_node_data(current_node_id)
    if not node: return no_update, no_update, f"Navigation Error: Node {current_node_id} not found."

    new_node_id = current_node_id
    new_path = current_path
    status_msg = "Navigated."
    roots = dg.get_root_nodes()

    parents = dg.get_parents(current_node_id)
    if not current_path: current_path = [current_node_id]

    first_parent_id = parents[0] if parents else None

    if triggered_id == 'prev-sibling-btn' or triggered_id == 'next-sibling-btn':
        if not first_parent_id: return no_update, no_update, "Cannot navigate siblings: No parent."
        parent_children = dg.get_children(first_parent_id)
        try:
            current_index = parent_children.index(current_node_id)
            direction = -1 if triggered_id == 'prev-sibling-btn' else 1
            new_index = current_index + direction
            if 0 <= new_index < len(parent_children):
                new_node_id = parent_children[new_index]
                if len(current_path) > 1:
                    path_to_parent = current_path[:-1]
                    new_path = path_to_parent + [new_node_id]
                else:
                    if roots: new_path = dg.get_path(roots[0], new_node_id) or [new_node_id]
                    else: new_path = [new_node_id]
                status_msg = f"Moved to sibling {new_node_id[:6]}..."
            else:
                status_msg = "No more siblings in this direction."
                return no_update, no_update, status_msg
        except ValueError:
             return no_update, no_update, "Error: Current node not found in parent's children."

    elif triggered_id == 'go-up-btn':
        if not first_parent_id: return no_update, no_update, "Cannot go up: No parent."
        new_node_id = first_parent_id
        if len(current_path) > 1:
            new_path = current_path[:-1]
        else:
             if roots: new_path = dg.get_path(roots[0], new_node_id) or [new_node_id]
             else: new_path = [new_node_id]
        status_msg = f"Moved up to parent {new_node_id[:6]}..."

    # Ensure path validity
    if not new_path or new_path[-1] != new_node_id:
         if roots:
             calculated_path = dg.get_path(roots[0], new_node_id)
             new_path = calculated_path if calculated_path else [new_node_id]
         else:
             new_path = [new_node_id]

    return new_node_id, new_path, status_msg

# Callback for choice buttons
@callback(
    Output('current-node-store', 'data', allow_duplicate=True),
    Output('current-path-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input({'type': 'choice-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
    State('current-path-store', 'data'),
    State('graph-store', 'data'),
    prevent_initial_call=True
)
def handle_choice(n_clicks, current_path, graph_data):
    clicked_button = ctx.triggered_id
    if not any(n_clicks) or not clicked_button:
        return no_update, no_update, no_update

    chosen_child_id = clicked_button['index']

    if not current_path:
         dg = DialogueGraph(graph_data)
         roots = dg.get_root_nodes()
         if roots:
             parents = dg.get_parents(chosen_child_id)
             if parents:
                 parent_path = dg.get_path(roots[0], parents[0])
                 if parent_path: current_path = parent_path
                 else:
                      status_msg = f"Chose option {chosen_child_id[:6]}... (Path context lost, resetting)"
                      return chosen_child_id, [chosen_child_id], status_msg
             else:
                 status_msg = f"Chose option {chosen_child_id[:6]}... (Path context lost, resetting)"
                 return chosen_child_id, [chosen_child_id], status_msg
         else:
             status_msg = f"Chose option {chosen_child_id[:6]}... (Path context lost, resetting)"
             return chosen_child_id, [chosen_child_id], status_msg

    new_path = current_path + [chosen_child_id]
    status_msg = f"Chose option leading to {chosen_child_id[:6]}..."

    return chosen_child_id, new_path, status_msg


# Callback for Add New Child button
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('add-child-btn', 'n_clicks'),
    State('graph-store', 'data'),
    State('current-node-store', 'data'),
    prevent_initial_call=True
)
def add_new_child(n_clicks, graph_data, current_node_id):
    if not n_clicks or not graph_data or not current_node_id:
        return no_update, "Error: Cannot add child."

    dg = DialogueGraph(graph_data)
    parent_node = dg.get_node_data(current_node_id)
    if not parent_node: return no_update, f"Error: Parent node {current_node_id} not found."
    if parent_node.node_type == NodeType.PLAYER_CHOICE:
        return no_update, "Cannot add standard child to PLAYER_CHOICE node."

    new_speaker = SpecificSpeaker("New NPC") if parent_node.speaker != player else player
    new_node = DialogueNode(node_type=NodeType.NPC_LINE, speaker=new_speaker)
    new_node.add_text_version(f"New node (child of {current_node_id[:6]})", source="placeholder")

    dg.add_node(new_node)
    success = dg.add_edge(current_node_id, new_node.node_id)

    if success:
        status_msg = f"Added new child node {new_node.node_id[:6]}."
        return dg.to_dict(), status_msg
    else:
        if new_node.node_id in dg.graph: dg.graph.remove_node(new_node.node_id)
        return no_update, "Error adding edge for new child."


# Callback for Link Existing Child button
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('link-child-btn', 'n_clicks'),
    State('graph-store', 'data'),
    State('current-node-store', 'data'),
    State('link-child-dropdown', 'value'),
    prevent_initial_call=True
)
def link_existing_child(n_clicks, graph_data, current_node_id, child_to_link_id):
    if not n_clicks or not graph_data or not current_node_id or not child_to_link_id:
        return no_update, "Error: Missing information to link child."

    dg = DialogueGraph(graph_data)
    parent_node = dg.get_node_data(current_node_id)
    if not parent_node: return no_update, f"Error: Parent node {current_node_id} not found."
    if parent_node.node_type == NodeType.PLAYER_CHOICE:
         return no_update, "Cannot link child to PLAYER_CHOICE node using this button."

    success = dg.add_edge(current_node_id, child_to_link_id)

    if success:
        status_msg = f"Linked existing node {child_to_link_id[:6]} as child."
        return dg.to_dict(), status_msg
    else:
        return no_update, f"Failed to link {child_to_link_id[:6]}. Check for cycles."

# --- Callback for Saving Text Edit ---
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('save-edit-btn', 'n_clicks'),
    State('graph-store', 'data'),
    State('current-node-store', 'data'),
    State('edit-node-textarea', 'value'), # Get text from textarea
    prevent_initial_call=True
)
def save_node_text_edit(n_clicks, graph_data, current_node_id, edited_text):
    if not n_clicks or not graph_data or not current_node_id:
        return no_update, "Error: Cannot save edit."
    if edited_text is None: # Check if text is None
         return no_update, "Error: Edited text is empty."

    dg = DialogueGraph(graph_data)
    node_data = dg.get_node_data(current_node_id)

    if not node_data:
        return no_update, f"Error: Node {current_node_id} not found."
    if node_data.node_type == NodeType.PLAYER_CHOICE:
         return no_update, "Cannot edit text of a PLAYER_CHOICE node."

    # Add new text version
    node_data.set_current_text(edited_text, source="manual_edit")

    # Update node data in the graph
    dg.update_node_data(node_data)

    status_msg = f"Saved text edit for node {current_node_id[:6]}."
    return dg.to_dict(), status_msg

# --- Callback for Removing Selected Child ---
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('remove-child-btn', 'n_clicks'),
    State('graph-store', 'data'),
    State('current-node-store', 'data'),
    State('remove-child-dropdown', 'value'), # Get selected child ID
    prevent_initial_call=True
)
def remove_selected_child(n_clicks, graph_data, current_node_id, child_to_remove_id):
    if not n_clicks or not graph_data or not current_node_id or not child_to_remove_id:
        return no_update, "Error: Missing information to remove child."

    dg = DialogueGraph(graph_data)

    # Use the DialogueGraph method to remove the edge
    dg.remove_edge(current_node_id, child_to_remove_id)

    status_msg = f"Removed child link: {current_node_id[:6]} -> {child_to_remove_id[:6]}."
    # Return the modified graph data
    return dg.to_dict(), status_msg


# Callback for clicking node in Cytoscape graph
@callback(
    Output('current-node-store', 'data', allow_duplicate=True),
    Output('current-path-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('cytoscape-graph', 'tapNodeData'),
    State('graph-store', 'data'),
    prevent_initial_call=True
)
def display_tap_node_data(node_data, graph_data):
    if not node_data or not graph_data:
        return no_update, no_update, no_update

    clicked_node_id = node_data['id']
    dg = DialogueGraph(graph_data)
    roots = dg.get_root_nodes()
    if not roots:
         status_msg = f"Selected node {clicked_node_id[:6]} (no root found)."
         return clicked_node_id, [clicked_node_id], status_msg

    new_path = dg.get_path(roots[0], clicked_node_id)

    if new_path:
        status_msg = f"Selected node {clicked_node_id[:6]} from graph."
        return clicked_node_id, new_path, status_msg
    else:
        status_msg = f"Selected node {clicked_node_id[:6]} (path not found from root)."
        return clicked_node_id, [clicked_node_id], status_msg


# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True)
