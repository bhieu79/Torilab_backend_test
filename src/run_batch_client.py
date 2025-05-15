import os
import asyncio
from batch_client import main

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Run the batch client
asyncio.run(main())