import pytest
import copy
from typing import List, Dict, Any, Optional, Union, Tuple, Type

# *** Updated Imports ***
from dialogue_editor.data_models import (
    DialogueGraph, DialogueNode, NodeType, Speaker, GenericSpeaker, SpecificSpeaker, TextVersion
)
from dialogue_editor.commands import (
    Command, AddNodeCommand, DeleteNodeCommand, UpdateNodeCommand, AddEdgeCommand, RemoveEdgeCommand
)
from dialogue_editor.command_manager import CommandManager
# *** End Updated Imports ***

# --- Test Fixtures ---

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
def command_manager(empty_graph: DialogueGraph) -> CommandManager:
    """Provides a CommandManager with an empty graph."""
    return CommandManager(empty_graph)

@pytest.fixture
def command_manager_with_simple_graph(simple_graph: DialogueGraph) -> CommandManager:
    """Provides a CommandManager with a simple graph."""
    return CommandManager(simple_graph)

# --- Test Data ---

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


# --- Command Tests ---

def test_add_root_node_command(command_manager: CommandManager, sample_node_data: DialogueNode):
    """Test adding a root node."""
    cmd = AddNodeCommand(parent_id=None, new_node_data=sample_node_data)
    result = command_manager.execute_command(cmd)

    assert result['success'] is True
    assert result['new_node_id'] == sample_node_data.node_id
    assert sample_node_data.node_id in command_manager.dialogue_graph.graph
    assert command_manager.can_undo() is True
    assert command_manager.can_redo() is False

    # Test Undo
    undo_result = command_manager.undo()
    assert undo_result['success'] is True
    assert sample_node_data.node_id not in command_manager.dialogue_graph.graph
    assert command_manager.can_undo() is False
    assert command_manager.can_redo() is True

    # Test Redo
    redo_result = command_manager.redo()
    assert redo_result['success'] is True
    assert sample_node_data.node_id in command_manager.dialogue_graph.graph
    assert command_manager.can_undo() is True
    assert command_manager.can_redo() is False

def test_add_child_node_command(command_manager_with_simple_graph: CommandManager, sample_node_data: DialogueNode):
    """Test adding a child node to an existing node."""
    manager = command_manager_with_simple_graph
    parent_id = "root"
    cmd = AddNodeCommand(parent_id=parent_id, new_node_data=sample_node_data)
    result = manager.execute_command(cmd)

    assert result['success'] is True
    assert result['new_node_id'] == sample_node_data.node_id
    assert sample_node_data.node_id in manager.dialogue_graph.graph
    assert manager.dialogue_graph.graph.has_edge(parent_id, sample_node_data.node_id)
    assert manager.can_undo() is True

    # Test Undo
    undo_result = manager.undo()
    assert undo_result['success'] is True
    assert sample_node_data.node_id not in manager.dialogue_graph.graph
    assert not manager.dialogue_graph.graph.has_edge(parent_id, sample_node_data.node_id)
    assert manager.can_redo() is True

    # Test Redo
    redo_result = manager.redo()
    assert redo_result['success'] is True
    assert sample_node_data.node_id in manager.dialogue_graph.graph
    assert manager.dialogue_graph.graph.has_edge(parent_id, sample_node_data.node_id)
    assert manager.can_undo() is True

