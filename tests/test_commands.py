# tests/test_commands.py

import pytest
import copy
from typing import List, Dict, Any, Optional, Union, Tuple, Type

# Imports from the package
from dialogue_editor.data_models import (
    DialogueGraph, DialogueNode, NodeType, Speaker, GenericSpeaker, SpecificSpeaker, TextVersion
)
from dialogue_editor.commands import (
    Command, AddNodeCommand, DeleteNodeCommand, UpdateNodeCommand, AddEdgeCommand, RemoveEdgeCommand
)
# Note: CommandManager is not needed here

# --- Fixtures (Can be moved to conftest.py later if shared) ---

@pytest.fixture
def empty_graph() -> DialogueGraph:
    """Provides an empty DialogueGraph."""
    return DialogueGraph()

@pytest.fixture
def simple_graph() -> DialogueGraph:
    """Provides a graph with a root node."""
    dg = DialogueGraph()
    root_node = DialogueNode(node_id="root")
    root_node.add_text_version("Root node text")
    dg.add_node(root_node)
    return dg

@pytest.fixture
def sample_node_data() -> DialogueNode:
    """Provides sample DialogueNode data."""
    node = DialogueNode(node_id="new_node_1", speaker=GenericSpeaker("Narrator"))
    node.add_text_version("Sample text for new node")
    return node

@pytest.fixture
def updated_node_data(sample_node_data: DialogueNode) -> DialogueNode:
     """Provides updated data for the sample node."""
     updated_node = copy.deepcopy(sample_node_data)
     updated_node.set_current_text("Updated sample text", source="test_update")
     updated_node.speaker = SpecificSpeaker("Guard")
     return updated_node

# ===========================================
# --- Unit Tests for Concrete Commands ---
# ===========================================

def test_add_node_command_execute_undo(empty_graph: DialogueGraph, sample_node_data: DialogueNode):
    """Test AddNodeCommand execute and undo directly."""
    graph = empty_graph
    cmd = AddNodeCommand(parent_id=None, new_node_data=sample_node_data)

    # Execute
    result_exec = cmd.execute(graph)
    assert result_exec['success'] is True
    assert result_exec['new_node_id'] == sample_node_data.node_id
    assert sample_node_data.node_id in graph.graph

    # Undo
    result_undo = cmd.undo(graph)
    assert result_undo['success'] is True
    assert sample_node_data.node_id not in graph.graph

def test_add_child_node_command_execute_undo(simple_graph: DialogueGraph, sample_node_data: DialogueNode):
    """Test AddNodeCommand with a parent."""
    graph = simple_graph
    parent_id = "root"
    cmd = AddNodeCommand(parent_id=parent_id, new_node_data=sample_node_data)

    # Execute
    result_exec = cmd.execute(graph)
    assert result_exec['success'] is True
    assert sample_node_data.node_id in graph.graph
    assert graph.graph.has_edge(parent_id, sample_node_data.node_id)

    # Undo
    result_undo = cmd.undo(graph)
    assert result_undo['success'] is True
    assert sample_node_data.node_id not in graph.graph
    assert not graph.graph.has_edge(parent_id, sample_node_data.node_id)


def test_delete_node_command_execute_undo(simple_graph: DialogueGraph):
    """Test DeleteNodeCommand execute and undo directly."""
    graph = simple_graph
    node_to_delete_id = "root"

    # Add child for edge testing
    child_node = DialogueNode(node_id="child1")
    graph.add_node(child_node)
    graph.add_edge(node_to_delete_id, "child1")
    original_node_data = graph.get_node_data(node_to_delete_id)

    cmd = DeleteNodeCommand(node_id=node_to_delete_id)

    # Execute
    result_exec = cmd.execute(graph)
    assert result_exec['success'] is True
    assert node_to_delete_id not in graph.graph
    assert "child1" in graph.graph # Child should remain
    assert not graph.graph.has_edge(node_to_delete_id, "child1") # Edge gone

    # Undo
    result_undo = cmd.undo(graph)
    assert result_undo['success'] is True
    assert node_to_delete_id in graph.graph
    # Check data restoration
    restored_node = graph.get_node_data(node_to_delete_id)
    assert restored_node is not None
    assert restored_node.current_text == original_node_data.current_text
    # Check edge restoration
    assert graph.graph.has_edge(node_to_delete_id, "child1")


def test_update_node_command_execute_undo(simple_graph: DialogueGraph, updated_node_data: DialogueNode):
    """Test UpdateNodeCommand execute and undo directly."""
    graph = simple_graph
    node_to_update_id = "root"
    original_node = graph.get_node_data(node_to_update_id)
    assert original_node is not None
    original_text = original_node.current_text
    original_speaker = original_node.speaker

    # Create update data with correct ID
    update_data = copy.deepcopy(updated_node_data)
    update_data.node_id = node_to_update_id

    cmd = UpdateNodeCommand(node_id=node_to_update_id, new_node_data=update_data)

    # Execute
    result_exec = cmd.execute(graph)
    assert result_exec['success'] is True
    updated_node_check = graph.get_node_data(node_to_update_id)
    assert updated_node_check is not None
    assert updated_node_check.current_text == update_data.current_text
    assert isinstance(updated_node_check.speaker, SpecificSpeaker)

    # Undo
    result_undo = cmd.undo(graph)
    assert result_undo['success'] is True
    undone_node_check = graph.get_node_data(node_to_update_id)
    assert undone_node_check is not None
    assert undone_node_check.current_text == original_text
    assert undone_node_check.speaker == original_speaker

def test_add_edge_command_execute_undo(simple_graph: DialogueGraph):
    """Test AddEdgeCommand execute and undo directly."""
    graph = simple_graph
    parent_id = "root"
    child_node = DialogueNode(node_id="child_edge")
    graph.add_node(child_node) # Add node first

    edge_data = {'label': 'test link'}
    cmd = AddEdgeCommand(parent_id=parent_id, child_id=child_node.node_id, edge_data=edge_data)

    # Execute
    result_exec = cmd.execute(graph)
    assert result_exec['success'] is True
    assert graph.graph.has_edge(parent_id, child_node.node_id)
    assert graph.graph.edges[parent_id, child_node.node_id]['label'] == 'test link'

    # Undo
    result_undo = cmd.undo(graph)
    assert result_undo['success'] is True
    assert not graph.graph.has_edge(parent_id, child_node.node_id)

def test_remove_edge_command_execute_undo(simple_graph: DialogueGraph):
    """Test RemoveEdgeCommand execute and undo directly."""
    graph = simple_graph
    parent_id = "root"
    child_node = DialogueNode(node_id="child_edge")
    graph.add_node(child_node)
    edge_data = {'label': 'to remove'}
    graph.add_edge(parent_id, child_node.node_id, **edge_data) # Add edge first

    cmd = RemoveEdgeCommand(parent_id=parent_id, child_id=child_node.node_id)

    # Execute
    result_exec = cmd.execute(graph)
    assert result_exec['success'] is True
    assert not graph.graph.has_edge(parent_id, child_node.node_id)

    # Undo
    result_undo = cmd.undo(graph)
    assert result_undo['success'] is True
    assert graph.graph.has_edge(parent_id, child_node.node_id)
    assert graph.graph.edges[parent_id, child_node.node_id]['label'] == 'to remove'
