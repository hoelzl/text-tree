# dialogue_editor/commands.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import copy

# Import necessary classes from data_models
from .data_models import DialogueGraph, DialogueNode

# --- Command Pattern Implementation ---

class Command(ABC):
    """Abstract base class for commands."""

    @abstractmethod
    def execute(self, graph: DialogueGraph) -> Dict[str, Any]:
        """Applies the command. Returns results for UI/Manager."""
        pass

    @abstractmethod
    def undo(self, graph: DialogueGraph) -> Dict[str, Any]:
        """Reverses the command. Returns results for UI/Manager."""
        pass

# --- Concrete Command Examples ---

@dataclass
class AddNodeCommand(Command):
    """Command to add a new node and an edge from a parent."""
    parent_id: Optional[str]
    new_node_data: DialogueNode

    def execute(self, graph: DialogueGraph) -> Dict[str, Any]:
        try:
            graph.add_node(self.new_node_data)
            edge_added = False
            if self.parent_id:
                edge_added = graph.add_edge(self.parent_id, self.new_node_data.node_id)
                if not edge_added:
                    graph.remove_node(self.new_node_data.node_id)
                    return {'success': False, 'status': f"Failed to add edge (cycle?)."}
            return {'success': True, 'status': f"Added node {self.new_node_data.node_id[:6]}.", 'new_node_id': self.new_node_data.node_id}
        except Exception as e:
            return {'success': False, 'status': f"Error adding node: {e}"}

    def undo(self, graph: DialogueGraph) -> Dict[str, Any]:
        try:
            graph.remove_node(self.new_node_data.node_id)
            return {'success': True, 'status': f"Undid add node {self.new_node_data.node_id[:6]}.", 'affected_node': self.parent_id}
        except Exception as e:
            return {'success': False, 'status': f"Error undoing add node: {e}"}


@dataclass
class DeleteNodeCommand(Command):
    """Command to delete a node."""
    node_id: str
    _deleted_node_data: Optional[Dict] = field(default=None, init=False)
    _incoming_edges: List[Tuple[str, Dict]] = field(default_factory=list, init=False)
    _outgoing_edges: List[Tuple[str, Dict]] = field(default_factory=list, init=False)

    def execute(self, graph: DialogueGraph) -> Dict[str, Any]:
        if not graph.graph or self.node_id not in graph.graph:
            return {'success': False, 'status': f"Node {self.node_id} not found."}
        try:
            self._deleted_node_data = copy.deepcopy(graph.graph.nodes[self.node_id])
            self._incoming_edges = [(u, copy.deepcopy(data)) for u, _, data in graph.graph.in_edges(self.node_id, data=True)]
            self._outgoing_edges = [(v, copy.deepcopy(data)) for _, v, data in graph.graph.out_edges(self.node_id, data=True)]
            parents = list(graph.graph.predecessors(self.node_id))
            next_selected_node = parents[0] if parents else None
            graph.remove_node(self.node_id)
            return {'success': True, 'status': f"Deleted node {self.node_id[:6]}.", 'next_selected_node': next_selected_node}
        except Exception as e:
            return {'success': False, 'status': f"Error deleting node: {e}"}

    def undo(self, graph: DialogueGraph) -> Dict[str, Any]:
        if self._deleted_node_data is None:
            return {'success': False, 'status': "Undo failed: No data."}
        try:
            graph.graph.add_node(self.node_id, **self._deleted_node_data)
            for source, data in self._incoming_edges:
                if source in graph.graph: graph.graph.add_edge(source, self.node_id, **data)
            for target, data in self._outgoing_edges:
                 if target in graph.graph: graph.graph.add_edge(self.node_id, target, **data)
            return {'success': True, 'status': f"Undid delete node {self.node_id[:6]}.", 'affected_node': self.node_id}
        except Exception as e:
            return {'success': False, 'status': f"Error undoing delete: {e}"}


