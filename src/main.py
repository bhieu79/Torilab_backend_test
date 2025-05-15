import logging
from server.logging_config import logging_setup
import os
import uvicorn
from init_db import init_database
import asyncio
from dotenv import load_dotenv

load_dotenv()  # Load from .env file

# Set up logging first before any imports
logger = logging_setup()

async def init_media_dirs():
    """Initialize media directories"""
    media_types = ['images', 'videos', 'voices']
    media_root = 'media'
    
    try:
        # Create main media directory
        if not os.path.exists(media_root):
            os.makedirs(media_root)
            
        # Create subdirectories for each media type
        for media_type in media_types:
            media_dir = os.path.join(media_root, media_type)
            if not os.path.exists(media_dir):
                os.makedirs(media_dir)
                
        logger.info("Media directories initialized", extra={
            'component': 'Setup',
            'media_types': media_types
        })
        
    except Exception as e:
        logger.error("Media directory initialization failed", extra={
            'component': 'Setup',
            'error': str(e)
        })
        raise

async def init_server():
    """Initialize server components"""
    try:
        # Initialize media directories
        await init_media_dirs()
        
        # Initialize database
        await init_database()
        
        logger.info("Server initialization completed", extra={
            'component': 'Setup'
        })
        
    except Exception as e:
        logger.error("Server initialization failed", extra={
            'component': 'Setup',
            'error': str(e)
        })
        raise

def main():
    try:
        # Run initialization
        asyncio.run(init_server())
        
        # Get host and port from environment or use defaults
        host = os.getenv("SERVER_HOST", "localhost")
        port = int(os.getenv("SERVER_PORT", 8082))
        logger.info("Starting server", extra={
            'component': 'Setup',
            'host': host,
            'port': port
        })

        # Start FastAPI server with uvicorn
        uvicorn.run(
            "server.chat_server:app",
            host=host,
            port=port,
            reload=True,  # Enable auto-reload for development
            log_level="info"
        )

    except Exception as e:
        logger.error("Server startup failed", extra={
            'component': 'Setup',
            'error': str(e)
        })
        raise

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error("Server crashed", extra={
            'component': 'Setup',
            'error': str(e)
        })
