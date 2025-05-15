#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
from pathlib import Path

from server.logging_config import setup_logging
setup_logging()
logger = logging.getLogger("my_logger")

def check_python_version():
    """Check if Python version is 3.10 or higher"""
    if sys.version_info < (3, 10):
        logger.error("Python 3.10 or higher is required")
        sys.exit(1)

def create_virtual_environment():
    """Create virtual environment if it doesn't exist"""
    if not os.path.exists("venv"):
        logger.info("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        logger.info("Virtual environment created successfully")

def install_requirements():
    """Install required packages"""
    venv_python = "venv/bin/python" if os.name != 'nt' else r"venv\Scripts\python.exe"
    logger.info("Installing requirements...")
    subprocess.run([venv_python, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

def setup_environment():
    """Set up environment configuration"""
    if not os.path.exists(".env"):
        logger.info("Creating .env file from template...")
        with open(".env.example", "r") as example, open(".env", "w") as env:
            env.write(example.read())
        logger.info("Created .env file. Please update it with your settings")

def create_directories():
    """Create required directories"""
    dirs = [
        "media/images",
        "media/videos",
    ]
    
    for dir_path in dirs:
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)
        # Create .gitkeep to preserve empty directories
        (path / ".gitkeep").touch()
    
    logger.info("Created required directories")

def initialize_database():
    """Initialize the database"""
    venv_python = "venv/bin/python" if os.name != 'nt' else r"venv\Scripts\python.exe"
    logger.info("Initializing database...")
    subprocess.run([venv_python, "src/init_db.py"], check=True)

def main():
    """Main initialization function"""
    try:
        logger.info("Starting project initialization...")
        
        # Run initialization steps
        check_python_version()
        create_virtual_environment()
        install_requirements()
        setup_environment()
        create_directories()
        initialize_database()
        
        logger.info("""
Project initialized successfully!

To start the application:
1. Activate virtual environment:
   - On Unix/macOS: source venv/bin/activate
   - On Windows: .\\venv\\Scripts\\activate

2. Edit .env file with your settings

3. Start the server:
   python src/main.py

4. In another terminal, start the client:
   python src/run_client.py
""")

    except subprocess.CalledProcessError as e:
        logger.error(f"Initialization failed during subprocess execution: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()