def test_delete_node_command(command_manager_with_simple_graph: CommandManager):
    """Test deleting an existing node."""
    manager = command_manager_with_simple_graph
    node_to_delete_id = "root"

    child_node = DialogueNode(node_id="child1")
    add_child_cmd = AddNodeCommand(parent_id=node_to_delete_id, new_node_data=child_node)
    manager.execute_command(add_child_cmd)
    assert manager.dialogue_graph.graph.has_edge(node_to_delete_id, "child1")

    # Execute Delete
    cmd = DeleteNodeCommand(node_id=node_to_delete_id)
    result = manager.execute_command(cmd)

    assert result['success'] is True
    assert node_to_delete_id not in manager.dialogue_graph.graph
    assert "child1" in manager.dialogue_graph.graph
    assert not manager.dialogue_graph.graph.has_edge(node_to_delete_id, "child1")
    assert manager.can_undo() is True

    # Test Undo Delete
    undo_result = manager.undo()
    assert undo_result['success'] is True
    assert node_to_delete_id in manager.dialogue_graph.graph
    restored_node = manager.dialogue_graph.get_node_data(node_to_delete_id)
    assert restored_node is not None
    assert restored_node.current_text == "Root node text"
    assert manager.dialogue_graph.graph.has_edge(node_to_delete_id, "child1")
    assert manager.can_redo() is True

    # Test Redo Delete
    redo_result = manager.redo()
    assert redo_result['success'] is True
    assert node_to_delete_id not in manager.dialogue_graph.graph
    assert manager.can_undo() is True

def test_update_node_command(command_manager_with_simple_graph: CommandManager, updated_node_data: DialogueNode):
    """Test updating data of an existing node."""
    manager = command_manager_with_simple_graph
    node_to_update_id = "root"

    original_node = manager.dialogue_graph.get_node_data(node_to_update_id)
    assert original_node is not None
    original_text = original_node.current_text

    update_data = copy.deepcopy(updated_node_data)
    update_data.node_id = node_to_update_id

    # Execute Update
    cmd = UpdateNodeCommand(node_id=node_to_update_id, new_node_data=update_data)
    result = manager.execute_command(cmd)

    assert result['success'] is True
    updated_node_check = manager.dialogue_graph.get_node_data(node_to_update_id)
    assert updated_node_check is not None
    assert updated_node_check.current_text == update_data.current_text
    assert isinstance(updated_node_check.speaker, SpecificSpeaker)
    assert str(updated_node_check.speaker) == "Guard"
    assert manager.can_undo() is True

    # Test Undo Update
    undo_result = manager.undo()
    assert undo_result['success'] is True
    undone_node_check = manager.dialogue_graph.get_node_data(node_to_update_id)
    assert undone_node_check is not None
    assert undone_node_check.current_text == original_text
    assert undone_node_check.speaker is None
    assert manager.can_redo() is True

    # Test Redo Update
    redo_result = manager.redo()
    assert redo_result['success'] is True
    redone_node_check = manager.dialogue_graph.get_node_data(node_to_update_id)
    assert redone_node_check is not None
    assert redone_node_check.current_text == update_data.current_text
    assert isinstance(redone_node_check.speaker, SpecificSpeaker)
    assert manager.can_undo() is True

def test_command_manager_stacks(command_manager: CommandManager, sample_node_data: DialogueNode):
    """Test undo/redo stack management."""
    cmd1 = AddNodeCommand(parent_id=None, new_node_data=sample_node_data)
    node2_data = DialogueNode(node_id="node2")
    cmd2 = AddNodeCommand(parent_id=sample_node_data.node_id, new_node_data=node2_data)

    # Execute two commands
    res1 = command_manager.execute_command(cmd1)
    assert res1['success']
    res2 = command_manager.execute_command(cmd2)
    assert res2['success']
    assert len(command_manager.undo_stack) == 2
    assert len(command_manager.redo_stack) == 0

    # Undo one
    res_undo1 = command_manager.undo()
    assert res_undo1['success']
    assert len(command_manager.undo_stack) == 1
    assert len(command_manager.redo_stack) == 1
    assert command_manager.redo_stack[0] == cmd2 # Last undone command is cmd2

    # Execute a new command (should clear redo stack)
    node3_data = DialogueNode(node_id="node3")
    cmd3 = AddNodeCommand(parent_id=sample_node_data.node_id, new_node_data=node3_data)
    res3 = command_manager.execute_command(cmd3)
    assert res3['success']
    assert len(command_manager.undo_stack) == 2 # cmd1, cmd3
    assert len(command_manager.redo_stack) == 0 # Redo stack cleared
    assert command_manager.undo_stack[0] == cmd1
    assert command_manager.undo_stack[1] == cmd3

    # Undo two
    res_undo2 = command_manager.undo() # Undo cmd3
    assert res_undo2['success']
    res_undo3 = command_manager.undo() # Undo cmd1
    assert res_undo3['success']
    assert len(command_manager.undo_stack) == 0
    assert len(command_manager.redo_stack) == 2
    # *** Corrected assertion order for redo stack ***
    assert command_manager.redo_stack[0] == cmd3 # First undone was cmd3
    assert command_manager.redo_stack[1] == cmd1 # Second undone was cmd1

    # Redo two
    res_redo1 = command_manager.redo() # Redo cmd1 (which is at index 1)
    assert res_redo1['success']
    res_redo2 = command_manager.redo() # Redo cmd3 (which is now at index 0)
    assert res_redo2['success']
    assert len(command_manager.undo_stack) == 2
    assert len(command_manager.redo_stack) == 0
    # Check order in undo stack after redo
    assert command_manager.undo_stack[0] == cmd1
    assert command_manager.undo_stack[1] == cmd3


