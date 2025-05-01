# dialogue_editor/app.py

import dash
from dash import dcc, html, Input, Output, State, callback, ctx, no_update
import dash_cytoscape as cyto
import networkx as nx
import uuid
from typing import List, Dict, Any, Optional, Tuple

# --- Imports from local package modules ---
from .data_models import (
    DialogueGraph, DialogueNode, NodeType, Speaker, GenericSpeaker, SpecificSpeaker,
    TextVersion, get_speaker_details, speaker_from_dict
)
from .commands import (
    Command, AddNodeCommand, DeleteNodeCommand, UpdateNodeCommand,
    AddEdgeCommand, RemoveEdgeCommand
)
from .command_manager import CommandManager

# --- Initial Setup ---
player = GenericSpeaker(identifier="Player") # Define player globally

initial_dg = DialogueGraph() # Start with empty graph by default
# Or load from a file if implementing persistence later
# initial_dg = setup_initial_graph() # Can use helper for initial data

# Setup initial state if graph is empty
if not initial_dg.get_root_nodes():
     print("Graph is empty, setting up initial structure...")
     # Add a root node if graph is empty
     root_node = DialogueNode(node_id="root", speaker=SpecificSpeaker("Narrator"))
     root_node.add_text_version("Start of the dialogue.")
     initial_dg.add_node(root_node)

initial_roots = initial_dg.get_root_nodes()
initial_start_node_id = initial_roots[0] if initial_roots else None
initial_path = [initial_start_node_id] if initial_start_node_id else []

# Instantiate CommandManager
command_manager = CommandManager(initial_dg)

# --- UI Helper Functions --- (Moved here from global scope)

def build_chat_history_display(dg: DialogueGraph, path: List[str]) -> List[html.Div]:
    """Constructs Dash HTML components for chat history."""
    history_elements = []
    if not path: return [html.P("Dialogue history is empty.")]
    for node_id in path:
        node_data = dg.get_node_data(node_id)
        if node_data and node_data.node_type != NodeType.PLAYER_CHOICE:
            speaker_name = str(node_data.speaker) if node_data.speaker else "Narrator"
            text = node_data.current_text or "[No text]"
            style = {'padding': '8px', 'margin': '4px 0', 'borderRadius': '5px', 'maxWidth': '80%'}
            if isinstance(node_data.speaker, GenericSpeaker) and node_data.speaker.identifier == player.identifier:
                 style.update({'backgroundColor': '#e0f0ff', 'marginLeft': 'auto', 'textAlign': 'right'})
            else: style.update({'backgroundColor': '#f0f0f0', 'marginRight': 'auto'})
            history_elements.append(html.Div([html.Strong(f"{speaker_name}:"), html.P(text, style={'margin': '2px 0 0 0'})], style=style))
    return history_elements

def networkx_to_cytoscape(dg: DialogueGraph, current_node_id: Optional[str]) -> List[Dict[str, Any]]:
    """Converts NetworkX graph to Cytoscape elements format."""
    elements = []
    if not dg or not dg.graph: return []
    for node_id in dg.graph.nodes:
        node_data = dg.get_node_data(node_id)
        label, node_class = "[Error]", "npc-node" # Defaults
        if node_data:
            if node_data.node_type == NodeType.PLAYER_CHOICE: label, node_class = "[CHOICE]", 'choice-node'
            elif node_data.current_text:
                label = node_data.current_text[:20] + ('...' if len(node_data.current_text) > 20 else '')
                if isinstance(node_data.speaker, GenericSpeaker) and node_data.speaker.identifier == player.identifier: node_class = 'player-node'
            else: label = "[Empty]"
        elements.append({'data': {'id': node_id, 'label': label}, 'classes': node_class})
    for source, target, edge_data in dg.graph.edges(data=True):
        elements.append({'data': {'source': source, 'target': target, 'label': edge_data.get('choice_label', '')}})
    return elements

# --- Dash App Setup ---

app = dash.Dash(__name__, suppress_callback_exceptions=True, title="Dialogue DAG Editor")
server = app.server # Expose server for potential deployment

