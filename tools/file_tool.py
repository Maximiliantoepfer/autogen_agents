import os
from autogen.agentchat.agent import ConversableAgentTool


class FileTool(ConversableAgentTool):
    def __init__(self, root_dir: str):
        super().__init__(
            name="FileTool",
            description=(
                "Read or write a file inside the project directory. "
                "Use `read <relative_path>` to read a file, and `write <relative_path> <content>` to overwrite it."
            )
        )
        self.root_dir = os.path.abspath(root_dir)

    def _run(self, command: str) -> str:
        parts = command.strip().split(" ", 2)
        if len(parts) < 2:
            return "Invalid command. Use `read <file>` or `write <file> <content>`"

        action, rel_path = parts[0], parts[1]
        path = os.path.abspath(os.path.join(self.root_dir, rel_path))

        # Sicherheit: Nur im erlaubten Verzeichnis
        if not path.startswith(self.root_dir):
            return "Access denied: file is outside of root directory."

        if action == "read":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Error reading file: {e}"

        elif action == "write" and len(parts) == 3:
            content = parts[2]
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Successfully wrote to {rel_path}."
            except Exception as e:
                return f"Error writing file: {e}"

        return "Invalid command. Use `read <file>` or `write <file> <content>`"
