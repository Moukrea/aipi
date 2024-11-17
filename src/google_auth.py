from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import json
import os
from random import choice, uniform
import asyncio
from dotenv import load_dotenv
import yaml
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class GoogleAuth:
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.session_file = f'google_auth_{service_name.lower()}.json'
        self.screenshot_dir = 'error_screenshots'
        os.makedirs(self.screenshot_dir, exist_ok=True)

    @staticmethod
    def get_random_user_agent():
        """Return a random modern browser user agent."""
        user_agents = [
            # Chrome on Windows 11
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Chrome on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Chrome on Linux
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        return choice(user_agents)

    @staticmethod
    def get_browser_launch_options():
        """Return dictionary of browser launch options."""
        return {
            "args": [
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
                '--no-first-run',
                '--no-sandbox',
                '--no-zygote',
                '--ignore-certificate-errors',
                '--disable-extensions',
                '--disable-infobars',
                '--disable-notifications',
                '--disable-popup-blocking',
                '--remote-debugging-port=9222',
                '--disable-blink-features=AutomationControlled'
            ]
        }

    @staticmethod
    def get_next_button_selector():
        """Return a selector that works for 'Next' button in multiple languages."""
        next_button_translations = [
            "Next",        # English
            "Suivant",     # French
            "Próximo",     # Portuguese
            "Siguiente",   # Spanish
            "Weiter",      # German
            "Dalej",       # Polish
            "다음",        # Korean
            "次へ",        # Japanese
            "下一步",      # Chinese Simplified
            "Далее",       # Russian
            "Volgende",    # Dutch
            "Nästa",       # Swedish
            "Avanti",      # Italian
            "İleri",       # Turkish
            "Tiếp theo",   # Vietnamese
            "ถัดไป",       # Thai
            "التالي",      # Arabic
            "הבא",        # Hebrew
            "Berikutnya"   # Indonesian
        ]
        
        text_selectors = [f'button:has-text("{text}")' for text in next_button_translations]
        text_selectors.append('button[jsname="LgbsSe"]')
        return ', '.join(text_selectors)

    @staticmethod
    def get_continue_button_selector():
        """Return a selector that works for 'Continue' button in multiple languages."""
        continue_button_translations = [
            "Continue",    # English
            "Continuer",   # French
            "Continuar",   # Spanish/Portuguese
            "Weiter",      # German
            "Dalej",       # Polish
            "계속",        # Korean
            "続行",        # Japanese
            "继续",        # Chinese Simplified
            "Продолжить",  # Russian
            "Doorgaan",    # Dutch
            "Fortsätt",    # Swedish
            "Continua",    # Italian
            "Devam",       # Turkish
            "Tiếp tục",    # Vietnamese
            "ดำเนินการต่อ",  # Thai
            "متابعة",      # Arabic
            "המשך",        # Hebrew
            "Lanjutkan"    # Indonesian
        ]
        
        text_selectors = [f'button:has-text("{text}")' for text in continue_button_translations]
        text_selectors.append('div[role="button"][jsname="LgbsSe"]')
        return ', '.join(text_selectors)

    def save_authentication_state(self, storage_state: Dict):
        """Save the authentication state to a file."""
        with open(self.session_file, 'w') as f:
            json.dump(storage_state, f)

    def load_authentication_state(self):
        """Load the authentication state from a file."""
        if os.path.exists(self.session_file):
            with open(self.session_file, 'r') as f:
                return json.load(f)
        return None

    def is_session_valid(self) -> bool:
        """Check if the session file exists and is not empty/corrupted."""
        if not os.path.exists(self.session_file):
            return False
        try:
            with open(self.session_file, 'r') as f:
                session_data = json.load(f)
                return isinstance(session_data, dict) and 'cookies' in session_data
        except (json.JSONDecodeError, IOError):
            return False
        return True

    async def type_with_delay(self, page: Page, selector: str, text: str, min_delay: float = 0.1, max_delay: float = 0.3):
        """Type text with random delays between keystrokes."""
        await page.fill(selector, "")
        for character in text:
            await page.type(selector, character)
            await asyncio.sleep(uniform(min_delay, max_delay))

    async def login(self, email: str, password: str, headless: bool = False):
        """Login to Google and save the authentication state."""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=headless,
            **self.get_browser_launch_options()
        )
        
        context = await browser.new_context(
            user_agent=self.get_random_user_agent(),
            viewport={'width': 1920, 'height': 1080}
        )
        
        await context.grant_permissions(['geolocation'])
        page = await context.new_page()
        await page.set_default_timeout(30000)
        await page.set_default_navigation_timeout(30000)
        
        try:
            # Navigate to login page and wait for it to load
            logger.info("Navigating to login page...")
            await page.goto('https://accounts.google.com', wait_until='networkidle')
            
            # Step 1: Type email and click next
            logger.info("Entering email...")
            await page.wait_for_selector('input[type="email"]', state="visible")
            await self.type_with_delay(page, 'input[type="email"]', email)
            await asyncio.sleep(1)
            
            # Click the first Next button
            logger.info("Clicking next after email...")
            next_button = self.get_next_button_selector()
            await page.wait_for_selector(next_button, state="visible")
            await page.click(next_button)
            
            # Step 2: Type password and click next
            logger.info("Waiting for password field...")
            await page.wait_for_selector('input[type="password"]', state="visible")
            logger.info("Entering password...")
            await self.type_with_delay(page, 'input[type="password"]', password)
            await asyncio.sleep(1)
            
            # Click the second Next button
            logger.info("Clicking next after password...")
            await page.wait_for_selector(next_button, state="visible")
            await page.click(next_button)
            
            # Wait for successful login
            logger.info("Waiting for login completion...")
            await page.wait_for_url('https://myaccount.google.com/**', timeout=60000)
            logger.info("Successfully logged in!")
            
            # Save authentication state
            storage_state = await context.storage_state()
            self.save_authentication_state(storage_state)
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            await page.screenshot(path=os.path.join(self.screenshot_dir, f"login_error_{self.service_name}.png"))
            raise
        finally:
            await browser.close()
            await playwright.stop()