# dialogue_editor/command_manager.py

from typing import List, Dict, Any
from .data_models import DialogueGraph
from .commands import Command # Use relative import

class CommandManager:
    """Manages command execution, undo, and redo."""

    def __init__(self, dialogue_graph: DialogueGraph):
        self.dialogue_graph = dialogue_graph
        self.undo_stack: List[Command] = []
        self.redo_stack: List[Command] = []

    def execute_command(self, command: Command) -> Dict[str, Any]:
        """Executes a command, updates stacks, and returns results."""
        try:
            result = command.execute(self.dialogue_graph)
            if result.get('success', False):
                self.undo_stack.append(command)
                self.redo_stack.clear() # Clear redo stack on new action
            # Always include graph data in result for store update
            result['graph_data'] = self.get_graph_data()
            return result
        except Exception as e:
            print(f"Error during command execution: {command.__class__.__name__} - {e}")
            return {'success': False, 'status': f"Command execution failed: {e}", 'graph_data': self.get_graph_data()}


    def undo(self) -> Dict[str, Any]:
        """Undoes the last command."""
        if not self.can_undo():
            return {'success': False, 'status': "Nothing to undo.", 'graph_data': self.get_graph_data()}

        command = self.undo_stack.pop()
        try:
            result = command.undo(self.dialogue_graph)
            if result.get('success', False):
                self.redo_stack.append(command)
            else:
                self.undo_stack.append(command) # Revert stack change on failure
            # Always include graph data in result
            result['graph_data'] = self.get_graph_data()
            return result
        except Exception as e:
            print(f"Error during command undo: {command.__class__.__name__} - {e}")
            self.undo_stack.append(command) # Revert stack
            return {'success': False, 'status': f"Command undo failed: {e}", 'graph_data': self.get_graph_data()}

    def redo(self) -> Dict[str, Any]:
        """Redoes the last undone command."""
        if not self.can_redo():
            return {'success': False, 'status': "Nothing to redo.", 'graph_data': self.get_graph_data()}

        command = self.redo_stack.pop()
        try:
            result = command.execute(self.dialogue_graph) # Re-execute
            if result.get('success', False):
                self.undo_stack.append(command)
            else:
                self.redo_stack.append(command) # Revert stack change on failure
            # Always include graph data in result
            result['graph_data'] = self.get_graph_data()
            return result
        except Exception as e:
            print(f"Error during command redo: {command.__class__.__name__} - {e}")
            self.redo_stack.append(command) # Revert stack
            return {'success': False, 'status': f"Command redo failed: {e}", 'graph_data': self.get_graph_data()}

    def can_undo(self) -> bool:
        """Checks if the undo stack is not empty."""
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        """Checks if the redo stack is not empty."""
        return bool(self.redo_stack)

    def get_graph_data(self) -> Dict:
        """Serializes the current graph state."""
        return self.dialogue_graph.to_dict()
