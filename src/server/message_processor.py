import logging
import json
import random
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from .message_validator import Message, MessageType
from .database import DatabaseManager
from .openai_client import OpenAIClient
from .media_handler import MediaHandler
# ReplyDispatcher might not be directly used here if we construct replies directly
# from .reply_dispatcher import ReplyDispatcher

logger = logging.getLogger("app")

class MessageProcessor:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.openai_client = OpenAIClient()
        self.media_handler = MediaHandler()
        self.processing_count = 0

    async def process_message(self, message: Message) -> List[Dict[str, Any]]:
        """Process an incoming message and generate appropriate replies based on type."""
        try:
            # Check if message is allowed based on time restrictions
            if not message.is_accepted:
                return [{
                    "type": "message",
                    "data": {"message": message.status_message, "reply_type": "text"}
                }]

            # Initialize content variable for database storage
            content_to_save = message.content

            # Handle media content if present
            if message.message_type in [MessageType.IMAGE, MessageType.VIDEO, MessageType.VOICE]:
                if not message.filename:
                    raise ValueError(f"Filename is required for {message.message_type.value} message")
                if not message.binary_content:
                    raise ValueError(f"Binary content is required for {message.message_type.value} message")
                
                media_path = await self.media_handler.save_media(
                    content=message.binary_content,
                    media_type=message.message_type.value,
                    filename=message.filename
                )
                if not media_path:
                    raise ValueError(f"Failed to save {message.message_type.value} file")
                content_to_save = media_path

            # Save message with appropriate content
            message_id = await self.db.save_message(
                client_id=message.client_id,
                message_type=message.message_type.value,
                content=content_to_save,  # Will be file path for media or text for text messages
                client_timestamp=message.client_timestamp,
                timezone=message.timezone,
                is_accepted=message.is_accepted,
                status_message=message.status_message or "Message accepted"
            )
            
            self.processing_count += 1
            replies = []
            rate_limit_status = self.openai_client.get_rate_limit_status()

            # Determine response time based on message type
            if message.message_type == MessageType.TEXT:
                await asyncio.sleep(random.uniform(0, 1))
            elif message.message_type == MessageType.VOICE:
                await asyncio.sleep(random.uniform(1, 2))
            elif message.message_type in [MessageType.VIDEO, MessageType.IMAGE]:
                await asyncio.sleep(random.uniform(2, 3))

            if rate_limit_status["rate_limited"]:
                minutes_remaining = int(rate_limit_status["time_remaining"] / 60) + 1
                text_reply_content = f"System is currently busy. Please try again in {minutes_remaining} minutes. (Original message: {message.content[:30]}...)"
                
                reply_id = await self.db.save_reply(
                    message_id=message_id,
                    content=text_reply_content,
                    reply_type="text"
                )
                replies.append({
                    "type": "message",
                    "data": {
                        "id": reply_id,
                        "content": text_reply_content,
                        "reply_type": "text"
                    }
                })
            else:
                # Generate text reply using OpenAI
                try:
                    # Only use GPT-4o-mini for text messages
                    if message.message_type == MessageType.TEXT:
                        prompt = (
                            "You are a friendly chat assistant. "
                            "Please provide a natural and helpful response: "
                            f"\"{message.content}\""
                        )
                        text_reply_content = await self.openai_client.get_chat_response(prompt)
                    else:
                        # For voice and video messages, use a standard response
                        text_reply_content = f"Received your {message.message_type.value} message"
                    if not text_reply_content: # Fallback if OpenAI returns empty
                        text_reply_content = f"Received your {message.message_type.value} message: \"{message.content[:50]}...\""
                except Exception as openai_error:
                    logger.error(f"OpenAI API error: {openai_error}")
                    # Fallback generic message if OpenAI fails
                    text_reply_content = f"Sorry, I couldn't process your request at the moment. (Received: {message.content[:30]}...)"

                # Save and prepare text reply
                text_reply_id = await self.db.save_reply(
                    message_id=message_id,
                    content=text_reply_content,
                    reply_type="text"
                )
                replies.append({
                    "type": "message",
                    "data": {
                        "id": text_reply_id,
                        "content": text_reply_content,
                        "reply_type": "text"
                    }
                })

                # Handle additional replies based on message type
                # Add media replies based on message type
                if message.message_type in [MessageType.VOICE, MessageType.VIDEO, MessageType.IMAGE]:
                    # Media reply options
                    media_replies = {
                        'voice': {
                            'url': '/media/static_replies/reply.mp3',
                            'type': 'voice',
                            'mime': 'audio/mpeg',
                            'filename': 'reply.mp3'
                        },
                        'image': {
                            'url': '/media/static_replies/reply.png',
                            'type': 'image',
                            'mime': 'image/png',
                            'filename': 'reply.png'
                        }
                    }

                    # Add voice reply
                    reply = media_replies['voice']
                    voice_reply_id = await self.db.save_reply(
                        message_id=message_id,
                        content=reply['url'],
                        reply_type=reply['type']
                    )
                    replies.append({
                        "type": "message",
                        "data": {
                            "id": voice_reply_id,
                            "content": reply['url'],
                            "reply_type": reply['type'],
                            "filename": reply['filename'],
                            "mime_type": reply['mime']
                        }
                    })

                    # Add image reply for video/image messages
                    if message.message_type in [MessageType.VIDEO, MessageType.IMAGE]:
                        reply = media_replies['image']
                        image_reply_id = await self.db.save_reply(
                            message_id=message_id,
                            content=reply['url'],
                            reply_type=reply['type']
                        )
                        replies.append({
                            "type": "message",
                            "data": {
                                "id": image_reply_id,
                                "content": reply['url'],
                                "reply_type": reply['type'],
                                "filename": reply['filename'],
                                "mime_type": reply['mime']
                            }
                        })
            
            return replies

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return [{
                "type": "message",
                "data": {"message": f"Error processing message: {str(e)}", "reply_type": "text"}
            }]