import logging
from .logging_config import logging_setup

# Initialize logging
logger = logging_setup()
from datetime import datetime
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .models import Message, MessageType
from .message_processor import MessageProcessor
from .database import DatabaseManager
from .connection_manager import ConnectionManager
from .message_validator import validate_message

# Setup logging
logger = logging.getLogger("app")

app = FastAPI()
db = DatabaseManager()
message_processor = MessageProcessor(db)
connection_manager = ConnectionManager()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount media directories for serving files
# app.mount("/media/images", StaticFiles(directory="media/images"), name="media_images")
# app.mount("/media/videos", StaticFiles(directory="media/videos"), name="media_videos")
# app.mount("/media/voices", StaticFiles(directory="media/voices"), name="media_voices")
app.mount("/media", StaticFiles(directory="media"), name="media")
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_id = None
    
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    try:
        # Get initial connection message with client ID
        data = await websocket.receive_json()
        client_id = data.get("client_id")
        client_timezone = data.get("timezone", "UTC")
        
        if not client_id:
            await websocket.send_json({
                "type": "error",
                "data": {"message": "Client ID required"}
            })
            await websocket.close(code=1008)
            return
            
        logger.info(f"Client {client_id} identified")
        
        # Add client to database and connection manager
        await db.add_or_update_client(client_id, client_timezone)
        if not await connection_manager.connect(websocket, client_id, client_timezone):
            return  # Connection rejected due to max clients
        
        # Send connection confirmation and start heartbeat
        try:
            # Check if connection is still open before sending confirmation
            if websocket.client_state.CONNECTED:
                await websocket.send_json({
                    "type": "system",
                    "data": {"message": "Connected successfully"},
                    "is_system": True
                })
            else:
                logger.info(f"Client {client_id} connection closed before confirmation could be sent")
                return

            # Then start heartbeat
            await connection_manager.start_heartbeat(client_id)
        except WebSocketDisconnect:
            logger.info(f"Client {client_id} disconnected during initial setup")
            return
        except Exception as e:
            if "code 1000" in str(e) or "Normal closure" in str(e):
                logger.info(f"Client {client_id} closed connection normally during initial setup")
            else:
                logger.error(f"Error during initial setup for client {client_id}: {str(e)}")
            return
        
        try:
            while True:
                # Receive message - could be JSON or binary
                try:
                    message_data = await websocket.receive_json()
                    is_binary = False
                except ValueError:
                    # If not JSON, try to receive as binary
                    binary_data = await websocket.receive_bytes()
                    is_binary = True
                    message_data = await websocket.receive_json()  # Expect metadata after binary
                    message_data['binary_content'] = binary_data
                
                # Handle heartbeat messages
                if message_data.get("type") == "heartbeat":
                    message = message_data.get("data", {}).get("message")
                    if message == "pong":
                        # Update last heartbeat time when we receive pong
                        await connection_manager.heartbeat(client_id)
                    continue
                
                # Add message type if not present (default to text)
                if "message_type" not in message_data:
                    message_data["message_type"] = "text"
                
                # Skip system messages
                if message_data.get("is_system"):
                    continue

                # Check if client can send message
                if not await connection_manager.start_sending(client_id):
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": "Too many clients sending messages simultaneously (max 50). Please try again later."}
                    })
                    continue

                try:
                    # Validate message format
                    try:
                        message = await validate_message(message_data, client_id, client_timezone)
                    except ValueError as e:
                        await websocket.send_json({
                            "type": "error",
                            "data": {"message": str(e)}
                        })
                        continue

                    # Check if can process another message
                    if not await connection_manager.increment_processing():
                        await websocket.send_json({
                            "type": "error",
                            "data": {"message": "Server at maximum message processing capacity (500). Please try again later."}
                        })
                        continue

                    try:
                        # Process message and get replies
                        replies = await message_processor.process_message(message)
                        for reply in replies:
                            try:
                                await websocket.send_json(reply)
                            except WebSocketDisconnect:
                                logger.warning(f"Client {client_id} disconnected during reply")
                                raise
                            except Exception as e:
                                logger.error(f"Error sending reply to {client_id}: {str(e)}")
                                # Any WebSocket closure is treated as a disconnect
                                if "code 1000" in str(e) or "connection" in str(e).lower():
                                    raise WebSocketDisconnect()
                                # For other errors, continue trying to send remaining replies
                                continue
                    except Exception as e:
                        print(e)
                        logger.error(f"Error processing message: {str(e)}")
                        await websocket.send_json({
                            "type": "error",
                            "data": {"message": "Error processing message"}
                        })
                    finally:
                        await connection_manager.decrement_processing()
                finally:
                    await connection_manager.stop_sending(client_id)

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected by client {client_id}")
        except Exception as e:
            logger.error(f"Error in websocket connection for client {client_id}: {str(e)}")
            
    except Exception as e:
        logger.error(f"Unhandled WebSocket error: {str(e)}", exc_info=True)
        
    finally:
        if client_id:
            await connection_manager.disconnect(client_id)
            logger.info(f"Client {client_id} disconnected and removed from active connections")

@app.get("/chat-history/{client_id}")
async def get_chat_history(client_id: str, limit: int = 50, offset: int = 0):
    """Get chat history for a client with pagination"""
    try:
        limit = min(max(1, limit), 100)  # Limit between 1 and 100
        offset = max(0, offset)  # Ensure non-negative offset
        
        # Get total count of messages for this client
        total_count = await db.get_client_message_count(client_id)
        
        # Get paginated history
        history = await db.get_chat_history(client_id, limit, offset)
        
        return {
            "status": "success",
            "data": history,
            "pagination": {
                "total": total_count,
                "offset": offset,
                "limit": limit,
                "has_more": offset + limit < total_count
            }
        }
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        return {"status": "error", "message": "Failed to retrieve chat history"}

@app.get("/health")
async def health_check():
    """Server health check endpoint"""
    return {
        "status": "healthy",
        "active_connections": connection_manager.get_active_connections(),
        "currently_sending": len(connection_manager.sending_clients),
        "messages_processing": connection_manager.messages_processing,
        "max_sending": connection_manager.MAX_SENDING,
        "max_processing": connection_manager.MAX_PROCESSING
    }