import asyncio
import logging
from alembic.config import Config
from alembic import command

logger = logging.getLogger('app')

async def init_database():
    """Initialize database with tables"""
    try:
        # Run database migrations asynchronously
        def run_upgrade(cfg):
            command.upgrade(cfg, "head")
        
        alembic_cfg = Config("alembic.ini")
        # Run in executor to avoid blocking
        await asyncio.get_event_loop().run_in_executor(None, run_upgrade, alembic_cfg)
        logger.info("Database migrations completed", extra={
            'version': 'head'
        })

    except Exception as e:
        logger.warning("Database migration warning", extra={
            'error': str(e),
            'message': 'This is okay if tables exist'
        })

if __name__ == "__main__":
    asyncio.run(init_database())