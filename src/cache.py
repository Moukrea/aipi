import sqlite3
import aiosqlite
from datetime import datetime, timedelta
import hashlib
from typing import List, Dict, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)

class ConversationCache:
    def __init__(self, db_path: str, cleanup_interval: int = 3600, max_age: int = 86400):
        self.db_path = db_path
        self.cleanup_interval = cleanup_interval
        self.max_age = max_age
        self.cleanup_task = None
        self.init_db()

    async def start_cleanup(self):
        """Start the cleanup task - should be called after event loop is running"""
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup())

    def init_db(self):
        """Initialize SQLite database with required tables."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_hash TEXT PRIMARY KEY,
                web_chat_url TEXT,
                model TEXT,
                last_used TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_hash TEXT,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_hash) REFERENCES conversations (conversation_hash)
            )
        ''')
        
        conn.commit()
        conn.close()

    def generate_conversation_hash(self, messages: List[Dict[str, str]], model: str) -> str:
        """Generate a unique hash for a conversation based on messages and model."""
        conversation_str = f"{model}:"
        for msg in messages:
            conversation_str += f"{msg['role']}:{msg['content']};"
        return hashlib.sha256(conversation_str.encode()).hexdigest()

    async def find_matching_conversation(self, messages: List[Dict[str, str]], model: str) -> Optional[str]:
        """Find an existing conversation URL that matches the message history."""
        if not messages[:-1]:  # No previous messages
            return None
            
        conversation_hash = self.generate_conversation_hash(messages[:-1], model)
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT web_chat_url FROM conversations WHERE conversation_hash = ?",
                (conversation_hash,)
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None

    async def store_conversation(self, messages: List[Dict[str, str]], model: str, web_chat_url: str):
        """Store a new conversation and its messages."""
        conversation_hash = self.generate_conversation_hash(messages, model)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO conversations (conversation_hash, web_chat_url, model, last_used)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (conversation_hash, web_chat_url, model)
            )
            
            for msg in messages:
                await db.execute(
                    """
                    INSERT INTO messages (conversation_hash, role, content)
                    VALUES (?, ?, ?)
                    """,
                    (conversation_hash, msg['role'], msg['content'])
                )
            
            await db.commit()

    async def update_conversation(self, web_chat_url: str, new_message: Dict[str, str], response_content: str):
        """Update existing conversation with new message and response."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE conversations SET last_used = CURRENT_TIMESTAMP WHERE web_chat_url = ?",
                (web_chat_url,)
            )
            
            async with db.execute(
                "SELECT conversation_hash FROM conversations WHERE web_chat_url = ?",
                (web_chat_url,)
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    return
                
                conversation_hash = result[0]
            
            await db.execute(
                "INSERT INTO messages (conversation_hash, role, content) VALUES (?, ?, ?)",
                (conversation_hash, new_message['role'], new_message['content'])
            )
            await db.execute(
                "INSERT INTO messages (conversation_hash, role, content) VALUES (?, ?, ?)",
                (conversation_hash, 'assistant', response_content)
            )
            
            await db.commit()

    async def _periodic_cleanup(self):
        """Periodically remove old conversations."""
        while True:
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    cutoff_time = datetime.now() - timedelta(seconds=self.max_age)
                    
                    # Get old conversation hashes
                    async with db.execute(
                        "SELECT conversation_hash FROM conversations WHERE last_used < ?",
                        (cutoff_time.isoformat(),)
                    ) as cursor:
                        old_conversations = await cursor.fetchall()
                    
                    for (conv_hash,) in old_conversations:
                        # Delete messages first (foreign key constraint)
                        await db.execute(
                            "DELETE FROM messages WHERE conversation_hash = ?",
                            (conv_hash,)
                        )
                        # Delete conversation
                        await db.execute(
                            "DELETE FROM conversations WHERE conversation_hash = ?",
                            (conv_hash,)
                        )
                    
                    await db.commit()
                    
                    if old_conversations:
                        logger.info(f"Cleaned up {len(old_conversations)} old conversations")
                
            except Exception as e:
                logger.error(f"Error during conversation cleanup: {str(e)}")
            
            await asyncio.sleep(self.cleanup_interval)
