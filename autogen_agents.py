import os
import subprocess
import shlex
from typing_extensions import Annotated

from autogen import ConversableAgent, GroupChat, GroupChatManager, UserProxyAgent, register_function
from autogen.coding import DockerCommandLineCodeExecutor
from autogen_core.memory import ListMemory
from autogen import gather_usage_summary


# def read_file(path: Annotated[str, "Relative file path"]) -> str:
#     full = os.path.abspath(path)
#     root = os.getcwd()
#     if not full.startswith(root):
#         return "ERROR: outside working dir"
#     try:
#         with open(full, "r", encoding="utf-8") as f:
#             return f.read()
#     except Exception as e:
#         return f"ERROR: {e}"

# def write_file(path: Annotated[str, "Relative file path"], content: Annotated[str, "File content"]) -> str:
#     full = os.path.abspath(path)
#     root = os.getcwd()
#     if not full.startswith(root):
#         return "ERROR: outside working dir"
#     try:
#         with open(full, "w", encoding="utf-8") as f:
#             f.write(content)
#         return f"Wrote to {path}"
#     except Exception as e:
#         return f"ERROR: {e}"

# def list_dir(path: Annotated[str, "Directory path (optional)"] = ".") -> str:
#     full = os.path.abspath(path)
#     root = os.getcwd()
#     if not full.startswith(root):
#         return "ERROR: outside working dir"
#     try:
#         return "\\n".join(os.listdir(full))
#     except Exception as e:
#         return f"ERROR: {e}"

# def run_git(command: Annotated[str, "Git command without 'git' prefix"]) -> str:
#     cmd = ["git"] + shlex.split(command)
#     try:
#         r = subprocess.run(cmd, cwd=os.getcwd(), stdout=subprocess.PIPE,
#                            stderr=subprocess.PIPE, text=True, timeout=20)
#         return r.stdout if r.returncode == 0 else f"ERROR: {r.stderr.strip()}"
#     except Exception as e:
#         return f"ERROR: {e}"

