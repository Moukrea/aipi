from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import logging
from typing import Tuple, List, Dict, AsyncGenerator
import asyncio
import time
from models import CLAUDE_MODELS, CHATGPT_MODELS, ModelProvider
from cache import ConversationCache
from google_auth import GoogleAuth

logger = logging.getLogger(__name__)

class LLMWebBridge:
   def __init__(self, config: dict, cache: ConversationCache):
       self.config = config
       self.cache = cache
       self.browser: Browser = None
       
       # Service contexts and pages
       self.claude_context: BrowserContext = None
       self.claude_page: Page = None
       self.chatgpt_context: BrowserContext = None
       self.chatgpt_page: Page = None
       
       # Google auth handlers
       self.claude_auth = GoogleAuth("claude")
       self.chatgpt_auth = GoogleAuth("chatgpt")
       
       self.initialized = False
       self.current_model = None
       
       # Development mode settings
       self.debug = config.get('dev', {}).get('debug', False)
       self.slow_mo = config.get('dev', {}).get('slow_mo', 50) if self.debug else 0
       self.timeout = 0 if self.debug else 60000

   async def initialize(self):
       """Initialize the browser and log in to services."""
       if self.initialized:
           return
       
       try:
           playwright = await async_playwright().start()
           self.browser = await playwright.chromium.launch(
               headless=not self.debug,
               slow_mo=self.slow_mo,
               args=GoogleAuth.get_browser_launch_options()["args"]
           )
           
           logger.info(f"Browser launched in {'debug' if self.debug else 'headless'} mode")
           
           # Initialize each service
           await self._initialize_service("claude", self.config["claude"])
           await self._initialize_service("chatgpt", self.config["chatgpt"])
           
           self.initialized = True
           logger.info("Bridge initialized successfully")
           
       except Exception as e:
           logger.error(f"Initialization error: {str(e)}")
           raise

   async def _initialize_service(self, service: str, config: dict):
       """Initialize a specific service using config."""
       context = None
       page = None
       try:
           auth_handler = self.claude_auth if service == "claude" else self.chatgpt_auth
           
           # Check if we need to perform Google login
           if config["auth_method"] == "google" and not auth_handler.is_session_valid():
               logger.info(f"No valid Google session found for {service}, performing login...")
               # We need to run this synchronously as the Google auth module uses sync API
               auth_handler.login(
                   email=config["email"],
                   password=config["password"],
                   headless=not self.debug
               )
               logger.info(f"Google login completed for {service}")

           # Create context with base configuration
           context = await self.browser.new_context(
               viewport={'width': 1920, 'height': 1080},
               user_agent=GoogleAuth.get_random_user_agent()
           )

           # Load Google auth state if using Google auth
           if config["auth_method"] == "google":
               storage_state = auth_handler.load_authentication_state()
               if storage_state:
                   await context.add_cookies(storage_state["cookies"])
                   for origin, state in storage_state.get("origins", {}).items():
                       await context.add_init_script(
                           f"window.localStorage.setItem('{origin}', '{state}')"
                       )

           # Create new page
           page = await context.new_page()
           
           if self.debug:
               # Setup debug listeners
               logger.debug(f"Setting up debug listeners for {service}")
               page.on("request", lambda request: logger.debug(f"Request: {request.method} {request.url}"))
               page.on("response", lambda response: logger.debug(f"Response: {response.status} {response.url}"))
               page.on("console", lambda msg: logger.debug(f"Browser console: {msg.text}"))

           if service == "claude":
               await self._login_claude(page, config)
               self.claude_context = context
               self.claude_page = page
           else:
               await self._login_chatgpt(page, config)
               self.chatgpt_context = context
               self.chatgpt_page = page
           
           logger.info(f"Successfully initialized {service} service")
           
       except Exception as e:
           logger.error(f"Failed to initialize {service}: {str(e)}")
           if context:
               try:
                   await context.close()
               except Exception as close_error:
                   logger.error(f"Error closing context during failure: {str(close_error)}")
           raise

   def _get_current_page(self) -> Page:
       """Get the appropriate page based on the current model."""
       if self.current_model and self.current_model.startswith(ModelProvider.ANTHROPIC):
           return self.claude_page
       return self.chatgpt_page

   async def _login_claude(self, page: Page, config: dict):
       """Handle Claude login."""
       try:
           if config["auth_method"] == "google":
               logger.info("Starting Claude Google login flow")
               await page.goto('https://claude.ai/login', wait_until='networkidle', timeout=self.timeout)
               
               # Click the Google sign-in button
               google_button = 'button:has-text("Continue with Google")'
               await page.click(google_button)
               
               # Handle the Google account chooser popup
               popup = await page.wait_for_event('popup')
               await popup.wait_for_load_state('networkidle')
               
               # Click on the first Google account
               account_button = popup.locator('div[role="link"]').first
               await account_button.click()
               
               # Wait for Continue button and click it
               continue_button = GoogleAuth.get_continue_button_selector()
               await popup.wait_for_selector(continue_button, state="visible", timeout=self.timeout)
               await popup.click(continue_button)
               
               # Wait for Claude to complete authentication
               await page.wait_for_url('https://claude.ai/chat', timeout=self.timeout)
               logger.info("Successfully logged into Claude with Google")
               
           else:
               logger.info("Starting direct Claude login")
               await page.goto('https://claude.ai/login', wait_until='networkidle', timeout=self.timeout)
               await page.fill('input[type="email"]', config["email"])
               await page.fill('input[type="password"]', config["password"])
               await page.click('button[type="submit"]')
               await page.wait_for_url('https://claude.ai/chat', timeout=self.timeout)
           
           logger.info("Logged into Claude")
           
       except Exception as e:
           logger.error(f"Claude login error: {str(e)}")
           if self.debug:
               await page.screenshot(path="error_claude_login.png")
               if 'popup' in locals() and not popup.is_closed():
                   await popup.screenshot(path="error_claude_popup.png")
           raise

   async def _login_chatgpt(self, page: Page, config: dict):
       """Handle ChatGPT login."""
       try:
           if config["auth_method"] == "google":
               logger.info("Starting ChatGPT Google login flow")
               await page.goto('https://chat.openai.com/auth/login', wait_until='networkidle', timeout=self.timeout)
               
               # Click the Google sign-in button
               google_button = 'button:has-text("Continue with Google")'
               await page.click(google_button)
               
               # Handle the Google account chooser popup
               popup = await page.wait_for_event('popup')
               await popup.wait_for_load_state('networkidle')
               
               # Click on the first Google account
               account_button = popup.locator('div[role="link"]').first
               await account_button.click()
               
               # Wait for Continue button and click it
               continue_button = GoogleAuth.get_continue_button_selector()
               await popup.wait_for_selector(continue_button, state="visible", timeout=self.timeout)
               await popup.click(continue_button)
               
               # Wait for ChatGPT to complete authentication
               await page.wait_for_url('https://chat.openai.com/', timeout=self.timeout)
               logger.info("Successfully logged into ChatGPT with Google")
               
           else:
               logger.info("Starting direct ChatGPT login")
               await page.goto('https://chat.openai.com/auth/login', wait_until='networkidle', timeout=self.timeout)
               await page.fill('input[type="email"]', config["email"])
               await page.fill('input[type="password"]', config["password"])
               await page.click('button[type="submit"]')
               await page.wait_for_url('https://chat.openai.com/', timeout=self.timeout)
           
           logger.info("Logged into ChatGPT")
           
       except Exception as e:
           logger.error(f"ChatGPT login error: {str(e)}")
           if self.debug:
               await page.screenshot(path="error_chatgpt_login.png")
               if 'popup' in locals() and not popup.is_closed():
                   await popup.screenshot(path="error_chatgpt_popup.png")
           raise

   async def select_model(self, model_id: str) -> bool:
       """Select the specified model in the web UI."""
       try:
           page = self._get_current_page()
           if not page:
               raise ValueError("No active page found")

           logger.debug(f"Selecting model: {model_id}")
           
           if model_id.startswith(ModelProvider.ANTHROPIC):
               if model_id not in CLAUDE_MODELS:
                   raise ValueError(f"Unsupported Claude model: {model_id}")
               
               select_button = 'button[aria-label="Select Model"]'
               await page.wait_for_selector(select_button, timeout=self.timeout)
               await page.click(select_button)
               await page.wait_for_selector(CLAUDE_MODELS[model_id]["selector"], timeout=self.timeout)
               await page.click(CLAUDE_MODELS[model_id]["selector"])
               self.current_model = model_id
               logger.info(f"Selected Claude model: {CLAUDE_MODELS[model_id]['display_name']}")
               
           elif model_id.startswith(ModelProvider.OPENAI):
               if model_id not in CHATGPT_MODELS:
                   raise ValueError(f"Unsupported ChatGPT model: {model_id}")
               
               select_button = 'button[aria-label="Model selector"]'
               await page.wait_for_selector(select_button, timeout=self.timeout)
               await page.click(select_button)
               await page.wait_for_selector(CHATGPT_MODELS[model_id]["selector"], timeout=self.timeout)
               await page.click(CHATGPT_MODELS[model_id]["selector"])
               self.current_model = model_id
               logger.info(f"Selected ChatGPT model: {CHATGPT_MODELS[model_id]['display_name']}")
               
           else:
               raise ValueError(f"Unknown model provider in model ID: {model_id}")
           
           return True
           
       except Exception as e:
           logger.error(f"Error selecting model {model_id}: {str(e)}")
           if self.debug:
               await page.screenshot(path=f"error_model_selection_{model_id.replace('/', '_')}.png")
           raise

   async def process_completion_request(self, model: str, messages: List[Dict[str, str]]) -> Tuple[str, bool]:
       """Process a completion request, returns (chat_url, is_new_chat)."""
       try:
           logger.debug(f"Processing completion request for model: {model}")
           self.current_model = model
           page = self._get_current_page()
           if not page:
               raise ValueError("No active page found")
           
           # Check for existing conversation
           existing_chat_url = await self.cache.find_matching_conversation(messages, model)
           
           if existing_chat_url:
               logger.debug(f"Found existing chat: {existing_chat_url}")
               # Use existing chat
               await page.goto(existing_chat_url, wait_until='networkidle', timeout=self.timeout)
               await self.select_model(model)  # Ensure correct model is selected
               return existing_chat_url, False
           else:
               logger.debug("Starting new chat")
               # Start new chat
               if model.startswith(ModelProvider.ANTHROPIC):
                   await page.goto('https://claude.ai/chat', wait_until='networkidle', timeout=self.timeout)
               else:
                   await page.goto('https://chat.openai.com/', wait_until='networkidle', timeout=self.timeout)
               
               await self.select_model(model)
               chat_url = page.url
               
               # Store the new conversation
               await self.cache.store_conversation(messages, model, chat_url)
               logger.debug(f"Created new chat: {chat_url}")
               return chat_url, True
               
       except Exception as e:
           logger.error(f"Error processing completion request: {str(e)}")
           if self.debug and page:
               await page.screenshot(path="error_completion_request.png")
           raise

   async def _send_single_message(self, message: str) -> str:
       """Send a single message and wait for response."""
       try:
           page = self._get_current_page()
           if not page:
               raise ValueError("No active page found")

           logger.debug(f"Sending message: {message[:50]}...")
           
           # Determine which service we're using based on the URL
           if 'claude.ai' in page.url:
               input_selector = 'textarea[placeholder="Message Claude..."]'
               response_selector = '.claude-response'
           else:
               input_selector = 'textarea[placeholder="Send a message"]'
               response_selector = '.markdown'
           
           await page.wait_for_selector(input_selector, timeout=self.timeout)
           await page.fill(input_selector, message)
           await page.keyboard.press('Enter')
           
           # Wait for response
           await page.wait_for_selector(response_selector, state='visible', timeout=self.timeout)
           
           # Get the latest response
           responses = await page.query_selector_all(response_selector)
           latest_response = responses[-1]
           response_text = await latest_response.text_content()
           
           logger.debug(f"Received response: {response_text[:50]}...")
           return response_text
           
       except Exception as e:
           logger.error(f"Error sending message: {str(e)}")
           if self.debug and page:
               await page.screenshot(path="error_send_message.png")
           raise

   async def send_message(self, message: str, is_new_chat: bool, chat_url: str, 
                         full_messages: List[Dict[str, str]] = None) -> str:
       """Send a message and handle the response."""
       try:
           if is_new_chat and full_messages:
               logger.debug("Sending previous messages for context")
               # Need to send all messages for context
               for msg in full_messages[:-1]:
                   if msg['role'] == 'user':
                       await self._send_single_message(msg['content'])
                       # Wait for response to complete
                       page = self._get_current_page()
                       await page.wait_for_selector('.response-complete-indicator', timeout=self.timeout)
           
           # Send the final/new message
           response_text = await self._send_single_message(message)
           
           # Update conversation cache
           await self.cache.update_conversation(
               chat_url,
               {'role': 'user', 'content': message},
               response_text
           )
           
           return response_text
           
       except Exception as e:
           logger.error(f"Error in send_message: {str(e)}")
           if self.debug:
               page = self._get_current_page()
               if page:
                   await page.screenshot(path="error_send_message_complete.png")
           raise

   async def stream_response(self, message: str, is_new_chat: bool, chat_url: str,
                           full_messages: List[Dict[str, str]] = None) -> AsyncGenerator[str, None]:
       """Stream the response for a message."""
       try:
           if is_new_chat and full_messages:
               logger.debug("Sending previous messages for context in streaming mode")
               # Send previous messages first
               for msg in full_messages[:-1]:
                   if msg['role'] == 'user':
                       await self._send_single_message(msg['content'])
                       page = self._get_current_page()
                       await page.wait_for_selector('.response-complete-indicator', timeout=self.timeout)
           
           logger.debug(f"Starting streaming response for message: {message[:50]}...")
           
           page = self._get_current_page()
           if not page:
               raise ValueError("No active page found")

           # Send the final message
           if 'claude.ai' in page.url:
               input_selector = 'textarea[placeholder="Message Claude..."]'
               response_selector = '.claude-response'
           else:
               input_selector = 'textarea[placeholder="Send a message"]'
               response_selector = '.markdown'
           
           await page.wait_for_selector(input_selector, timeout=self.timeout)
           await page.fill(input_selector, message)
           await page.keyboard.press('Enter')
           
           # Wait for response to start
           await page.wait_for_selector(response_selector, state='visible', timeout=self.timeout)
           
           # Get the latest response container
           responses = await page.query_selector_all(response_selector)
           latest_response = responses[-1]
           
           # Initialize previous content
           prev_content = ""
           response_complete = False
           complete_wait_count = 0
           max_complete_wait = 50  # 5 seconds total wait for completion
           
           logger.debug("Starting response streaming")
           while not response_complete and complete_wait_count < max_complete_wait:
               current_content = await latest_response.text_content()
               
               if current_content != prev_content:
                   # Reset wait count when content changes
                   complete_wait_count = 0
                   # Calculate the difference (new tokens)
                   new_content = current_content[len(prev_content):]
                   if new_content:
                       if self.debug:
                           logger.debug(f"Streaming chunk: {new_content[:50]}...")
                       yield new_content
                   prev_content = current_content
               
               # Check if response is complete
               done_indicator = await page.query_selector('.response-complete-indicator')
               if done_indicator:
                   response_complete = True
                   logger.debug("Response streaming completed")
               else:
                   complete_wait_count += 1
                   await asyncio.sleep(0.1)
           
           if complete_wait_count >= max_complete_wait:
               logger.warning("Response streaming timed out waiting for completion")
           
           # Update conversation cache with complete response
           await self.cache.update_conversation(
               chat_url,
               {'role': 'user', 'content': message},
               prev_content
           )
           
       except Exception as e:
           logger.error(f"Error in stream_response: {str(e)}")
           if self.debug:
               page = self._get_current_page()
               if page:
                   await page.screenshot(path="error_stream_response.png")
           raise

   async def cleanup(self):
       """Cleanup resources."""
       try:
           logger.info("Cleaning up browser resources")
           if self.claude_context:
               await self.claude_context.close()
           if self.chatgpt_context:
               await self.chatgpt_context.close()
           if self.browser:
               await self.browser.close()
           logger.info("Browser cleanup completed")
       except Exception as e:
           logger.error(f"Error during browser cleanup: {str(e)}")

   async def __aenter__(self):
       """Async context manager enter."""
       await self.initialize()
       return self

   async def __aexit__(self, exc_type, exc_val, exc_tb):
       """Async context manager exit."""
       await self.cleanup()