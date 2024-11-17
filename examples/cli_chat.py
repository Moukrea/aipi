import asyncio
import json
import os
from datetime import datetime
from typing import Optional, List

import httpx
import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live
from rich.text import Text

# Styling
style = Style.from_dict({
    'prompt': '#00aa00 bold',
    'model': '#888888 italic',
})

console = Console()

class ChatCLI:
    def __init__(self, api_url: str, model: str):
        self.api_url = api_url.rstrip('/')
        self.model = model
        self.session = PromptSession(
            message=[
                ('class:model', f'[{model}] '),
                ('class:prompt', '> '),
            ],
            style=style
        )
        self.messages: List[dict] = []
        self.client = httpx.AsyncClient()

    async def get_user_input(self) -> Optional[str]:
        try:
            message = await self.session.prompt_async()
            if message.strip().lower() in ['quit', 'exit', 'q']:
                return None
            return message
        except (EOFError, KeyboardInterrupt):
            return None

    async def stream_response(self, messages: List[dict]):
        response = await self.client.post(
            f"{self.api_url}/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "stream": True
            },
            timeout=None,
            headers={"Accept": "text/event-stream"}
        )

        full_response = ""
        with Live(console=console, refresh_per_second=4) as live:
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data)
                        content = chunk['choices'][0]['delta'].get('content', '')
                        if content:
                            full_response += content
                            live.update(Markdown(full_response))
                    except json.JSONDecodeError:
                        continue

        return full_response

    def save_conversation(self):
        if not self.messages:
            return
        
        # Create conversations directory if it doesn't exist
        os.makedirs('conversations', exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'conversations/chat_{timestamp}.md'
        
        # Write conversation to file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Conversation with {self.model}\n\n")
            for msg in self.messages:
                role = msg['role'].title()
                content = msg['content']
                f.write(f"## {role}\n{content}\n\n")
        
        console.print(f"\n[green]Conversation saved to {filename}[/green]")

    async def chat_loop(self):
        console.print(Panel(
            Text.from_markup(
                "Welcome to the LLM Web Bridge Chat CLI!\n"
                "Type your message and press Enter to send.\n"
                "Type 'quit', 'exit', or 'q' to end the conversation."
            ),
            title="LLM Web Bridge",
            subtitle="Press Ctrl+C to exit"
        ))

        try:
            while True:
                user_message = await self.get_user_input()
                if user_message is None:
                    break

                # Add user message to history
                self.messages.append({"role": "user", "content": user_message})

                try:
                    # Get streaming response
                    assistant_response = await self.stream_response(self.messages)
                    
                    # Add assistant response to history
                    self.messages.append({"role": "assistant", "content": assistant_response})
                    
                    console.print()  # Add a blank line for readability
                
                except Exception as e:
                    console.print(f"\n[red]Error: {str(e)}[/red]")
                    continue

        except KeyboardInterrupt:
            pass
        
        finally:
            # Save conversation on exit
            if self.messages:
                save = typer.confirm("\nDo you want to save this conversation?")
                if save:
                    self.save_conversation()
            
            await self.client.aclose()

def main(
    api_url: str = typer.Option("http://localhost:8000", help="API URL"),
    model: str = typer.Option(
        "aipi/anthropic/claude-3.5-sonnet",
        help="Model to use"
    )
):
    """
    Interactive CLI chat interface for LLM Web Bridge
    """
    async def run():
        chat = ChatCLI(api_url, model)
        await chat.chat_loop()

    asyncio.run(run())

if __name__ == "__main__":
    typer.run(main)