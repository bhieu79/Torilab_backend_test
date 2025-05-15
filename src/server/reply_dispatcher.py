import asyncio
import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger("my_logger")

class ReplyDispatcher:
    def __init__(self, db_manager):
        self.clients = {}  # client_id -> writer
        self.db = db_manager

    def register_client(self, client_id: str, writer: asyncio.StreamWriter):
        """Register a client for receiving replies"""
        self.clients[client_id] = writer
        logger.info(f"Client registered: {client_id}")

    def unregister_client(self, client_id: str):
        """Unregister a client"""
        if client_id in self.clients:
            del self.clients[client_id]
            logger.info(f"Client unregistered: {client_id}")

    async def send_error(self, client_id: str, error_message: str):
        """Send an error message to a client"""
        response = {
            "type": "error",
            "data": {
                "message": error_message
            }
        }
        await self._send_to_client(client_id, response)
        logger.error(f"Error sent to client {client_id}: {error_message}")

    async def send_replies(self, client_id: str, replies: List[Dict[str, Any]]):
        """Send replies to a client"""
        try:
            for reply in replies:
                response = {
                    "type": "reply",
                    "data": reply
                }
                
                success = await self._send_to_client(client_id, response)
                if success:
                    # Mark reply as delivered in database if applicable
                    if reply.get("id"):
                        await self.db.mark_reply_delivered(reply["id"])
                        logger.debug(f"Reply {reply['id']} marked as delivered")
                else:
                    logger.error(f"Failed to send reply to client {client_id}")

        except Exception as e:
            logger.error(f"Error sending replies to client {client_id}: {str(e)}")
            await self.send_error(client_id, "Internal server error")

    async def _send_to_client(self, client_id: str, message: dict) -> bool:
        """Send a message to a specific client. Returns True if successful."""
        try:
            if client_id not in self.clients:
                logger.error(f"Client {client_id} not found")
                return False
                
            writer = self.clients[client_id]
            if writer.is_closing():
                logger.error(f"Connection to client {client_id} is closing")
                return False

            # Send message
            content = json.dumps(message)
            writer.write(content.encode() + b'\n')
            await writer.drain()
            
            logger.debug(f"Message sent to client {client_id}: {content}")
            return True

        except ConnectionError as e:
            logger.error(f"Connection error sending to client {client_id}: {str(e)}")
            self.unregister_client(client_id)
            return False

        except Exception as e:
            logger.error(f"Error sending to client {client_id}: {str(e)}")
            return False