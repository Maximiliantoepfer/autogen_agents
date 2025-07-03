import subprocess
import shlex
from autogen.agentchat.agent import ConversableAgentTool

class GitTool(ConversableAgentTool):
    def __init__(self, name="GitTool", repo_path=".", description=None):
        if description is None:
            description = (
                "Use this tool to run git commands in the repository, e.g.:\n"
                " - status\n"
                " - diff\n"
                " - checkout <branch_or_hash>\n"
                " - add .\n"
                " - commit -m 'your commit message'\n"
                "Input must be a valid git command without the prefix 'git'."
            )
        super().__init__(name=name, description=description)
        self.repo_path = repo_path

    def _run(self, command: str) -> str:
        try:
            git_cmd = ["git"] + shlex.split(command)
            result = subprocess.run(
                git_cmd,
                cwd=self.repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return f"[stderr]\n{result.stderr.strip()}"
        except Exception as e:
            return f"[error] {str(e)}"
