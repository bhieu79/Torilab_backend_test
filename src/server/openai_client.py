import os
from typing import Dict, Any
import logging
from httpx import AsyncClient, TimeoutException
from dotenv import load_dotenv
from datetime import datetime, timedelta

logger = logging.getLogger("app")
load_dotenv()

class OpenAIClient:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4")
        self.api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "1000"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
        
        # Rate limit tracking
        self.rate_limit_hit = False
        self.rate_limit_time = None
        self.rate_limit_duration = timedelta(minutes=30)
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

    def is_rate_limited(self) -> bool:
        """Check if we're currently rate limited"""
        if not self.rate_limit_hit:
            return False
            
        if datetime.now() - self.rate_limit_time > self.rate_limit_duration:
            # Reset rate limit after cooldown period
            self.rate_limit_hit = False
            self.rate_limit_time = None
            return False
            
        return True

    def _prepare_chat_request(self, message: str) -> Dict[str, Any]:
        """Prepare the chat completion request data"""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": message}
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }

    async def get_chat_response(self, message: str) -> str:
        """Get a chat response from OpenAI with proper error handling"""
        # Check rate limit before making request
        if self.is_rate_limited():
            return "Sorry, still rate limited. Please try again later."
            
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = self._prepare_chat_request(message)
        
        try:
            async with AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                if response.status_code == 401:
                    logger.error(f"OpenAI API authentication failed (HTTP {response.status_code})")
                    return "Sorry, I'm having trouble with my authentication. Please try again later."
                    
                elif response.status_code == 429:
                    logger.error(f"OpenAI API rate limit exceeded (HTTP {response.status_code})")
                    # Set rate limit tracking
                    self.rate_limit_hit = True
                    self.rate_limit_time = datetime.now()
                    return "Sorry, I'm receiving too many requests right now. Please try again in 30 minutes."
                    
                elif response.status_code != 200:
                    logger.error(f"OpenAI API error (HTTP {response.status_code}): {response.text}")
                    return "Sorry, I'm having trouble processing your request. Please try again later."
                    
                try:
                    result = response.json()
                    if not result.get("choices") or not result["choices"][0].get("message"):
                        logger.error(f"Invalid OpenAI response format: {result}")
                        return "Sorry, I received an invalid response. Please try again."
                    return result["choices"][0]["message"]["content"].strip()
                except Exception as e:
                    logger.error(f"Failed to parse OpenAI response: {str(e)}\nResponse: {response.text}")
                    return "Sorry, I received an invalid response. Please try again."
                
        except TimeoutException:
            logger.error("OpenAI API request timed out (30s)")
            return "Sorry, the request timed out. Please try again."
            
        except Exception as e:
            logger.error(f"OpenAI request failed ({type(e).__name__}): {str(e)}")
            return "Sorry, I'm having trouble connecting to my AI service. Please try again later."

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status"""
        if not self.rate_limit_hit:
            return {
                "rate_limited": False,
                "time_remaining": None
            }
            
        time_elapsed = datetime.now() - self.rate_limit_time
        time_remaining = self.rate_limit_duration - time_elapsed
        
        return {
            "rate_limited": True,
            "time_remaining": time_remaining.total_seconds()
        }