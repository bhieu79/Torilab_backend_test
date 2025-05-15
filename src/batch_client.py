import asyncio
import websockets
import json
import random
import uuid
import logging
from datetime import datetime, timezone
import sys
from typing import List, Set, Dict
import time
from asyncio import Semaphore, Queue, Task
from contextlib import suppress

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/batch_client.log')
    ]
)
logger = logging.getLogger(__name__)

class BatchClient:
    def __init__(self, server_url: str = "ws://localhost:8082/ws"):
        self.server_url = server_url
        self.total_messages = 2000  # Total messages to send
        self.num_clients = 100  # Set to exactly 100 clients
        self.duration = 300  # Set to 5 minutes to ensure all clients get to send
        self.messages_sent = 0
        self.messages_failed = 0
        self.rate_limits_hit = 0
        self.connections_rejected = 0
        self.active_clients: Set[str] = set()
        self.message_queue = Queue()
        self.start_time = None
        self.all_clients: List[str] = [f"batch_client_{i}" for i in range(self.num_clients)]
        
        # Connection management - Push beyond server limits
        self.connection_semaphore = Semaphore(100)  # Try to connect 100 clients simultaneously
        self.active_connections = 0
        self.max_active_connections = 100  # Maintain all 100 clients active
        self.min_active_connections = 100  # Keep all 100 clients connected
        
        # Rate limiting - Extreme load testing
        self.message_semaphore = Semaphore(2000)  # Try to process 2000 messages simultaneously
        self.batch_size = 100  # Larger batches
        self.message_delay = 0.05  # 50ms between messages
        self.connection_delay = 0.1  # 100ms between connections
        self.disconnect_probability = 0.01  # Reduce disconnect chance to 1%
        self.reconnect_delay = (0.5, 2)  # Faster reconnection between 0.5-2 seconds
        
        # Client state tracking
        self.client_tasks: Dict[str, Task] = {}
        self.failed_messages: List[tuple] = []
        self.client_message_counts: Dict[str, int] = {}
        self.shutdown_event = asyncio.Event()

    async def manage_connection_pool(self):
        """Maintain a healthy pool of connections"""
        while not self.shutdown_event.is_set():
            current_connections = len(self.active_clients)
            
            if current_connections < self.min_active_connections:
                # Add more connections
                available_clients = [c for c in self.all_clients if c not in self.active_clients]
                if available_clients:
                    client_id = random.choice(available_clients)
                    self.client_tasks[client_id] = asyncio.create_task(self.client_session(client_id))
            
            elif current_connections > self.max_active_connections:
                # Remove excess connections
                excess = current_connections - self.max_active_connections
                clients_to_remove = random.sample(list(self.active_clients), min(excess, len(self.active_clients)))
                for client_id in clients_to_remove:
                    if client_id in self.client_tasks:
                        self.client_tasks[client_id].cancel()
            
            await asyncio.sleep(1)

    async def send_message(self, websocket, client_id: str) -> bool:
        """Send a message with rate limiting and retries"""
        max_retries = 3
        retry_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                async with self.message_semaphore:
                    message = {
                        "content": f"Test message {self.messages_sent} from {client_id}",
                        "message_type": "text",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    await websocket.send(json.dumps(message))
                    
                    # Wait for acknowledgment with timeout
                    try:
                        async with asyncio.timeout(5.0):
                            response = await websocket.recv()
                            response_data = json.loads(response)
                            
                            if response_data.get("type") == "error":
                                error_msg = response_data.get('data', {}).get('message', '')
                                logger.warning(f"Error sending message from {client_id}: {error_msg}")
                                if "rate limit" in error_msg.lower():
                                    self.rate_limits_hit += 1
                                self.messages_failed += 1
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(retry_delay)
                                    retry_delay *= 2
                                    continue
                                return False
                            
                            self.messages_sent += 1
                            self.client_message_counts[client_id] = self.client_message_counts.get(client_id, 0) + 1
                            
                            if self.messages_sent % 100 == 0:
                                elapsed = time.time() - self.start_time
                                logger.info(f"Progress: {self.messages_sent}/{self.total_messages} messages sent. "
                                          f"Time elapsed: {elapsed:.2f}s")
                            
                            await asyncio.sleep(self.message_delay)
                            return True
                            
                    except asyncio.TimeoutError:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        logger.error(f"Timeout sending message from {client_id} after {max_retries} attempts")
                        return False
                    
            except Exception as e:
                logger.error(f"Error in send_message for {client_id}: {str(e)}")
                return False

    async def client_session(self, client_id: str):
        """Handle individual client websocket session with retries"""
        retry_count = 0
        max_retries = 3
        backoff_delay = 1.0
        
        while retry_count < max_retries and not self.shutdown_event.is_set():
            # Check if client is already connected
            if client_id in self.active_clients:
                logger.warning(f"Client {client_id} is already connected. Skipping...")
                self.connections_rejected += 1
                return

            # Track connection attempt
            logger.info(f"Attempting to connect client {client_id}")

            try:
                async with self.connection_semaphore:
                    async with websockets.connect(self.server_url) as websocket:
                        # Send initial connection message
                        await websocket.send(json.dumps({
                            "client_id": client_id,
                            "timezone": "UTC"
                        }))
                        
                        self.active_clients.add(client_id)
                        logger.info(f"Client {client_id} connected. Active clients: {len(self.active_clients)}")

                        last_check = time.time()
                        while not self.shutdown_event.is_set():
                            try:
                                # Non-blocking receive for any server messages
                                message = await asyncio.wait_for(websocket.recv(), 0.1)
                                # Randomly ignore ping messages to simulate connection drops
                                if random.random() < self.disconnect_probability:
                                    logger.info(f"Client {client_id} ignoring server message")
                                    continue
                            except asyncio.TimeoutError:
                                pass
                            except Exception as e:
                                logger.error(f"Error receiving message for {client_id}: {str(e)}")
                                break

                            current_time = time.time()
                            if self.messages_sent >= self.total_messages:
                                return
                                
                            if random.random() < 0.8:  # 80% chance to send message for higher throughput
                                if not await self.send_message(websocket, client_id):
                                    break
                            
                            await asyncio.sleep(random.uniform(0.1, 0.5))

                        # Random delay before reconnecting
                        delay = random.uniform(*self.reconnect_delay)
                        logger.info(f"Client {client_id} will reconnect in {delay:.1f} seconds")
                        await asyncio.sleep(delay)

            except websockets.exceptions.WebSocketException as ws_error:
                logger.error(f"WebSocket error for client {client_id}: {str(ws_error)}")
                self.connections_rejected += 1
                retry_count += 1
                await asyncio.sleep(backoff_delay)
                backoff_delay *= 2
                continue
            except Exception as e:
                logger.error(f"Unexpected error in client {client_id}: {str(e)}")
                retry_count += 1
                await asyncio.sleep(backoff_delay)
                backoff_delay *= 2
            except Exception as e:
                retry_count += 1
                logger.error(f"Error in client {client_id}: {str(e)}")
                await asyncio.sleep(backoff_delay)
                backoff_delay *= 2
            finally:
                self.active_clients.discard(client_id)
                logger.info(f"Client {client_id} disconnected. Active clients: {len(self.active_clients)}")

    async def run(self):
        """Main execution method"""
        self.start_time = time.time()
        last_status_time = time.time()
        status_interval = 10  # Log status every 10 seconds

        logger.info(f"Starting batch client test with {self.num_clients} clients targeting {self.total_messages} messages")
        logger.info(f"Settings: max_connections={self.connection_semaphore._value}, "
                   f"max_messages={self.message_semaphore._value}")
        
        # Start connection pool manager
        pool_manager = asyncio.create_task(self.manage_connection_pool())
        
        try:
            while self.messages_sent < self.total_messages:
                current_time = time.time()
                
                # Check if we've exceeded time limit
                if current_time - self.start_time > self.duration:
                    logger.warning("Time limit reached before sending all messages")
                    break

                # Log periodic status updates
                if current_time - last_status_time >= status_interval:
                    elapsed = current_time - self.start_time
                    message_rate = self.messages_sent / elapsed if elapsed > 0 else 0
                    
                    logger.info(f"Status Update:")
                    logger.info(f"Active Clients: {len(self.active_clients)}/{self.num_clients}")
                    logger.info(f"Messages: {self.messages_sent}/{self.total_messages} ({message_rate:.1f} msgs/sec)")
                    logger.info(f"Failed: {self.messages_failed}, Rate Limited: {self.rate_limits_hit}")
                    logger.info(f"Time: {elapsed:.1f}/{self.duration} seconds")
                    
                    last_status_time = current_time

                await asyncio.sleep(0.1)
            
        finally:
            # Cleanup
            self.shutdown_event.set()
            for task in self.client_tasks.values():
                task.cancel()
            
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*self.client_tasks.values(), return_exceptions=True)
            
            pool_manager.cancel()
            with suppress(asyncio.CancelledError):
                await pool_manager
                
        elapsed = time.time() - self.start_time
        logger.info("Test Results:")
        logger.info(f"Duration: {elapsed:.2f} seconds")
        logger.info(f"Messages sent successfully: {self.messages_sent}")
        logger.info(f"Messages failed: {self.messages_failed}")
        logger.info(f"Rate limits hit: {self.rate_limits_hit}")
        logger.info(f"Connections rejected: {self.connections_rejected}")
        logger.info(f"Success rate: {(self.messages_sent / (self.messages_sent + self.messages_failed)) * 100:.1f}%")
        
        # Print top 10 client message distribution
        logger.info("\nTop 10 clients by message count:")
        for client_id, count in sorted(self.client_message_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            logger.info(f"{client_id}: {count} messages")

async def main():
    client = BatchClient()
    await client.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {str(e)}", exc_info=True)