class AutogenAgents:
    def __init__(self, llm_config={}, current_dir: str = "", executor=None, max_rounds: int = 5):
        self.llm_config = llm_config
        self.manager = None
        self.agents = []
        self.current_dir = current_dir
        self.last_chat = None

        # Code-Executor im Docker-Container
        if not executor:
            executor = DockerCommandLineCodeExecutor(
                image="maximiliantoepfer1/autogen-agent",
                timeout=120,
                work_dir=current_dir,
            )
        # self.executor = executor

        self.planner_agent = ConversableAgent(
            name="Planner_Agent",
            system_message=(
                "You are a Senior Python Software Engineer acting as the Planner Agent.\n"
                f"You work in the repository located at {current_dir}.\n"
                "Your job is to analyze the coding task described by the user and create a step-by-step plan for the implementation.\n"
                "The plan must include for each step:\n "
                "- The full path to the file to be created or modified (e.g., 'src/prices/get_prices.py') \n"
                "- A precise description of what should be added, changed, or removed in that file \n"
                "You are not allowed to write any code yourself. Your task is only to generate a clear plan for the Coding Agent. \n"
                "Do not assume that Git is used. You can assume that the project is locally available as files. \n"
                "After reasoning and exploration, you must stop and write the final plan in natural language."
                "If you notice that no progress is being made, or that you cannot proceed, you must respond with the word 'TERMINATE'. "
                "Do not continue the conversation endlessly.  Always ensure to stop the conversation if your task is completed or blocked."
            ),
            llm_config=llm_config,
            # chat_messages=memory,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=max_rounds,
            is_termination_msg=lambda msg: "TERMINATE" in msg["content"].upper(),
        )

        self.coding_agent = ConversableAgent(
            name="Coding_Agent",
            system_message=(
                "You are a Senior Software Developer acting as the Coding Agent.\n"
                f"You work directly on the codebase in the local repository at {current_dir}.\n"
                "You will receive a step-by-step plan from the Planner Agent that describes which files need to be created or modified and what changes should be made.\n"
                "___\n"
                "For each step:\n"
                "- Open the specified file\n"
                "- Read the entire file\n"
                "- Apply the required changes\n"
                "- Overwrite the file with the complete updated content\n"
                "Always ensure that you write the full content of the target file — never just append snippets or make partial replacements.\n"
                "Only use proper Python filenames such as 'main.py', 'get_prices.py', etc. that reflect the project structure.\n"
                "You must not use Git or mention git commands. Just write files locally in the file system."
                "If you notice that no progress is being made, or that you cannot proceed, you must respond with the word 'TERMINATE'. "
                "Do not continue the conversation endlessly.  Always ensure to stop the conversation if your task is completed or blocked."

            ),
            llm_config=llm_config,
            # chat_messages=memory,
            code_execution_config={"executor": executor},
            human_input_mode="NEVER",
            max_consecutive_auto_reply=max_rounds,
            is_termination_msg=lambda msg: "TERMINATE" in msg["content"].upper(),
        )

        # Test Agent blockiert ziemlich oft den Chat und sorgt für ewige loops - daher vorerst deaktiviert
        # self.test_agent = ConversableAgent(
        #     name="Test_Agent",
        #     system_message=(
        #         "You are a Senior QA Engineer acting as the Test Agent.\n"
        #         f"You work directly on the codebase in the local repository at {current_dir}.\n"
        #         "You review the changes made by the Coding Agent.\n"
        #         "You will verify whether the planned implementation is complete and consistent with the task description.\n"
        #         "\n"
        #         "You may do the following:\n"
        #         "- Read the changed files\n"
        #         "- Describe what you see in them\n"
        #         "- Optionally execute test commands like `pytest` or `python file.py` if appropriate\n"
        #         "\n"
        #         "You are not allowed to modify code or use Git.\n"
        #         "If you are confident that the implementation is correct and complete, then respond with:\n"
        #         "'TERMINATE'\n"
        #         "Otherwise, provide specific feedback on what is missing or needs improvement."

        #     ),
        #     llm_config=llm_config,
        #     # chat_messages=memory,
        #     code_execution_config={"executor": executor},
        #     human_input_mode="NEVER",
        #     is_termination_msg=lambda msg: "TERMINATE" in msg["content"].upper(),
        # )

        self.agents = [
            self.planner_agent, 
            self.coding_agent, 
            # self.test_agent
        ]

        self.user_proxy = UserProxyAgent(
            name="User",
            system_message=(
                "You are a helpful AI-Assistant with User role. "
                "Your task is to describe the coding problem and accept the results produced by the agents. "
                "You do not intervene in the planning, coding, or testing steps."
                "If you notice that no progress is being made, or that you cannot proceed, you must respond with the word 'TERMINATE'. "
                "Do not continue the conversation endlessly.  Always ensure to stop the conversation if your task is completed or blocked."

            ),
            llm_config=self.llm_config,
            human_input_mode="NEVER",
            code_execution_config={"executor": executor},
            max_consecutive_auto_reply=max_rounds,
            is_termination_msg=lambda msg: "TERMINATE" in msg["content"].upper(),
        )
        
        
        # !!! TOOLS funktionieren auch nach vielem probieren nicht zuverlässig ... !!!
        # Als code scheint deprecated zu sein, aber die register_functions wirft manchmal Fehler. 
        # Agenten brauchen es aber scheinbar nicht zum bearbeiten.
        
        # for agent in self.agents:
        #     register_function(read_file, caller=agent, executor=self.user_proxy, name="read_file", description="Read a file.")
        #     register_function(write_file, caller=agent, executor=self.user_proxy, name="write_file", description="Overwrite file.")
        #     register_function(list_dir, caller=agent, executor=self.user_proxy, name="list_dir", description="List directory.")
        #     register_function(run_git, caller=agent, executor=self.user_proxy, name="run_git", description="Run git command.")


    def assign_task(self, task: str, max_rounds: int = 5):
        groupchat = GroupChat(agents=[self.user_proxy] + self.agents, messages=[], max_round=max_rounds)
        self.manager = GroupChatManager(
            groupchat=groupchat,
            name="Autogen_Agents_Manager",
            system_message=(
                "You are the manager of the Autogen Agents. "
                "Your job is to coordinate the agents to solve the user task step by step. "
                "Ensure that each agent performs its role correctly and does not interfere with others."
                "If you notice that no progress is being made, or that you cannot proceed, you must respond with the word 'TERMINATE'. "
                "Do not continue the conversation endlessly.  Always ensure to stop the conversation if your task is completed or blocked."

            ),
            max_consecutive_auto_reply=max_rounds,
            llm_config=self.llm_config,
            human_input_mode="NEVER",
            is_termination_msg=lambda msg: "TERMINATE" in msg["content"].upper(),
        )
        chat = self.user_proxy.initiate_chat(self.manager, message=task, max_turns=max_rounds)
        self.last_chat_cost = chat.cost
        return chat.cost
        
    def get_token_usage(self):
        return self.last_chat_cost
        # if self.last_chat:
        #     try:
        #         with open("info.log", "w", encoding="utf-8") as log:   
        #             log.write(f"Info\n") 
        #         cost_info = self.last_chat_cost
        #         with open("info.log", "a", encoding="utf-8") as log:   
        #             log.write(f"cost: {cost_info}\n") 
        #         usage = cost_info.get("usage_including_cached_inference")
        #         if usage: 
        #             # ggf. erster Model-Eintrag extrahieren
        #             model_key = next( iter(usage) ) 
        #             model_usage = usage[model_key]
        #             with open("info.log", "a", encoding="utf-8") as log:   
        #                 log.write(f"usage: {usage}\n") 
        #             return {
        #                 "model": model_key,
        #                 "prompt_tokens": model_usage.get("prompt_tokens", 0),
        #                 "completion_tokens": model_usage.get("completion_tokens", 0),
        #                 "total_tokens": model_usage.get("total_tokens", 0),
        #                 "total_cost": model_usage.get("cost", 0.0)
        #             }
        #     except Exception as e:
        #         print(f"Failed to extract cost info: {e}")
        #         return None
    
        # print("No chat session available to extract token usage.")
        # return None