@dataclass
class UpdateNodeCommand(Command):
    """Command to update data of an existing node."""
    node_id: str
    new_node_data: DialogueNode # Pass the whole updated object
    _previous_node_dict: Optional[Dict] = field(default=None, init=False)

    def execute(self, graph: DialogueGraph) -> Dict[str, Any]:
        original_node = graph.get_node_data(self.node_id)
        if not original_node:
            return {'success': False, 'status': f"Node {self.node_id} not found."}
        try:
            self._previous_node_dict = original_node.to_dict()
            graph.update_node_data(self.new_node_data)
            return {'success': True, 'status': f"Updated node {self.node_id[:6]}.", 'affected_node': self.node_id}
        except Exception as e:
            return {'success': False, 'status': f"Error updating node: {e}"}

    def undo(self, graph: DialogueGraph) -> Dict[str, Any]:
        if self._previous_node_dict is None:
             return {'success': False, 'status': "Undo failed: No previous data."}
        if self.node_id not in graph.graph:
            return {'success': False, 'status': f"Undo failed: Node {self.node_id} missing."}
        try:
            # Restore previous attributes
            for key, value in self._previous_node_dict.items():
                graph.graph.nodes[self.node_id][key] = value
            # Need to reconstruct the DialogueNode object from dict to update graph correctly
            # This assumes update_node_data handles the reconstruction implicitly, which it does not.
            # Let's reconstruct and call update_node_data
            restored_node_data = DialogueNode.from_dict(self.node_id, self._previous_node_dict)
            graph.update_node_data(restored_node_data)

            return {'success': True, 'status': f"Undid update for node {self.node_id[:6]}.", 'affected_node': self.node_id}
        except Exception as e:
            return {'success': False, 'status': f"Error undoing update: {e}"}


@dataclass
class AddEdgeCommand(Command):
    """Command to add an edge between existing nodes."""
    parent_id: str
    child_id: str
    edge_data: Dict = field(default_factory=dict)

    def execute(self, graph: DialogueGraph) -> Dict[str, Any]:
        try:
            success = graph.add_edge(self.parent_id, self.child_id, **self.edge_data)
            if success:
                return {'success': True, 'status': f"Added edge {self.parent_id[:6]} -> {self.child_id[:6]}."}
            else:
                # add_edge already prints cycle error
                return {'success': False, 'status': f"Failed to add edge {self.parent_id[:6]} -> {self.child_id[:6]}."}
        except Exception as e:
            return {'success': False, 'status': f"Error adding edge: {e}"}

    def undo(self, graph: DialogueGraph) -> Dict[str, Any]:
        try:
            graph.remove_edge(self.parent_id, self.child_id)
            return {'success': True, 'status': f"Undid add edge {self.parent_id[:6]} -> {self.child_id[:6]}."}
        except Exception as e:
            return {'success': False, 'status': f"Error undoing add edge: {e}"}


@dataclass
class RemoveEdgeCommand(Command):
    """Command to remove an edge."""
    parent_id: str
    child_id: str
    _removed_edge_data: Optional[Dict] = field(default=None, init=False)

    def execute(self, graph: DialogueGraph) -> Dict[str, Any]:
        if not graph.graph or not graph.graph.has_edge(self.parent_id, self.child_id):
            return {'success': False, 'status': f"Edge {self.parent_id[:6]} -> {self.child_id[:6]} not found."}
        try:
            self._removed_edge_data = copy.deepcopy(graph.graph.get_edge_data(self.parent_id, self.child_id))
            graph.remove_edge(self.parent_id, self.child_id)
            return {'success': True, 'status': f"Removed edge {self.parent_id[:6]} -> {self.child_id[:6]}."}
        except Exception as e:
            return {'success': False, 'status': f"Error removing edge: {e}"}

    def undo(self, graph: DialogueGraph) -> Dict[str, Any]:
        if self._removed_edge_data is None:
            return {'success': False, 'status': "Undo failed: No removed edge data."}
        try:
            # Add edge back with stored data
            graph.add_edge(self.parent_id, self.child_id, **self._removed_edge_data)
            return {'success': True, 'status': f"Undid remove edge {self.parent_id[:6]} -> {self.child_id[:6]}."}
        except Exception as e:
            return {'success': False, 'status': f"Error undoing remove edge: {e}"}

