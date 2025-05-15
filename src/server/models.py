from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from enum import Enum

class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    FILE = "file"

Base = declarative_base()

class Client(Base):
    __tablename__ = 'clients'
    
    client_id = Column(String, primary_key=True)
    timezone = Column(String, nullable=False)
    
    messages = relationship("Message", back_populates="client")

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    client_id = Column(String, ForeignKey('clients.client_id'), nullable=False)
    message_type = Column(String(5), nullable=False)
    content = Column(String, nullable=False)
    client_timestamp = Column(DateTime, nullable=False)
    timezone = Column(String, nullable=False)  # Store timezone for each message
    is_accepted = Column(Boolean, nullable=False)  # Track message acceptance
    status_message = Column(String)  # Store validation/error messages
    
    client = relationship("Client", back_populates="messages")
    replies = relationship("Reply", back_populates="message")

class Reply(Base):
    __tablename__ = 'replies'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('messages.id'), nullable=False)
    content = Column(String, nullable=False)
    reply_type = Column(String, nullable=False)
    is_delivered = Column(Boolean, nullable=False, default=False)
    
    message = relationship("Message", back_populates="replies")