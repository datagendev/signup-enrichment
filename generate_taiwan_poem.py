import asyncio
import os
from claude_agent_sdk import query, ClaudeAgentOptions
from random_number_generator import generate_random_number


async def main():
    github_token = os.environ.get('GITHUB_TOKEN')
    github_repo = os.environ.get('GITHUB_REPO')
    
    options = ClaudeAgentOptions(
        system_prompt="You are an expert poet and developer",
        permission_mode='bypassPermissions',
        cwd=os.getcwd()
    )

    git_email = os.environ.get('GIT_USER_EMAIL', 'bot@example.com')
    git_name = os.environ.get('GIT_USER_NAME', 'Render Bot')
    
    prompt = f"""
1. First, run the random_number_generator.py script using Python to get a random number and display it clearly to the user
"""

    async for message in query(prompt=prompt, options=options):
        print(message)


asyncio.run(main())
