import logging
import asyncio
from typing import Dict
from fastapi import WebSocket
from datetime import datetime, timedelta

logger = logging.getLogger("my_logger")

# Constants for heartbeat configuration
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 60  # seconds

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.client_timezones: Dict[str, str] = {}
        self.sending_clients: set = set()  # Clients currently sending messages
        self.messages_processing: int = 0  # Number of messages currently processing
        self.MAX_SENDING = 50  # Max clients that can send simultaneously
        self.MAX_PROCESSING = 500  # Max messages that can be processed simultaneously
        self.last_heartbeat: Dict[str, datetime] = {}  # Track last heartbeat for each client
        self.heartbeat_task = None

    async def connect(self, websocket: WebSocket, client_id: str, client_timezone: str = "UTC"):
        """Connect a new client"""
        self.active_connections[client_id] = websocket
        self.client_timezones[client_id] = client_timezone
        logger.info(f"Client {client_id} connected. Active clients: {len(self.active_connections)}")
        return True

    async def start_heartbeat(self, client_id: str):
        """Start heartbeat monitoring for a connected client"""
        self.last_heartbeat[client_id] = datetime.now()
        
        # Start heartbeat task if not already running
        if not self.heartbeat_task or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def disconnect(self, client_id: str):
        """Disconnect a client and cleanup resources"""
        # Remove from tracking collections first
        if client_id in self.sending_clients:
            self.sending_clients.remove(client_id)
        if client_id in self.client_timezones:
            del self.client_timezones[client_id]
        if client_id in self.last_heartbeat:
            del self.last_heartbeat[client_id]
            
        # Handle WebSocket cleanup last
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            del self.active_connections[client_id]  # Remove from active connections first
            
            try:
                await websocket.close(code=1000)
            except Exception as e:
                if "already closed" not in str(e).lower() and "unexpected asgi message" not in str(e).lower():
                    logger.error(f"Error during connection cleanup for {client_id}: {str(e)}")
            
        logger.info(f"Client {client_id} disconnected and cleaned up. Active clients: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, client_id: str):
        """Send a message to a specific client"""
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                if "code 1000" in str(e):
                    logger.info(f"Client {client_id} closed connection normally")
                else:
                    logger.error(f"Error sending message to client {client_id}: {str(e)}")
                await self.disconnect(client_id)

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients"""
        disconnected_clients = []
        for client_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                if "code 1000" in str(e):
                    logger.info(f"Client {client_id} closed connection normally")
                else:
                    logger.error(f"Error broadcasting to client {client_id}: {str(e)}")
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

    def get_client_timezone(self, client_id: str) -> str:
        """Get a client's timezone"""
        return self.client_timezones.get(client_id, "UTC")

    def get_active_connections(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)

    def is_connected(self, client_id: str) -> bool:
        """Check if a client is connected"""
        return client_id in self.active_connections

    async def start_sending(self, client_id: str) -> bool:
        """Mark client as sending a message"""
        if len(self.sending_clients) >= self.MAX_SENDING:
            return False
        self.sending_clients.add(client_id)
        return True

    async def stop_sending(self, client_id: str):
        """Mark client as done sending message"""
        if client_id in self.sending_clients:
            self.sending_clients.remove(client_id)

    async def increment_processing(self) -> bool:
        """Increment message processing count"""
        if self.messages_processing >= self.MAX_PROCESSING:
            return False
        self.messages_processing += 1
        return True

    async def decrement_processing(self):
        """Decrement message processing count"""
        if self.messages_processing > 0:
            self.messages_processing -= 1

    async def heartbeat(self, client_id: str):
        """Update client's last heartbeat time"""
        self.last_heartbeat[client_id] = datetime.now()
        
    async def _heartbeat_loop(self):
        """Background task to send heartbeats and clean up stale connections"""
        while True:
            try:
                current_time = datetime.now()
                stale_clients = []
                
                # Check each client's last heartbeat
                for client_id, last_time in self.last_heartbeat.items():
                    if current_time - last_time > timedelta(seconds=HEARTBEAT_TIMEOUT):
                        logger.warning(f"Client {client_id} timed out (no heartbeat)")
                        stale_clients.append(client_id)
                    elif current_time - last_time > timedelta(seconds=HEARTBEAT_INTERVAL):
                        # Send ping to client
                        try:
                            if client_id in self.active_connections:
                                await self.active_connections[client_id].send_json({
                                    "type": "heartbeat",
                                    "data": {
                                        "message": "ping",
                                        "timestamp": current_time.isoformat()
                                    }
                                })
                        except Exception as e:
                            logger.error(f"Error sending heartbeat to client {client_id}: {str(e)}")
                            stale_clients.append(client_id)
                
                # Clean up stale clients
                for client_id in stale_clients:
                    await self.disconnect(client_id)
                    
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {str(e)}")
                await asyncio.sleep(HEARTBEAT_INTERVAL)  # Wait before retrying