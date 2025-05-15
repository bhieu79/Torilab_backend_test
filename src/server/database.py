import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime
import os
from dotenv import load_dotenv
from .models import Message, Reply, Client  # Import all required models

# Load environment variables
load_dotenv()

logger = logging.getLogger("app")

class DatabaseManager:
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv("DATABASE_URL", "sqlite+aiosqlite:///chat_server.db")
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            connect_args={
                "timeout": 30,
                "check_same_thread": False,
                "isolation_level": "IMMEDIATE"
            }
        )
        self._session_factory = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def get_client_message_count(self, client_id: str) -> int:
        """Get total message count for a specific client"""
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(func.count())
                    .select_from(Message)
                    .where(Message.client_id == client_id)
                )
                return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error getting message count for client {client_id}: {str(e)}")
            return 0

    async def add_or_update_client(self, client_id: str, timezone: str = "UTC"):
        """Add or update a client record"""
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    client = await session.get(Client, client_id)
                    if client:
                        client.timezone = timezone
                    else:
                        client = Client(client_id=client_id, timezone=timezone)
                        session.add(client)
        except Exception as e:
            logger.error(f"Error adding/updating client {client_id}: {str(e)}")
            raise

    async def save_message(self, content: str, message_type: str, client_id: str, client_timestamp: datetime,
                         timezone: str = "UTC", is_accepted: bool = True, status_message: str = None) -> int:
        """Save a message to the database and return its ID"""
        last_error = None
        retries = 3

        for attempt in range(retries):
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        message = Message(
                            client_id=client_id,
                            content=content,
                            message_type=message_type,
                            client_timestamp=client_timestamp,
                            timezone=timezone,
                            is_accepted=is_accepted,
                            status_message=status_message
                        )
                        session.add(message)
                        await session.flush()
                        return message.id
            except Exception as e:
                last_error = e
                if "database is locked" in str(e):
                    if attempt < retries - 1:
                        await asyncio.sleep(0.1 * (attempt + 1))
                        continue
                else:
                    break

        logger.error(f"Error saving message after {retries} attempts: {str(last_error)}")
        raise last_error

    async def save_reply(self, message_id: int, content: str, reply_type: str) -> int:
        """Save a reply to the database"""
        last_error = None
        retries = 3

        for attempt in range(retries):
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        reply = Reply(
                            message_id=message_id,
                            content=content,
                            reply_type=reply_type,
                            is_delivered=True
                        )
                        session.add(reply)
                        await session.flush()
                        return reply.id
            except Exception as e:
                last_error = e
                if "database is locked" in str(e):
                    if attempt < retries - 1:
                        await asyncio.sleep(0.1 * (attempt + 1))
                        continue
                else:
                    break

        logger.error(f"Error saving reply after {retries} attempts: {str(last_error)}")
        raise last_error

    async def get_chat_history(self, client_id: str, limit: int = 50, offset: int = 0):
        """Get chat history for a client including replies"""
        try:
            async with self._session_factory() as session:
                query = (
                    select(Message)
                    .options(selectinload(Message.replies))
                    .where(Message.client_id == client_id)
                    .order_by(Message.client_timestamp.desc())
                    .limit(limit)
                    .offset(offset)
                )
                
                result = await session.execute(query)
                messages_with_replies = result.scalars().all()
                
                messages = []
                for message in messages_with_replies:
                    message_dict = {
                        "id": message.id,
                        "client_id": message.client_id,
                        "content": message.content,
                        "message_type": message.message_type,
                        "timezone": message.timezone,
                        "is_accepted": message.is_accepted,
                        "status_message": message.status_message,
                        "replies": []
                    }
                    
                    # Format timestamp
                    try:
                        if isinstance(message.client_timestamp, str):
                            timestamp = datetime.fromisoformat(message.client_timestamp.replace('Z', '+00:00'))
                        else:
                            timestamp = message.client_timestamp
                        message_dict["client_timestamp"] = timestamp.isoformat()
                    except Exception as e:
                        logger.error(f"Error formatting timestamp: {str(e)}")
                        message_dict["client_timestamp"] = datetime.now().isoformat()
                    
                    # Convert replies to dict
                    for reply in message.replies:
                        message_dict["replies"].append({
                            "id": reply.id,
                            "content": reply.content,
                            "reply_type": reply.reply_type,
                            "is_delivered": reply.is_delivered
                        })
                    
                    messages.append(message_dict)
                
                return messages
                
        except Exception as e:
            logger.error(f"Error getting chat history for {client_id}: {str(e)}")
            return []
