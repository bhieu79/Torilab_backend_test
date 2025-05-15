import os
import base64
import logging
import random
import traceback
from datetime import datetime
from typing import Optional, Union
from pathlib import Path

logger = logging.getLogger("my_logger")

class MediaHandler:
    def __init__(self):
        self.media_root = "media"
        self.media_types = {
            "image": ["jpg", "jpeg", "png", "gif"],
            "video": [
                "mp4",  # MPEG-4
                "webm", # WebM
                "mov",  # QuickTime
                "avi",  # AVI
                "mkv",  # Matroska
                "3gp"   # 3GPP
            ],
            "voice": ["wav", "mp3", "m4a"]
        }
        
        # MIME type mappings
        self.mime_types = {
            "mp4": "video/mp4",
            "webm": "video/webm",
            "mov": "video/quicktime",
            "avi": "video/x-msvideo",
            "mkv": "video/x-matroska",
            "3gp": "video/3gpp",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
            "m4a": "audio/mp4"
        }
        
        # Create media directories if they don't exist
        for media_type in self.media_types:
            media_dir = os.path.join(self.media_root, f"{media_type}s")
            if not os.path.exists(media_dir):
                logger.info(f"Creating media directory: {media_dir}")
                os.makedirs(media_dir, exist_ok=True)
        
    def _get_media_dir(self, media_type: str) -> str:
        """Get the appropriate directory for a media type"""
        media_dir = os.path.join(self.media_root, media_type + "s")
        logger.debug(f"Using media directory: {media_dir}")
        return media_dir
        
    def _is_valid_extension(self, filename: str, media_type: str) -> bool:
        """Check if the file extension is valid for the media type"""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        is_valid = ext in self.media_types.get(media_type, [])
        logger.debug(f"File extension validation - {filename}: {ext} ({is_valid})")
        return is_valid
        
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal"""
        safe_name = os.path.basename(filename)
        logger.debug(f"Sanitized filename: {filename} -> {safe_name}")
        return safe_name
        
    async def save_media(self, content: Union[str, dict, bytes], media_type: str, filename: str) -> Optional[str]:
        """Save media content to file and return the saved path"""
        try:
            logger.info(f"Saving {media_type} file: {filename}")
            
            # Extract content if it's a dict
            if isinstance(content, dict):
                logger.debug(f"Processing content with keys: {list(content.keys())}")
                if 'content' not in content:
                    logger.error(f"Missing content key. Available keys: {list(content.keys())}")
                    return None
                content = content['content']
            
            # Handle content based on type
            if isinstance(content, str):
                # Try to decode base64 content
                try:
                    file_content = base64.b64decode(content)
                except Exception as e:
                    logger.error(f"Base64 decode failed: {str(e)}")
                    return None
            elif isinstance(content, bytes):
                # Use byte data directly
                file_content = content
            else:
                logger.error(f"Unsupported content type: {type(content)}")
                return None
            
            # Validate content
            if not file_content:
                logger.error("Empty content provided")
                return None
                
            # Validate media type
            if media_type not in self.media_types:
                logger.error(f"Invalid media type: {media_type}. Supported types: {list(self.media_types.keys())}")
                return None
                
            # Get and ensure media directory exists
            media_dir = self._get_media_dir(media_type)
            os.makedirs(media_dir, exist_ok=True)
            
            # Sanitize and validate filename
            filename = self._sanitize_filename(filename)
            if not self._is_valid_extension(filename, media_type):
                logger.error(f"Invalid extension for {filename}. Valid extensions: {self.media_types[media_type]}")
                return None
                
            # Generate unique filename with timestamp and random string
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            random_str = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=6))
            base_name, ext = os.path.splitext(filename)
            new_filename = f"{base_name}_{timestamp}_{random_str}{ext}"
            file_path = os.path.join(media_dir, new_filename)
                
            # Write file in chunks to handle large files
            try:
                chunk_size = 1024 * 1024  # 1MB chunks
                with open(file_path, 'wb') as f:
                    for i in range(0, len(file_content), chunk_size):
                        chunk = file_content[i:i + chunk_size]
                        f.write(chunk)
                        f.flush()
                        logger.debug(f"Wrote chunk {i//chunk_size + 1} ({len(chunk)} bytes)")
                
                logger.info(f"Saved {media_type} file to {file_path} ({len(file_content)} bytes)")
                return file_path
                
            except Exception as e:
                logger.error(f"Failed to write file {file_path}: {str(e)}")
                # Try to clean up partial file
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass
                return None
                
        except Exception as e:
            logger.error(f"Error saving {media_type} file {filename}: {str(e)}")
            return None