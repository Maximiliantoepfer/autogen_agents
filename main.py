import autogen
import re
import os
import sys
import asyncio
import json
import re
import platform
import requests
import subprocess
import contextlib
from icecream import ic
from config import OPENAI_API_KEY
from autogen_agents import AutogenAgents

# --- Maximale Runden für den Chat ---
MAX_CHAT_ROUNDS = 7

WORK_DIR = os.path.abspath('repos')
LOG_DIR = os.path.abspath('logs')

os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = f"{LOG_DIR}/results.log"	
with open(LOG_FILE, "w", encoding="utf-8") as log:
    log.write(f"--- Starting new run on {platform.node()} at {os.getcwd()} ---\n")
    
TASK_API_URL = "http://localhost:8081/task/index/"  # API endpoint for SWE-Bench-Lite

# Konfiguration des LLM (Large Language Model)
config_list = [
    # {
    #     "model": "gpt-4o-mini",
    #     "api_key": OPENAI_API_KEY,
    #     "base_url": "http://188.245.32.59:4000/v1",  # Local LLM server
    #     "max_tokens": 8096,
    # },
    {
        "model": "gpt-4o",
        "api_key": OPENAI_API_KEY,
        "base_url": "http://188.245.32.59:4000/v1",  # Local LLM server
        "max_tokens": 8096,
    },
]


async def handle_task(index):
    api_url = f"{TASK_API_URL}{index}"
    print(f"Fetching test case {index} from {api_url}...")
    repo_dir = os.path.join(WORK_DIR, f"repo_{index}")  # Use unique repo directory per task
    start_dir = os.getcwd()  # Remember original working directory

    response = requests.get(api_url)
    if response.status_code != 200:
        raise Exception(f"Invalid response: {response.status_code}")

    testcase = response.json()
    prompt = testcase["Problem_statement"]
    git_clone = testcase["git_clone"]
    fail_tests = json.loads(testcase.get("FAIL_TO_PASS", "[]"))
    pass_tests = json.loads(testcase.get("PASS_TO_PASS", "[]"))
    instance_id = testcase["instance_id"]
    
    print(f"Received prompt for test case {index}: {len(prompt)} characters")
    print(f"Git: {git_clone}")
    print("______________________________")
    print("Starting test case processing...")
    print("______________________________")
    
    # Extract repo URL and commit hash
    parts = git_clone.split("&&")
    clone_part = parts[0].strip()
    checkout_part = parts[-1].strip() if len(parts) > 1 else None

    repo_url = clone_part.split()[2]
    
    try:
        ic("Setting up our repo dependencies if any...")
        # Extrahiere Commit-Hash
        commit_hash = checkout_part.split()[-1] if checkout_part else "main"

        # Repository aufbauen
        setup_repo(repo_url, repo_dir, commit_hash)
    except Exception as e:
        print(f"Error setting up repository for test case {index}: {e}")
        
    try:
        ic("Starting the code generation process...")
        current_dir = os.path.join(WORK_DIR, f"repo_{index}")

        ic("Starting chat with agents...")
        agents = AutogenAgents(llm_config=config_list[0], current_dir=current_dir, max_rounds=MAX_CHAT_ROUNDS)
        chat_cost = agents.assign_task(
            task=prompt,
            max_rounds=MAX_CHAT_ROUNDS,
        )
        ic(chat_cost)
        ic("Chat completed.")
        
        # git commit manuell durchführen, da die Agents auch bei direkter Anordung nie eigenständig korrekt commiten konnten.
        try:
            env = os.environ.copy()
            subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, env=env)
            ic("Git add completed.")
            subprocess.run(["git", "commit", "-m", "Solved Task by Autogen"], cwd=repo_dir, check=True, env=env)
            ic("Git commit completed.")
        except subprocess.CalledProcessError as e:
            print(f"Git commit failed: {e}")

    except Exception as e:
        print(f"Error during chat processing for test case {index}: {e}")


    ic("Evaluating test results...")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as log:            
                log.write(f"\n--- TESTCASE {index} ---\n")
        
        try:
            usage = chat_cost.get('usage_including_cached_inference')
            ic(usage)
            # Modellnamen filtern (alles außer 'total_cost')
            model_data = {k: v for k, v in usage.items() if k != 'total_cost'}

            # Falls du nur den ersten (oder einzigen) Eintrag brauchst:
            model_name, data = next(iter(model_data.items()))

            total_tokens = data['total_tokens']
            total_cost = usage['total_cost']
            with open(LOG_FILE, "a", encoding="utf-8") as log:   
                log.write(f"Model: {model_name}\n")
                log.write(f"Total Tokens Used: {total_tokens}\n")
                log.write(f"Total Cost: {total_cost:.4f}\n")
        except Exception as e:
            with open(LOG_FILE, "a", encoding="utf-8") as log:   
                log.write(f"No Token Info: {e}\n") 

        # Call REST service instead for evaluation changes from agent
        ic(f"Calling SWE-Bench REST service with repo", repo_dir)
        try:
            test_payload = { 
                "instance_id": instance_id,
                "repoDir": f"/repos/repo_{index}",  # mount with docker
                "FAIL_TO_PASS": fail_tests,
                "PASS_TO_PASS": pass_tests
            }
            res = requests.post("http://localhost:8082/test", json=test_payload) 
            ic(res)
            ic(res.status_code)  
            ic(res.text)
            res.raise_for_status()
            result_raw = res.json().get("harnessOutput", "{}")
            result_json = json.loads(result_raw)
            if not result_json:
                raise ValueError("No data in harnessOutput – possible evaluation error or empty result")
            instance_id = next(iter(result_json))
            tests_status = result_json[instance_id]["tests_status"]
            fail_pass_results = tests_status["FAIL_TO_PASS"]
            fail_pass_total = len(fail_pass_results["success"]) + len(fail_pass_results["failure"])
            fail_pass_passed = len(fail_pass_results["success"])
            pass_pass_results = tests_status["PASS_TO_PASS"]
            pass_pass_total = len(pass_pass_results["success"]) + len(pass_pass_results["failure"])
            pass_pass_passed = len(pass_pass_results["success"])
  
            # Log results
            os.chdir(start_dir)
            with open(LOG_FILE, "a", encoding="utf-8") as log: 
                log.write(f"FAIL_TO_PASS passed: {fail_pass_passed}/{fail_pass_total}\n") 
                log.write(f"PASS_TO_PASS passed: {pass_pass_passed}/{pass_pass_total}\n")
        except Exception as e: 
            os.chdir(start_dir)  
            with open(LOG_FILE, "a", encoding="utf-8") as log:
                log.write(f"Error calling SWE-Bench Test service: {e}\n")
            print(f"Error calling SWE-Bench Test service for test case {index}: {e}")
            return
        print(f"Test case {index} completed and logged.")
    except Exception as e:
        os.chdir(start_dir)
        with open(LOG_FILE, "a", encoding="utf-8") as log: 
            log.write(f"Error: {e}\n")
        print(f"Error in test case {index}: {e}") 


def setup_repo(repo_url: str, repo_dir: str, commit_hash: str):
    ic("Setting up repository...")

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    if not os.path.exists(repo_dir): 
        subprocess.run(["git", "clone", repo_url, repo_dir], check=True, env=env)
    else:
        ic(f"Repo {repo_dir} already exists – skipping clone.")
  
    subprocess.run(["git", "checkout", commit_hash], cwd=repo_dir, check=True, env=env)
    ic("Repository checked out.")

 
    

async def main():  
    for i in range(1, 100, 5):
        await handle_task(i)

  
if __name__ == "__main__":
    asyncio.run(main())