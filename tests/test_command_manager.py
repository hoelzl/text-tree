# tests/test_command_manager.py

import pytest
import copy
from typing import List, Dict, Any, Optional, Union, Tuple, Type
from unittest.mock import MagicMock # For mocking commands

# Imports from the package
from dialogue_editor.data_models import (
    DialogueGraph, DialogueNode, NodeType, Speaker, GenericSpeaker, SpecificSpeaker, TextVersion
)
from dialogue_editor.commands import (
    Command, AddNodeCommand, DeleteNodeCommand # Import real commands for integration tests
)
from dialogue_editor.command_manager import CommandManager

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

# --- Mock Command for Manager Tests ---
class MockCommand(Command):
    def __init__(self, success=True, undo_success=True):
        self.execute_called = 0
        self.undo_called = 0
        self.success = success
        self.undo_success = undo_success

    def execute(self, graph: DialogueGraph) -> Dict[str, Any]:
        self.execute_called += 1
        return {'success': self.success, 'status': 'Mock execute'}

    def undo(self, graph: DialogueGraph) -> Dict[str, Any]:
        self.undo_called += 1
        return {'success': self.undo_success, 'status': 'Mock undo'}

# ===========================================
# --- Unit Tests for CommandManager ---
# ===========================================

def test_command_manager_execute(command_manager: CommandManager):
    """Test CommandManager execute clears redo stack and adds to undo."""
    mock_cmd = MockCommand()
    # Pre-populate redo stack to test clearing
    command_manager.redo_stack.append(MockCommand())

    result = command_manager.execute_command(mock_cmd)

    assert result['success'] is True
    assert mock_cmd.execute_called == 1
    assert len(command_manager.undo_stack) == 1
    assert command_manager.undo_stack[0] == mock_cmd
    assert len(command_manager.redo_stack) == 0 # Redo stack cleared
    assert command_manager.can_undo() is True
    assert command_manager.can_redo() is False
    assert 'graph_data' in result # Check graph data is returned

def test_command_manager_execute_failure(command_manager: CommandManager):
    """Test CommandManager execute handles command failure."""
    mock_cmd = MockCommand(success=False)
    result = command_manager.execute_command(mock_cmd)

    assert result['success'] is False
    assert mock_cmd.execute_called == 1
    assert len(command_manager.undo_stack) == 0 # Not added on failure
    assert len(command_manager.redo_stack) == 0
    assert 'graph_data' in result

def test_command_manager_undo(command_manager: CommandManager):
    """Test CommandManager undo."""
    mock_cmd = MockCommand()
    command_manager.execute_command(mock_cmd) # Execute first

    assert command_manager.can_undo() is True
    result = command_manager.undo()

    assert result['success'] is True
    assert mock_cmd.undo_called == 1
    assert len(command_manager.undo_stack) == 0
    assert len(command_manager.redo_stack) == 1
    assert command_manager.redo_stack[0] == mock_cmd
    assert command_manager.can_undo() is False
    assert command_manager.can_redo() is True
    assert 'graph_data' in result

def test_command_manager_undo_failure(command_manager: CommandManager):
    """Test CommandManager undo handles command undo failure."""
    mock_cmd = MockCommand(undo_success=False)
    command_manager.execute_command(mock_cmd)

    result = command_manager.undo()
    assert result['success'] is False
    assert mock_cmd.undo_called == 1
    assert len(command_manager.undo_stack) == 1 # Command pushed back on failure
    assert len(command_manager.redo_stack) == 0
    assert 'graph_data' in result

def test_command_manager_redo(command_manager: CommandManager):
    """Test CommandManager redo."""
    mock_cmd = MockCommand()
    command_manager.execute_command(mock_cmd)
    command_manager.undo() # Undo first

    assert command_manager.can_redo() is True
    result = command_manager.redo()

    assert result['success'] is True
    assert mock_cmd.execute_called == 2 # Called again on redo
    assert len(command_manager.undo_stack) == 1
    assert command_manager.undo_stack[0] == mock_cmd
    assert len(command_manager.redo_stack) == 0
    assert command_manager.can_undo() is True
    assert command_manager.can_redo() is False
    assert 'graph_data' in result

def test_command_manager_redo_failure(command_manager: CommandManager):
    """Test CommandManager redo handles command execute failure during redo."""
    mock_cmd = MockCommand()
    command_manager.execute_command(mock_cmd)
    command_manager.undo()

    # Make the command fail on the *next* execute (the redo)
    mock_cmd.success = False
    result = command_manager.redo()

    assert result['success'] is False
    assert mock_cmd.execute_called == 2 # Attempted execute again
    assert len(command_manager.undo_stack) == 0 # Not added to undo on failure
    assert len(command_manager.redo_stack) == 1 # Pushed back onto redo on failure
    assert 'graph_data' in result

def test_command_manager_empty_undo_redo(command_manager: CommandManager):
    """Test undo/redo on empty stacks."""
    assert command_manager.can_undo() is False
    assert command_manager.can_redo() is False
    undo_result = command_manager.undo()
    assert undo_result['success'] is False
    assert "Nothing to undo" in undo_result['status']
    redo_result = command_manager.redo()
    assert redo_result['success'] is False
    assert "Nothing to redo" in redo_result['status']

# --- Integration-style tests (using manager with real commands) ---
# These ensure the manager and commands work together correctly

def test_integration_add_undo_redo(command_manager: CommandManager, sample_node_data: DialogueNode):
    """Test add -> undo -> redo flow via manager."""
    cmd = AddNodeCommand(parent_id=None, new_node_data=sample_node_data)

    # Execute
    res_exec = command_manager.execute_command(cmd)
    assert res_exec['success']
    assert sample_node_data.node_id in command_manager.dialogue_graph.graph

    # Undo
    res_undo = command_manager.undo()
    assert res_undo['success']
    assert sample_node_data.node_id not in command_manager.dialogue_graph.graph

    # Redo
    res_redo = command_manager.redo()
    assert res_redo['success']
    assert sample_node_data.node_id in command_manager.dialogue_graph.graph

def test_integration_delete_undo_redo(command_manager_with_simple_graph: CommandManager):
    """Test delete -> undo -> redo flow via manager."""
    manager = command_manager_with_simple_graph
    node_id = "root"
    cmd_del = DeleteNodeCommand(node_id=node_id)

    # Execute
    res_exec = manager.execute_command(cmd_del)
    assert res_exec['success']
    assert node_id not in manager.dialogue_graph.graph

    # Undo
    res_undo = manager.undo()
    assert res_undo['success']
    assert node_id in manager.dialogue_graph.graph

    # Redo
    res_redo = manager.redo()
    assert res_redo['success']
    assert node_id not in manager.dialogue_graph.graph

def test_integration_command_manager_stacks(command_manager: CommandManager, sample_node_data: DialogueNode):
    """Test undo/redo stack management using real commands."""
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
    # Corrected assertion order for redo stack
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