default_stylesheet = [
    {'selector': 'node', 'style': {'label': 'data(label)', 'background-color': '#ccc', 'shape': 'round-rectangle', 'width': 'label', 'height': 'label', 'padding': '10px', 'text-wrap': 'wrap', 'text-max-width': '80px', 'text-valign': 'center', 'text-halign': 'center'}},
    {'selector': 'edge', 'style': {'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'label': 'data(label)', 'font-size': '10px', 'text-rotation': 'autorotate'}},
    {'selector': '.choice-node', 'style': {'background-color': '#ffcc00', 'shape': 'diamond'}},
    {'selector': '.player-node', 'style': {'background-color': '#e0f0ff'}},
    {'selector': '.npc-node', 'style': {'background-color': '#f0f0f0'}},
]
default_zoom = 1
default_pan = {'x': 0, 'y': 0}
default_cy_layout = {'name': 'breadthfirst', 'directed': True, 'padding': 10, 'spacingFactor': 1.0}

# --- App Layout ---
app.layout = html.Div([
    # Stores
    dcc.Store(id='graph-store', data=command_manager.get_graph_data()), # Get initial data from manager
    dcc.Store(id='current-node-store', data=initial_start_node_id),
    dcc.Store(id='current-path-store', data=initial_path),
    dcc.Store(id='status-message-store', data="App loaded."),
    dcc.Store(id='editor-original-state-store', data={}),

    html.Div([ # Main container
        # Left Panel
        html.Div([
             # --- Added Undo/Redo Buttons ---
             html.Div([
                 html.Button('Undo', id='undo-btn', n_clicks=0, style={'marginRight': '5px'}),
                 html.Button('Redo', id='redo-btn', n_clicks=0),
             ], style={'marginBottom': '10px'}),
             # --- ---
            html.H3("Dialogue Flow"),
            html.Div(id='chat-history-display', style={'height': '300px', 'overflowY': 'scroll', 'border': '1px solid #ccc', 'marginBottom': '10px', 'padding': '5px'}),
            html.H3("Node Editor"),
            html.Div(id='node-editor-area', children=[
                html.Strong("Node ID: "), html.Span(id='editor-node-id', children="N/A"),
                html.Button('Delete This Node', id='delete-node-btn', n_clicks=0, style={'float': 'right', 'color': 'red', 'borderColor': 'red'}),
                html.Hr(),
                html.Div([
                    html.Div([
                        html.Label("Node Type:", style={'display': 'block', 'marginBottom': '2px'}),
                        dcc.Dropdown(id='editor-node-type', options=[{'label': nt.name, 'value': nt.value} for nt in NodeType], style={'width': '100%'}, clearable=False, disabled=True)
                    ], style={'flex': '1', 'marginRight': '10px'}),
                    html.Div([
                        html.Label("Speaker Type:", style={'display': 'block', 'marginBottom': '2px'}),
                        dcc.Dropdown(id='editor-speaker-type', options=[{'label': 'None', 'value': 'none'}, {'label': 'Generic', 'value': 'generic'}, {'label': 'Specific', 'value': 'specific'}], value='none', style={'width': '100%'}, clearable=False, disabled=True)
                    ], style={'flex': '1', 'marginRight': '10px'}),
                    html.Div([
                        html.Label("Speaker Name/ID:", style={'display': 'block', 'marginBottom': '2px'}),
                        dcc.Input(id='editor-speaker-name', type='text', list='speaker-names-list', style={'width': '100%'}, disabled=True),
                        html.Datalist(id='speaker-names-list', children=[])
                    ], style={'flex': '2'}),
                ], style={'display': 'flex', 'alignItems': 'flex-end', 'marginBottom': '10px'}),
                html.Label("Node Text:"),
                dcc.Textarea(id='editor-node-text', style={'width': '100%', 'height': 80, 'marginBottom': '5px'}, disabled=True),
                html.Button('Save Node Changes', id='save-node-changes-btn', n_clicks=0, disabled=True, style={'marginTop': '10px', 'marginBottom': '15px'}),
            ], style={'border': '1px solid #eee', 'padding': '10px', 'marginBottom': '15px'}),
            html.Div(id='choice-button-container', style={'marginBottom': '10px'}),
            html.H4("Navigation & Actions"),
            html.Button('<- Prev Sibling', id='prev-sibling-btn', n_clicks=0, style={'marginRight': '5px'}),
            html.Button('Next Sibling ->', id='next-sibling-btn', n_clicks=0, style={'marginRight': '5px'}),
            html.Button('Go Up', id='go-up-btn', n_clicks=0, style={'marginRight': '15px'}),
            html.Button('Add New Child (Placeholder)', id='add-child-btn', n_clicks=0, style={'marginRight': '5px'}),
            dcc.Dropdown(id='link-child-dropdown', placeholder="Select node to link as child...", style={'display': 'inline-block', 'width': '250px', 'marginRight': '5px', 'verticalAlign': 'middle'}),
            html.Button('Link Selected Child', id='link-child-btn', n_clicks=0, style={'verticalAlign': 'middle'}),
            html.H4("Manage Children", style={'marginTop': '15px'}),
            dcc.Dropdown(id='remove-child-dropdown', placeholder="Select child to remove...", style={'display': 'inline-block', 'width': '250px', 'marginRight': '5px', 'verticalAlign': 'middle'}),
            html.Button('Remove Selected Child Link', id='remove-child-btn', n_clicks=0, style={'verticalAlign': 'middle'}),
            html.Div(id='status-display', style={'marginTop': '15px', 'color': 'grey'}),
        ], style={'width': '48%', 'paddingRight': '2%', 'display': 'inline-block', 'verticalAlign': 'top'}),
        # Right Panel
        html.Div([
            html.Div([
                html.H3("Graph Visualization", style={'display': 'inline-block', 'marginRight': '10px'}),
                html.Button('Reset View', id='reset-view-btn', n_clicks=0, style={'display': 'inline-block', 'verticalAlign': 'middle'})
            ]),
            cyto.Cytoscape(
                id='cytoscape-graph',
                layout=default_cy_layout,
                style={'width': '100%', 'height': '650px', 'border': '1px solid black'},
                elements=networkx_to_cytoscape(command_manager.dialogue_graph, initial_start_node_id), # Use manager's graph
                stylesheet=default_stylesheet,
                zoom=default_zoom,
                pan=default_pan
            )
        ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'})
    ])
])

# --- Callbacks ---

# Helper function to process command results and determine state updates
def process_command_result(result: Dict[str, Any], current_node_id: Optional[str], current_path: List[str]) -> Dict[str, Any]:
    """Determines new UI state based on command results."""
    updates = {
        'graph_data': result.get('graph_data'),
        'status_msg': result.get('status', 'Error: Unknown result.')
    }
    if result.get('success', False):
        # Determine next selected node based on command hints
        if 'affected_node' in result:
            updates['current_node_id'] = result['affected_node']
        elif 'new_node_id' in result:
             updates['current_node_id'] = result['new_node_id']
        elif 'next_selected_node' in result:
             updates['current_node_id'] = result['next_selected_node']
        else:
            updates['current_node_id'] = current_node_id # Keep current selection if no hint

        # Attempt to update path if selection changed
        if updates.get('current_node_id') != current_node_id:
             new_selection = updates.get('current_node_id')
             if new_selection:
                 # Reconstruct graph to find path
                 temp_dg = DialogueGraph(result.get('graph_data'))
                 roots = temp_dg.get_root_nodes()
                 if roots:
                     new_path_calc = temp_dg.get_path(roots[0], new_selection)
                     updates['current_path'] = new_path_calc if new_path_calc else [new_selection]
                 else: # No roots, path is just the node
                      updates['current_path'] = [new_selection]
             else: # Selection became None (e.g., empty graph)
                  updates['current_path'] = []
        else:
             updates['current_path'] = current_path # Path didn't change
    else:
        # If command failed, don't change selection or path
        updates['current_node_id'] = current_node_id
        updates['current_path'] = current_path

    return updates


# Callback to update editor fields and store original state when node changes
@callback(
    Output('editor-node-id', 'children'),
    Output('editor-node-type', 'value'),
    Output('editor-node-type', 'disabled'),
    Output('editor-speaker-type', 'value'),
    Output('editor-speaker-type', 'disabled'),
    Output('editor-speaker-name', 'value'),
    Output('editor-speaker-name', 'disabled'),
    Output('editor-node-text', 'value'),
    Output('editor-node-text', 'disabled'),
    Output('editor-original-state-store', 'data'),
    Output('save-node-changes-btn', 'disabled'),
    Output('delete-node-btn', 'disabled'),
    Input('current-node-store', 'data'),
    State('graph-store', 'data'), # Use graph-store as state
    prevent_initial_call=True
)
def update_editor_area(current_node_id, graph_data):
    if not current_node_id or not graph_data:
        original_state = {}
        return "N/A", None, True, 'none', True, "", True, "", True, original_state, True, True

    # Use CommandManager's graph instance (or reconstruct if needed)
    # For read-only access like this, using the manager's instance is fine
    # If graph_data from store is guaranteed up-to-date, reconstruct:
    dg = DialogueGraph(graph_data)
    node_data = dg.get_node_data(current_node_id)

    if not node_data:
        original_state = {}
        return current_node_id[:8]+" (Error)", None, True, 'none', True, "", True, "", True, original_state, True, True

    is_choice_node = node_data.node_type == NodeType.PLAYER_CHOICE
    can_edit_text = not is_choice_node
    can_edit_speaker = not is_choice_node
    can_edit_type = True
    can_delete = True

    speaker_type, speaker_name = get_speaker_details(node_data.speaker)
    current_text = node_data.current_text if not is_choice_node else ""

    original_state = {
        'node_type': node_data.node_type.value,
        'speaker_type': speaker_type,
        'speaker_name': speaker_name,
        'text': current_text
    }

    return (
        current_node_id,
        node_data.node_type.value,
        not can_edit_type,
        speaker_type,
        not can_edit_speaker,
        speaker_name,
        speaker_type == 'none' or not can_edit_speaker,
        current_text,
        not can_edit_text,
        original_state,
        True, # Save disabled initially
        not can_delete
    )

# Callback to dynamically disable editor fields based on selected Node Type
@callback(
    Output('editor-speaker-type', 'disabled', allow_duplicate=True),
    Output('editor-speaker-name', 'disabled', allow_duplicate=True),
    Output('editor-node-text', 'disabled', allow_duplicate=True),
    # Also update text/speaker values when type changes to PLAYER_CHOICE
    Output('editor-speaker-type', 'value', allow_duplicate=True),
    Output('editor-speaker-name', 'value', allow_duplicate=True),
    Output('editor-node-text', 'value', allow_duplicate=True),
    Input('editor-node-type', 'value'),
    State('editor-speaker-type', 'value'),
    State('editor-speaker-name', 'value'),
    State('editor-node-text', 'value'),
    prevent_initial_call=True
)
def disable_editor_fields_on_type_change(selected_node_type_value, current_speaker_type, current_speaker_name, current_text):
    is_choice_node = selected_node_type_value == NodeType.PLAYER_CHOICE.value
    disable_speaker = is_choice_node
    disable_text = is_choice_node
    disable_speaker_name = is_choice_node or (current_speaker_type == 'none')

    # If becoming a choice node, clear/reset other fields
    new_speaker_type = 'none' if is_choice_node else current_speaker_type
    new_speaker_name = '' if is_choice_node else current_speaker_name
    new_text = '' if is_choice_node else current_text # Clear text for choice node in editor

    # Also disable speaker name if the new speaker type is none
    if new_speaker_type == 'none':
        disable_speaker_name = True

    return disable_speaker, disable_speaker_name, disable_text, new_speaker_type, new_speaker_name, new_text


# Callback to enable/disable the Save Node Changes button based on modifications
@callback(
    Output('save-node-changes-btn', 'disabled', allow_duplicate=True),
    Input('editor-node-type', 'value'),
    Input('editor-speaker-type', 'value'),
    Input('editor-speaker-name', 'value'),
    Input('editor-node-text', 'value'),
    State('editor-original-state-store', 'data'),
    State('current-node-store', 'data'),
    prevent_initial_call=True
)
def toggle_save_node_changes_button(new_type, new_speaker_type, new_speaker_name, new_text, original_state, current_node_id):
    if not current_node_id or not original_state: return True

    type_changed = new_type != original_state.get('node_type')
    speaker_type_changed = new_speaker_type != original_state.get('speaker_type')
    original_speaker_name = original_state.get('speaker_name', '')
    current_speaker_name = new_speaker_name if new_speaker_type != 'none' else ''
    speaker_name_changed = (new_speaker_type != 'none' and current_speaker_name != original_speaker_name)
    speaker_became_not_none = (original_state.get('speaker_type') == 'none' and new_speaker_type != 'none')
    speaker_became_none = (original_state.get('speaker_type') != 'none' and new_speaker_type == 'none')
    # Text change check only relevant if new type is not PLAYER_CHOICE
    text_changed = (new_type != NodeType.PLAYER_CHOICE.value and new_text != original_state.get('text'))

    enable_button = type_changed or speaker_type_changed or speaker_name_changed or speaker_became_not_none or speaker_became_none or text_changed
    return not enable_button


# Callback to handle saving node changes (Uses CommandManager)
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Output('save-node-changes-btn', 'disabled', allow_duplicate=True),
    Output('editor-original-state-store', 'data', allow_duplicate=True),
    # Potentially update current node/path if needed, but rely on main update for now
    Input('save-node-changes-btn', 'n_clicks'),
    State('current-node-store', 'data'),
    State('editor-node-type', 'value'),
    State('editor-speaker-type', 'value'),
    State('editor-speaker-name', 'value'),
    State('editor-node-text', 'value'),
    prevent_initial_call=True
)
def save_node_changes(n_clicks, current_node_id, node_type_val, speaker_type, speaker_name, node_text):
    if not n_clicks or not current_node_id:
        return no_update, "Save Error: No node selected.", True, no_update

    # Reconstruct the updated DialogueNode object from editor values
    try:
        new_node_type = NodeType(node_type_val)
    except ValueError:
        return no_update, f"Save Error: Invalid node type '{node_type_val}'.", False, no_update

    new_speaker = None
    if new_node_type != NodeType.PLAYER_CHOICE: # Only set speaker if not choice node
        if speaker_type == 'generic':
            new_speaker = GenericSpeaker(identifier=speaker_name.strip() or "Default Generic")
        elif speaker_type == 'specific':
            new_speaker = SpecificSpeaker(name=speaker_name.strip() or "Default Specific")

    # Get existing node data to preserve history etc.
    existing_node = command_manager.dialogue_graph.get_node_data(current_node_id)
    if not existing_node:
         return no_update, f"Save Error: Cannot find node {current_node_id} to update.", True, no_update

    # Create the updated node object
    updated_node_data = DialogueNode(
        node_id=current_node_id,
        node_type=new_node_type,
        speaker=new_speaker,
        # Preserve existing history, add new version if text changed
        text_history=existing_node.text_history,
        generation_metadata=existing_node.generation_metadata,
        custom_metadata=existing_node.custom_metadata
    )

    # Add new text version if text changed and it's not a choice node
    if new_node_type != NodeType.PLAYER_CHOICE and node_text != existing_node.current_text:
        updated_node_data.add_text_version(node_text, source="manual_edit")
    elif new_node_type == NodeType.PLAYER_CHOICE:
        # Ensure text history is empty for choice nodes
        updated_node_data.text_history = []


    # Create and execute the command
    command = UpdateNodeCommand(node_id=current_node_id, new_node_data=updated_node_data)
    result = command_manager.execute_command(command)

    # Update original state store if successful
    new_original_state = {}
    if result.get('success'):
        saved_speaker_type, saved_speaker_name = get_speaker_details(updated_node_data.speaker)
        new_original_state = {
            'node_type': updated_node_data.node_type.value,
            'speaker_type': saved_speaker_type,
            'speaker_name': saved_speaker_name,
            'text': updated_node_data.current_text or ""
        }
        # Disable save button after successful save
        disable_save = True
    else:
        # Keep save button enabled if save failed
        disable_save = False
        new_original_state = State('editor-original-state-store', 'data') # Keep old original state


    return result.get('graph_data'), result.get('status'), disable_save, new_original_state


# Combined callback to update UI elements based on current state (Main Update)
@callback(
    Output('chat-history-display', 'children'),
    Output('choice-button-container', 'children'),
    Output('prev-sibling-btn', 'disabled'),
    Output('next-sibling-btn', 'disabled'),
    Output('go-up-btn', 'disabled'),
    Output('add-child-btn', 'disabled'),
    Output('link-child-dropdown', 'options'),
    Output('link-child-dropdown', 'value'),
    Output('link-child-btn', 'disabled'),
    Output('status-display', 'children'),
    Output('remove-child-dropdown', 'options'),
    Output('remove-child-dropdown', 'value'),
    Output('remove-child-btn', 'disabled'),
    Output('speaker-names-list', 'children'),
    # --- Add Undo/Redo button state outputs ---
    Output('undo-btn', 'disabled'),
    Output('redo-btn', 'disabled'),
    # Inputs triggering the update
    Input('current-node-store', 'data'),
    Input('current-path-store', 'data'),
    Input('graph-store', 'data'),
    State('status-message-store', 'data')
)
def update_main_display_ui(current_node_id, current_path, graph_data, status_msg):
    # Use the global command_manager instance to check undo/redo state
    can_undo = command_manager.can_undo()
    can_redo = command_manager.can_redo()

    default_outputs = {
        'chat-history-display': [html.P("No node selected or history unavailable.")],
        'choice-button-container': [],
        'prev-sibling-btn': True, 'next-sibling-btn': True, 'go-up-btn': True,
        'add-child-btn': True,
        'link-child-dropdown-opts': [], 'link-child-dropdown-val': None, 'link-child-btn': True,
        'status-display': "Error: Invalid state.",
        'remove-child-opts': [], 'remove-child-val': None, 'remove-child-btn': True,
        'speaker-names-list': []
    }
    def make_output(updates):
        return (
            updates.get('chat-history-display', default_outputs['chat-history-display']),
            updates.get('choice-button-container', default_outputs['choice-button-container']),
            updates.get('prev-sibling-btn', default_outputs['prev-sibling-btn']),
            updates.get('next-sibling-btn', default_outputs['next-sibling-btn']),
            updates.get('go-up-btn', default_outputs['go-up-btn']),
            updates.get('add-child-btn', default_outputs['add-child-btn']),
            updates.get('link-child-dropdown-opts', default_outputs['link-child-dropdown-opts']),
            updates.get('link-child-dropdown-val', default_outputs['link-child-dropdown-val']),
            updates.get('link-child-btn', default_outputs['link-child-btn']),
            updates.get('status-display', default_outputs['status-display']),
            updates.get('remove-child-opts', default_outputs['remove-child-opts']),
            updates.get('remove-child-val', default_outputs['remove-child-val']),
            updates.get('remove-child-btn', default_outputs['remove-child-btn']),
            updates.get('speaker-names-list', default_outputs['speaker-names-list']),
            not can_undo, # undo-btn disabled state
            not can_redo  # redo-btn disabled state
        )

    if not current_node_id or not graph_data:
        dg_check = DialogueGraph(graph_data)
        roots_check = dg_check.get_root_nodes()
        if not roots_check:
             return make_output({'status-display': "Error: Invalid state or empty graph."})

    dg = DialogueGraph(graph_data) # Reconstruct graph from store data for display logic
    current_node = dg.get_node_data(current_node_id)

    speaker_names = dg.get_unique_speaker_names()
    speaker_datalist_options = [html.Option(value=name) for name in speaker_names]
    outputs = {'speaker-names-list': speaker_datalist_options}

    if not current_node:
         roots = dg.get_root_nodes()
         if roots:
             outputs['status-display'] = f"Error: Node {current_node_id[:6]} not found. Try selecting a node."
             return make_output(outputs)
         else:
             outputs['status-display'] = "Error: Graph is empty or invalid."
             return make_output(outputs)


    outputs['chat-history-display'] = build_chat_history_display(dg, current_path)

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

    outputs['add-child-btn'] = False # Enable Add Child button if a node is selected
    outputs['link-child-btn'] = current_node.node_type == NodeType.PLAYER_CHOICE

    all_nodes = dg.get_all_node_ids()
    link_options = []
    for nid in all_nodes:
        if nid == current_node_id: continue
        node_to_link = dg.get_node_data(nid)
        if not node_to_link: continue
        if not dg.is_reachable(nid, current_node_id):
            if node_to_link.node_type == NodeType.PLAYER_CHOICE: label_text = "[PLAYER CHOICE]"
            else: label_text = node_to_link.current_text[:15] if node_to_link.current_text else "[Empty]"
            label = f"{nid[:6]}... ({label_text}...)"
            link_options.append({'label': label, 'value': nid})
    outputs['link-child-dropdown-opts'] = link_options
    outputs['link-child-dropdown-val'] = None

    current_children = dg.get_children(current_node_id)
    outputs['remove-child-opts'] = [{'label': f"{cid[:6]}... ({dg.get_node_data(cid).current_text[:15] if dg.get_node_data(cid) and dg.get_node_data(cid).current_text else 'Choice/Empty'}...)", 'value': cid}
                                     for cid in current_children]
    outputs['remove-child-val'] = None
    outputs['remove-child-btn'] = not bool(current_children)

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

    dg = DialogueGraph(graph_data) # Reconstruct for read operations
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


# Callback for Add New Child button (Uses CommandManager)
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Output('current-node-store', 'data', allow_duplicate=True),
    Output('current-path-store', 'data', allow_duplicate=True),
    Input('add-child-btn', 'n_clicks'),
    State('current-node-store', 'data'),
    State('current-path-store', 'data'),
    prevent_initial_call=True
)
def add_new_child(n_clicks, current_node_id, current_path):
    if not n_clicks or not current_node_id:
        return no_update, "Error: Cannot add child.", no_update, no_update

    parent_node = command_manager.dialogue_graph.get_node_data(current_node_id)
    if not parent_node:
        return no_update, f"Error: Parent node {current_node_id} not found.", no_update, no_update

    # Determine defaults based on parent
    if parent_node.node_type == NodeType.PLAYER_CHOICE:
        new_speaker = player
        new_node_type = NodeType.NPC_LINE
    else:
        new_speaker = SpecificSpeaker("New NPC") if parent_node.speaker != player else player
        new_node_type = NodeType.NPC_LINE

    new_node_data = DialogueNode(node_type=new_node_type, speaker=new_speaker)
    new_node_data.add_text_version(f"New node (child of {current_node_id[:6]})", source="placeholder")

    command = AddNodeCommand(parent_id=current_node_id, new_node_data=new_node_data)
    result = command_manager.execute_command(command)

    # Process result to update UI state
    processed_state = process_command_result(result, current_node_id, current_path)

    return (
        processed_state['graph_data'],
        processed_state['status_msg'],
        processed_state['current_node_id'],
        processed_state['current_path']
    )


# Callback for Link Existing Child button (Uses CommandManager)
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('link-child-btn', 'n_clicks'),
    State('current-node-store', 'data'),
    State('link-child-dropdown', 'value'),
    prevent_initial_call=True
)
def link_existing_child(n_clicks, current_node_id, child_to_link_id):
    if not n_clicks or not current_node_id or not child_to_link_id:
        return no_update, "Error: Missing information to link child."

    # Create and execute command
    command = AddEdgeCommand(parent_id=current_node_id, child_id=child_to_link_id)
    result = command_manager.execute_command(command)

    return result.get('graph_data'), result.get('status')


# Callback for Removing Selected Child link (Uses CommandManager)
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('remove-child-btn', 'n_clicks'),
    State('current-node-store', 'data'),
    State('remove-child-dropdown', 'value'),
    prevent_initial_call=True
)
def remove_selected_child_link(n_clicks, current_node_id, child_to_remove_id):
    if not n_clicks or not current_node_id or not child_to_remove_id:
        return no_update, "Error: Missing information to remove child link."

    # Create and execute command
    command = RemoveEdgeCommand(parent_id=current_node_id, child_id=child_to_remove_id)
    result = command_manager.execute_command(command)

    return result.get('graph_data'), result.get('status')

