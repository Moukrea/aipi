from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from sse_starlette.sse import EventSourceResponse
import uvicorn
import logging
import time
import json
from typing import AsyncGenerator

from config import load_config
from models import ChatCompletionRequest, CLAUDE_MODELS, CHATGPT_MODELS
from bridge import LLMWebBridge
from cache import ConversationCache

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
config = load_config()

# Initialize cache and bridge
cache = ConversationCache(
    config['cache']['db_path'],
    config['cache']['cleanup_interval'],
    config['cache']['max_age']
)
bridge = LLMWebBridge(config, cache)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await bridge.initialize()
        await cache.start_cleanup()
        yield
    finally:
        # Shutdown
        if bridge.browser:
            await bridge.browser.close()

# Initialize FastAPI app
app = FastAPI(title="LLM Web Bridge API", lifespan=lifespan)

async def generate_streaming_response(model: str, message: str, is_new_chat: bool,
                                   chat_url: str, full_messages=None) -> AsyncGenerator[str, None]:
    """Generate streaming response in SSE format."""
    response_id = f"web-bridge-{int(time.time())}"
    created = int(time.time())
    
    try:
        async for chunk in bridge.stream_response(message, is_new_chat, chat_url, full_messages):
            response_data = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "delta": {
                        "content": chunk
                    },
                    "index": 0,
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(response_data)}\n\n"
        
        # Send the final chunk
        final_data = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "delta": {},
                "index": 0,
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(final_data)}\n\n"
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"Error in stream generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """Handle chat completion requests."""
    try:
        # Validate model
        if request.model not in CLAUDE_MODELS and request.model not in CHATGPT_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported model. Please use one of: {list(CLAUDE_MODELS.keys()) + list(CHATGPT_MODELS.keys())}"
            )
        
        # Process request and get chat URL
        chat_url, is_new_chat = await bridge.process_completion_request(
            request.model,
            [msg.dict() for msg in request.messages]
        )
        
        # Get the last message
        last_message = request.messages[-1]
        
        # Handle streaming response
        if request.stream:
            return EventSourceResponse(
                generate_streaming_response(
                    request.model,
                    last_message.content,
                    is_new_chat,
                    chat_url,
                    [msg.dict() for msg in request.messages] if is_new_chat else None
                )
            )
        
        # Handle non-streaming response
        response_text = await bridge.send_message(
            last_message.content,
            is_new_chat,
            chat_url,
            [msg.dict() for msg in request.messages] if is_new_chat else None
        )
        
        # Format response
        response = {
            "id": "web-bridge-" + str(hash(response_text)),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(last_message.content.split()),
                "completion_tokens": len(response_text.split()),
                "total_tokens": len(last_message.content.split()) + len(response_text.split())
            }
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing chat completion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config["server"]["host"],
        port=config["server"]["port"]
    )