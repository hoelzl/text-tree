# dialogue_editor/data_models.py

import uuid
import enum
import networkx as nx
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime, timezone, UTC
import copy

# --- Speaker Hierarchy ---
@dataclass
class Speaker: pass

@dataclass
class SpecificSpeaker(Speaker):
    name: str
    def __str__(self): return self.name
    def to_dict(self): return {'type': 'specific', 'name': self.name}
    @classmethod
    def from_dict(cls, data):
        if data and data.get('type') == 'specific': return cls(name=data.get('name', 'Unknown Specific'))
        return None

@dataclass
class GenericSpeaker(Speaker):
    identifier: str
    def __str__(self): return self.identifier
    def to_dict(self): return {'type': 'generic', 'identifier': self.identifier}
    @classmethod
    def from_dict(cls, data):
        if data and data.get('type') == 'generic': return cls(identifier=data.get('identifier', 'Unknown Generic'))
        return None

def speaker_from_dict(data):
    if isinstance(data, dict):
        if data.get('type') == 'specific': return SpecificSpeaker.from_dict(data)
        elif data.get('type') == 'generic': return GenericSpeaker.from_dict(data)
    elif isinstance(data, Speaker): return data
    return None

def get_speaker_details(speaker: Optional[Speaker]) -> Tuple[str, str]:
    if isinstance(speaker, SpecificSpeaker): return 'specific', speaker.name
    elif isinstance(speaker, GenericSpeaker): return 'generic', speaker.identifier
    else: return 'none', ''

# --- Node Type Enum ---
class NodeType(enum.Enum):
    NPC_LINE = "NPC_LINE"
    PLAYER_CHOICE = "PLAYER_CHOICE"

# --- Text Versioning ---
@dataclass
class TextVersion:
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "manual"
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self):
        return {'text': self.text, 'timestamp': self.timestamp.isoformat(), 'source': self.source, 'metadata': self.metadata}

    @classmethod
    def from_dict(cls, data):
        ts_str = data.get('timestamp')
        timestamp = datetime.fromisoformat(ts_str) if ts_str else datetime.now(UTC)
        return cls(text=data.get('text', ''), timestamp=timestamp, source=data.get('source', 'unknown'), metadata=data.get('metadata'))

# --- Dialogue Node ---
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
        return {"node_type": self.node_type.value, "speaker": self.speaker.to_dict() if self.speaker else None, "text_history": [th.to_dict() for th in self.text_history], "generation_metadata": self.generation_metadata, "custom_metadata": self.custom_metadata}

    @classmethod
    def from_dict(cls, node_id: str, data: Dict[str, Any]) -> 'DialogueNode':
        try:
             node_type_val = data.get("node_type")
             try: node_type = NodeType(node_type_val) if node_type_val else NodeType.NPC_LINE
             except ValueError: node_type = NodeType.NPC_LINE
             speaker_data = data.get("speaker")
             speaker = speaker_from_dict(speaker_data)
             history_data = data.get("text_history", [])
             if not isinstance(history_data, list): history_data = []
             text_history = [TextVersion.from_dict(th_data) for th_data in history_data]
             if node_type == NodeType.PLAYER_CHOICE: speaker = None
             return cls(node_id=node_id, node_type=node_type, speaker=speaker, text_history=text_history, generation_metadata=data.get("generation_metadata", {}), custom_metadata=data.get("custom_metadata", {}))
        except Exception as e:
             print(f"Error reconstructing DialogueNode {node_id} from dict: {e}")
             return cls(node_id=node_id, text_history=[TextVersion(text=f"Error loading node data: {e}", source="error")])

# --- Dialogue Graph ---
class DialogueGraph:
    def __init__(self, graph_data=None):
        if graph_data:
            if isinstance(graph_data, dict) and 'nodes' in graph_data and 'links' in graph_data:
                 try: self.graph = nx.node_link_graph(graph_data, directed=True, multigraph=False, edges="links")
                 except Exception as e: self.graph = nx.DiGraph()
            else: self.graph = nx.DiGraph()
        else: self.graph = nx.DiGraph()

    def to_dict(self):
        return nx.node_link_data(self.graph, edges="links") if self.graph else {'nodes': [], 'links': []}

    def add_node(self, node_data: DialogueNode):
        if not self.graph: self.graph = nx.DiGraph()
        self.graph.add_node(node_data.node_id, **node_data.to_dict())

    def get_node_data(self, node_id: str) -> Optional[DialogueNode]:
        if not self.graph or node_id not in self.graph: return None
        try:
            node_attrs = self.graph.nodes.get(node_id)
            if node_attrs is None: return None
            return DialogueNode.from_dict(node_id, node_attrs)
        except Exception: return None

    def update_node_data(self, node_data: DialogueNode):
        if not self.graph or node_data.node_id not in self.graph: raise ValueError("Node does not exist")
        node_attrs = node_data.to_dict()
        for key, value in node_attrs.items(): self.graph.nodes[node_data.node_id][key] = value

    def remove_node(self, node_id: str):
         if not self.graph: return
         if node_id in self.graph: self.graph.remove_node(node_id)

    def add_edge(self, parent_id: str, child_id: str, **kwargs) -> bool:
        if not self.graph: self.graph = nx.DiGraph()
        if parent_id not in self.graph or child_id not in self.graph: return False
        if self.is_reachable(child_id, parent_id): return False
        self.graph.add_edge(parent_id, child_id, **kwargs)
        return True

    def remove_edge(self, parent_id: str, child_id: str):
         if not self.graph: return
         if self.graph.has_edge(parent_id, child_id): self.graph.remove_edge(parent_id, child_id)

    def get_children(self, node_id: str) -> List[str]:
        if not self.graph or node_id not in self.graph: return []
        return list(self.graph.successors(node_id))

    def get_parents(self, node_id: str) -> List[str]:
        if not self.graph or node_id not in self.graph: return []
        return list(self.graph.predecessors(node_id))

    def get_siblings(self, node_id: str) -> List[str]:
        siblings = set()
        parents = self.get_parents(node_id)
        if not parents: return []
        first_parent = parents[0]
        for child in self.get_children(first_parent):
            if child != node_id: siblings.add(child)
        return list(siblings)

    def get_path(self, start_id: str, end_id: str) -> Optional[List[str]]:
        if not self.graph or start_id not in self.graph or end_id not in self.graph: return None
        try: return nx.shortest_path(self.graph, source=start_id, target=end_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            try:
                 paths = list(nx.all_simple_paths(self.graph, source=start_id, target=end_id))
                 return paths[0] if paths else None
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                 if start_id == end_id: return [start_id]
                 return None

    def is_reachable(self, start_id: str, end_id: str) -> bool:
        if not self.graph or start_id not in self.graph or end_id not in self.graph: return False
        if start_id == end_id: return True
        try: return nx.has_path(self.graph, start_id, end_id)
        except nx.NodeNotFound: return False

    def get_all_node_ids(self) -> List[str]:
        return list(self.graph.nodes) if self.graph else []

    def get_root_nodes(self) -> List[str]:
        return [node for node, degree in self.graph.in_degree() if degree == 0] if self.graph else []

    def get_unique_speaker_names(self) -> List[str]:
        names = set()
        if not self.graph: return []
        for node_id in self.graph.nodes:
            node_data = self.get_node_data(node_id)
            if node_data and node_data.speaker:
                 speaker_type, speaker_name = get_speaker_details(node_data.speaker)
                 if speaker_name: names.add(speaker_name)
        return sorted(list(names))
