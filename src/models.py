from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum

class AuthMethod(str, Enum):
    DIRECT = "direct"
    GOOGLE = "google"

class ModelProvider(str, Enum):
    ANTHROPIC = "aipi/anthropic"
    OPENAI = "aipi/openai"

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]

# Model configurations
CLAUDE_MODELS = {
    f"{ModelProvider.ANTHROPIC}/claude-3-opus": {
        "selector": "button[aria-label='Claude 3 Opus']",
        "display_name": "Claude 3 Opus"
    },
    f"{ModelProvider.ANTHROPIC}/claude-3.5-sonnet": {
        "selector": "button[aria-label='Claude 3.5 Sonnet']",
        "display_name": "Claude 3.5 Sonnet"
    },
    f"{ModelProvider.ANTHROPIC}/claude-3-haiku": {
        "selector": "button[aria-label='Claude 3 Haiku']",
        "display_name": "Claude 3 Haiku"
    }
}

CHATGPT_MODELS = {
    f"{ModelProvider.OPENAI}/gpt-4": {
        "selector": "button[aria-label='GPT-4']",
        "display_name": "GPT-4"
    },
    f"{ModelProvider.OPENAI}/gpt-3.5-turbo": {
        "selector": "button[aria-label='GPT-3.5']",
        "display_name": "GPT-3.5"
    }
}