# --- Add tests for AddEdgeCommand and RemoveEdgeCommand ---

def test_add_remove_edge_command(command_manager_with_simple_graph: CommandManager):
    """Test adding and removing edges."""
    manager = command_manager_with_simple_graph
    parent_id = "root"
    child_node = DialogueNode(node_id="child_edge_test")
    add_node_cmd = AddNodeCommand(parent_id=None, new_node_data=child_node)
    manager.execute_command(add_node_cmd) # Add the child node first

    # Test Add Edge
    # *** Corrected: Pass edge data as a dictionary ***
    edge_attributes = {'weight': 5, 'label': 'test_edge'}
    add_edge_cmd = AddEdgeCommand(parent_id=parent_id, child_id=child_node.node_id, edge_data=edge_attributes)
    result_add = manager.execute_command(add_edge_cmd)
    assert result_add['success'] is True
    assert manager.dialogue_graph.graph.has_edge(parent_id, child_node.node_id)
    assert manager.dialogue_graph.graph.edges[parent_id, child_node.node_id]['weight'] == 5
    assert manager.dialogue_graph.graph.edges[parent_id, child_node.node_id]['label'] == 'test_edge'
    assert manager.can_undo() is True

    # Test Undo Add Edge
    undo_add_result = manager.undo()
    assert undo_add_result['success'] is True
    assert not manager.dialogue_graph.graph.has_edge(parent_id, child_node.node_id)
    assert manager.can_redo() is True

    # Test Redo Add Edge
    redo_add_result = manager.redo()
    assert redo_add_result['success'] is True
    assert manager.dialogue_graph.graph.has_edge(parent_id, child_node.node_id)
    assert manager.dialogue_graph.graph.edges[parent_id, child_node.node_id]['weight'] == 5
    assert manager.dialogue_graph.graph.edges[parent_id, child_node.node_id]['label'] == 'test_edge'
    assert manager.can_undo() is True

    # Test Remove Edge
    remove_edge_cmd = RemoveEdgeCommand(parent_id=parent_id, child_id=child_node.node_id)
    result_remove = manager.execute_command(remove_edge_cmd)
    assert result_remove['success'] is True
    assert not manager.dialogue_graph.graph.has_edge(parent_id, child_node.node_id)
    assert manager.can_undo() is True

    # Test Undo Remove Edge
    undo_remove_result = manager.undo()
    assert undo_remove_result['success'] is True
    assert manager.dialogue_graph.graph.has_edge(parent_id, child_node.node_id)
    # Check edge data restored correctly
    assert manager.dialogue_graph.graph.edges[parent_id, child_node.node_id]['weight'] == 5
    assert manager.dialogue_graph.graph.edges[parent_id, child_node.node_id]['label'] == 'test_edge'
    assert manager.can_redo() is True

    # Test Redo Remove Edge
    redo_remove_result = manager.redo()
    assert redo_remove_result['success'] is True
    assert not manager.dialogue_graph.graph.has_edge(parent_id, child_node.node_id)
    assert manager.can_undo() is True
