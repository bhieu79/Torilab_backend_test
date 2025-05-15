from datetime import datetime, time
from enum import Enum
import logging
from typing import Optional, Union, Dict

logger = logging.getLogger("app")

class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    SYSTEM = "system"
    HEARTBEAT = "heartbeat"

class Message:
    def __init__(
        self,
        client_id: str,
        content: str,
        message_type: MessageType,
        client_timestamp: datetime,
        timezone: str,
        filename: Optional[str] = None,
        binary_content: Optional[bytes] = None,
        is_accepted: bool = True,
        status_message: Optional[str] = None,
        is_system: bool = False
    ):
        self.client_id = client_id
        self.content = content
        self.message_type = message_type
        self.client_timestamp = client_timestamp
        self.timezone = timezone
        self.filename = filename
        self.binary_content = binary_content  # Store binary data separately
        self.is_accepted = is_accepted
        self.status_message = status_message
        self.is_system = is_system

def _is_time_allowed(current_time: datetime, message_type: MessageType, timezone: str) -> tuple[bool, str]:
    """
    Check if the message type is allowed at the current time based on the provided timezone.
    Returns (is_allowed, rejection_message)
    """
    try:
        # Convert to user's timezone using the provided timezone string
        from zoneinfo import ZoneInfo
        local_time = current_time.astimezone(ZoneInfo(timezone))
        current_hour = local_time.hour
    except Exception as e:
        logger.error(f"Error processing timezone {timezone}: {str(e)}")
        # Fallback to UTC in case of timezone errors
        local_time = current_time.astimezone()
        current_hour = local_time.hour

    if message_type == MessageType.TEXT:
        # Text chat: 5 AM - midnight
        if 5 <= current_hour < 24:
            return True, ""
        return False, "Text messages are only accepted between 5 AM and midnight"
    
    elif message_type == MessageType.VOICE:
        # Voice chat: 8 AM - 12 PM (noon)
        if 8 <= current_hour < 12:
            return True, ""
        return False, "Voice messages are only accepted between 8 AM and 12 PM"
    
    elif message_type == MessageType.VIDEO:
        # Video chat: 8 PM - midnight
        if 20 <= current_hour < 24:
            return True, ""
        return False, "Video messages are only accepted between 8 PM and midnight"
    
    return True, ""  # Allow other message types at any time

async def validate_message(message_data: Dict, client_id: str, timezone: str) -> Message:
    """Validate and create a Message instance from raw message data"""
    
    # Handle system messages (like initial connection or heartbeat)
    message_type_str = message_data.get("type") or message_data.get("message_type", "text")
    logger.debug(f"Validating message type: {message_type_str}")
    
    if message_type_str in ["system", "heartbeat"] or message_data.get("is_system"):
        return Message(
            client_id=client_id,
            content=message_data.get("content", ""),
            message_type=MessageType.SYSTEM,
            client_timestamp=datetime.now(),
            timezone=timezone,
            is_system=True
        )

    # For regular messages, ensure message_type is present
    if "message_type" not in message_data and message_type_str not in [t.value for t in MessageType]:
        logger.debug(f"Message validation failed: Message type is required. Got: {message_data}")
        raise ValueError("Message type is required")

    try:
        message_type = MessageType(message_type_str)
    except ValueError:
        logger.error(f"Invalid message type: {message_type_str}")
        raise ValueError(f"Invalid message type: {message_type_str}")

    # Get content and filename
    content = message_data.get("content", "")
    filename = message_data.get("filename")

    # Validate content based on message type
    if message_type in [MessageType.IMAGE, MessageType.VIDEO, MessageType.VOICE] and not filename:
        raise ValueError(f"Filename is required for {message_type} messages")

    if not content and not filename:
        raise ValueError("Message content cannot be empty")

    # Get timestamp
    timestamp = message_data.get("timestamp")
    try:
        if timestamp and isinstance(timestamp, str):
            # Handle ISO format with optional Z or timezone
            if timestamp.endswith('Z'):
                timestamp = timestamp[:-1] + '+00:00'
            client_timestamp = datetime.fromisoformat(timestamp)
        else:
            client_timestamp = datetime.now()
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid timestamp format: {timestamp}, using current time. Error: {str(e)}")
        client_timestamp = datetime.now()

    # Handle binary content for media types
    binary_content = None
    if message_type in [MessageType.IMAGE, MessageType.VIDEO, MessageType.VOICE]:
        binary_content = content
        content = ""  # Clear the content field for media types
    
    # Check time-based restrictions
    is_allowed, rejection_message = _is_time_allowed(client_timestamp, message_type, timezone)
    logger.debug(f"Time validation for {message_type}: allowed={is_allowed}, message={rejection_message}")
    
    return Message(
        client_id=client_id,
        content=content,
        message_type=message_type,
        client_timestamp=client_timestamp,
        timezone=timezone,
        filename=filename,
        binary_content=binary_content,
        is_accepted=is_allowed,
        status_message=rejection_message if not is_allowed else None,
        is_system=message_data.get("is_system", False)
    )