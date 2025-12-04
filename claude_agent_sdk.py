"""
Simple Claude Agent SDK wrapper for using Claude Agent SDK tools
"""
import os
import asyncio
from typing import Optional, List

try:
    from claude_agent_sdk import query, ClaudeAgentOptions
except ImportError:
    # Fallback: try alternative import path
    try:
        from claude_agent_sdk.sdk import query, ClaudeAgentOptions
    except ImportError:
        raise ImportError(
            "claude-agent-sdk package not found. Install it with: pip install claude-agent-sdk"
        )


class ClaudeAgent:
    """Simple SDK wrapper for Claude Agent SDK interactions"""
    
    def __init__(self, api_key: Optional[str] = None, allowed_tools: Optional[List[str]] = None):
        """
        Initialize the Claude Agent SDK
        
        Args:
            api_key: Anthropic API key. If not provided, will try to get from ANTHROPIC_API_KEY env var
            allowed_tools: List of tools to allow (e.g., ["Write", "Read"]). Defaults to ["Write"]
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("API key is required. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter.")
        
        # Set the API key in environment if not already set
        if not os.getenv('ANTHROPIC_API_KEY'):
            os.environ['ANTHROPIC_API_KEY'] = self.api_key
        
        self.allowed_tools = allowed_tools or ["Write"]
    
    async def query(self, 
                    prompt: str,
                    permission_mode: str = "auto",
                    allowed_tools: Optional[List[str]] = None) -> dict:
        """
        Query Claude Agent SDK with tool support
        
        Args:
            prompt: The prompt/question to send to Claude
            permission_mode: Permission mode ("auto", "prompt", "deny"). Defaults to "auto"
            allowed_tools: Override default allowed tools for this query
            
        Returns:
            Dictionary with tool_use information if a tool was used, otherwise text response
        """
        tools = allowed_tools or self.allowed_tools
        
        options = ClaudeAgentOptions(
            allowed_tools=tools,
            permission_mode=permission_mode,
        )
        
        async for message in query(prompt=prompt, options=options):
            if hasattr(message, 'tool_use') and message.tool_use:
                return {
                    'tool_name': message.tool_use.name,
                    'tool_input': message.tool_use.input,
                    'tool_use': message.tool_use
                }
            elif hasattr(message, 'text') and message.text:
                return {
                    'text': message.text,
                    'tool_use': None
                }
        
        return {'text': '', 'tool_use': None}
    
    def query_sync(self, 
                   prompt: str,
                   permission_mode: str = "auto",
                   allowed_tools: Optional[List[str]] = None) -> dict:
        """
        Synchronous wrapper for query method
        
        Args:
            prompt: The prompt/question to send to Claude
            permission_mode: Permission mode ("auto", "prompt", "deny"). Defaults to "auto"
            allowed_tools: Override default allowed tools for this query
            
        Returns:
            Dictionary with tool_use information if a tool was used, otherwise text response
        """
        return asyncio.run(self.query(prompt, permission_mode, allowed_tools))

