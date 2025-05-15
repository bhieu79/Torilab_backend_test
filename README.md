## Implementation
- This source code fullfill most of the function stated in the test.

## Requirements

- Python 3.10 or higher 
- Node.js 14+ (for client)
- Dependencies listed in `requirements.txt`
- OpenAI API key
- Sufficient disk space for media storage

## Setup

1. Clone the repository:
```bash
git clone https://github.com/bhieu79/Torilab_backend_test.git
cd Torilab_backend_test
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
cd client && npm install    # Install client dependencies
```

4. Configure environment:
```bash
cp .env.example .env
```
Edit `.env` to set:
- OPENAI_API_KEY: Your OpenAI API key
- MAX_CONNECTIONS: Maximum simultaneous connections (default 100)
- MAX_MESSAGE_SIZE: Maximum message size in bytes
- MEDIA_STORAGE_PATH: Path for media file storage

5. Initialize the database:
```bash
python src/init_db.py
```

## Running the Server

1. Start the main server:
```bash
python src/main.py
```

2. Launch the client application:
```bash
cd client && npm start
```

3. (Optional) Run batch client for testing:
```bash
python src/run_batch_client.py
```

## Architecture

### Server Components

- `chat_server.py`: Main WebSocket server with connection handling
- `connection_manager.py`: Manages active connections and rate limiting
- `message_processor.py`: Processes messages and generates responses
- `media_handler.py`: Handles media file uploads and processing
- `database.py`: Manages database operations with retry logic
- `models.py`: SQLAlchemy database models

### Client Structure

- React-based frontend with WebSocket client
- Real-time message updates and media preview
- Connection status monitoring
- Responsive dark theme UI

## Performance Features

- Connection Management:
  - Rate limiting (50 client sending messages at any moment)
  - Automatic cleanup of inactive connections
  
- Database Optimization:
  - SQLite with IMMEDIATE transaction isolation
  - Retry mechanism for concurrent writes
  - Connection timeout handling
  
- Media Processing:
  - Asynchronous file handling
  - Automatic file organization
  - Size and format validation

## Development Tools

- `src/batch_client.py`: Load testing tool
- `src/cleanup.py`: Environment cleanup utility
- Database migrations via Alembic
- Logging configuration in `logging_config.py`

## Project Structure

```
.
├── media/                 # Media file storage
│   ├── images/           # Image files
│   ├── videos/           # Video files
│   └── voices/           # Voice messages
├── migrations/           # Database migrations
├── src/
│   ├── server/          # Server components
│   │   ├── chat_server.py
│   │   ├── connection_manager.py
│   │   ├── message_processor.py
│   │   └── media_handler.py
│   ├── main.py          # Server entry point
│   └── batch_client.py  # Testing utility
├── client/              # React frontend
├── .env                 # Environment configuration
└── requirements.txt     # Python dependencies
```

## Error Handling

- Comprehensive error handling for:
  - Connection failures
  - Database locks and timeouts
  - Media processing issues
  - Rate limit violations
- Automatic reconnection logic
- Detailed error logging
- Client feedback for all error conditions

## Testing

Use the batch client to test server performance:
```bash
python src/run_batch_client.py
```
This will simulate multiple clients connecting and sending messages simultaneously.

## License

This project is licensed under the MIT License - see the LICENSE file for details.