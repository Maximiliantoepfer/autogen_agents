import os
from autogen.agentchat.agent import ConversableAgentTool

class ListDirectoryTool(ConversableAgentTool):
    def __init__(self, root_dir: str):
        super().__init__(
            name="ListDirectoryTool",
            description="List the contents of a directory. Usage: `ls [relative_path]`"
        )
        self.root_dir = os.path.abspath(root_dir)

    def _run(self, command: str) -> str:
        rel_path = command.strip() if command else "."
        path = os.path.abspath(os.path.join(self.root_dir, rel_path))

        # Sicherheit
        if not path.startswith(self.root_dir):
            return "Access denied: directory is outside of root directory."

        if not os.path.isdir(path):
            return f"'{rel_path}' is not a valid directory."

        try:
            entries = os.listdir(path)
            return "\n".join(entries)
        except Exception as e:
            return f"Error listing directory: {e}"