# Callback for Deleting Selected Node (Uses CommandManager)
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('current-node-store', 'data', allow_duplicate=True),
    Output('current-path-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('delete-node-btn', 'n_clicks'),
    State('current-node-store', 'data'),
    State('current-path-store', 'data'), # Pass current path for context
    prevent_initial_call=True
)
def delete_selected_node(n_clicks, node_to_delete_id, current_path):
    if not n_clicks or not node_to_delete_id:
        return no_update, no_update, no_update, "Error: Cannot delete node."

    # Create and execute command
    command = DeleteNodeCommand(node_id=node_to_delete_id)
    result = command_manager.execute_command(command)

    # Process result to update UI state
    processed_state = process_command_result(result, node_to_delete_id, current_path)

    return (
        processed_state['graph_data'],
        processed_state['current_node_id'],
        processed_state['current_path'],
        processed_state['status_msg']
    )


# Callback for clicking node in Cytoscape graph
@callback(
    Output('current-node-store', 'data', allow_duplicate=True),
    Output('current-path-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('cytoscape-graph', 'tapNodeData'),
    State('graph-store', 'data'), # Use graph-store for read-only access
    prevent_initial_call=True
)
def display_tap_node_data(node_data, graph_data):
    if not node_data or not graph_data:
        return no_update, no_update, no_update

    clicked_node_id = node_data['id']
    # Reconstruct graph temporarily for path finding
    dg = DialogueGraph(graph_data)
    roots = dg.get_root_nodes()
    new_path = []
    status_msg = f"Selected node {clicked_node_id[:6]}."

    if roots:
        path_calc = dg.get_path(roots[0], clicked_node_id)
        if path_calc:
            new_path = path_calc
        else:
            new_path = [clicked_node_id] # Path not found, just select node
            status_msg += " (Path from root not found)"
    else: # No roots
        new_path = [clicked_node_id]
        status_msg += " (No root node found)"

    return clicked_node_id, new_path, status_msg

# Callback for Reset View Button
@callback(
    Output('cytoscape-graph', 'zoom', allow_duplicate=True),
    Output('cytoscape-graph', 'pan', allow_duplicate=True),
    Output('cytoscape-graph', 'layout', allow_duplicate=True),
    Input('reset-view-btn', 'n_clicks'),
    prevent_initial_call=True
)
def reset_graph_view(n_clicks):
    if n_clicks:
        # Return default zoom, pan, and trigger layout reset
        return default_zoom, default_pan, default_cy_layout
    return no_update, no_update, no_update

# --- Undo/Redo Callbacks ---
@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('current-node-store', 'data', allow_duplicate=True),
    Output('current-path-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('undo-btn', 'n_clicks'),
    State('current-node-store', 'data'),
    State('current-path-store', 'data'),
    prevent_initial_call=True
)
def handle_undo(n_clicks, current_node_id, current_path):
    if n_clicks:
        result = command_manager.undo()
        processed_state = process_command_result(result, current_node_id, current_path)
        return (
            processed_state['graph_data'],
            processed_state['current_node_id'],
            processed_state['current_path'],
            processed_state['status_msg']
        )
    return no_update, no_update, no_update, no_update

@callback(
    Output('graph-store', 'data', allow_duplicate=True),
    Output('current-node-store', 'data', allow_duplicate=True),
    Output('current-path-store', 'data', allow_duplicate=True),
    Output('status-message-store', 'data', allow_duplicate=True),
    Input('redo-btn', 'n_clicks'),
    State('current-node-store', 'data'),
    State('current-path-store', 'data'),
    prevent_initial_call=True
)
def handle_redo(n_clicks, current_node_id, current_path):
    if n_clicks:
        result = command_manager.redo()
        processed_state = process_command_result(result, current_node_id, current_path)
        return (
            processed_state['graph_data'],
            processed_state['current_node_id'],
            processed_state['current_path'],
            processed_state['status_msg']
        )
    return no_update, no_update, no_update, no_update


# --- Run the App ---
# Note: The CommandManager instance is global in this simple setup.
# For more complex apps, consider passing it via Flask context or other DI methods.
if __name__ == '__main__':
    # Ensure initial graph state is loaded into the manager if needed
    # command_manager = CommandManager(DialogueGraph(initial_graph_data_if_loaded_from_file))
    app.run(debug=True)

