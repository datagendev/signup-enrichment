import asyncio
import os
from claude_agent_sdk import query, ClaudeAgentOptions


async def main():
    github_token = os.environ.get('GITHUB_TOKEN')
    github_repo = os.environ.get('GITHUB_REPO')
    
    options = ClaudeAgentOptions(
        system_prompt="You are an expert poet and developer",
        permission_mode='acceptEdits',
        cwd=os.getcwd()
    )

    git_email = os.environ.get('GIT_USER_EMAIL', 'bot@example.com')
    git_name = os.environ.get('GIT_USER_NAME', 'Render Bot')
    
    prompt = f"""
1. Write a beautiful poem about Taiwan and save it to 'taiwan_poem.txt'

2. Configure git and push to GitHub:
   - Set git user: git config user.email "{git_email}" && git config user.name "{git_name}"
   - Set remote with token: git remote set-url origin https://x-access-token:{github_token}@github.com/{github_repo}.git
   - Stage the file: git add taiwan_poem.txt
   - Commit: git commit -m "Add Taiwan poem"
   - Push: git push origin main
"""

    async for message in query(prompt=prompt, options=options):
        print(message)


asyncio.run(main())
