import React, { useState, useRef, useCallback, useEffect } from 'react';
import { w3cwebsocket as W3CWebSocket } from 'websocket';

const ALLOWED_FILE_TYPES = {
  image: ['image/jpeg', 'image/png', 'image/gif'],
  video: [
    'video/mp4',
    'video/webm',
    'video/quicktime',  // .mov
    'video/x-msvideo',  // .avi
    'video/x-matroska', // .mkv
    'video/3gpp'        // .3gp
  ],
  voice: ['audio/mp3', 'audio/wav', 'audio/mpeg', 'audio/m4a']
};

const MAX_FILE_SIZES_MB = {
  image: 5, // MB
  video: 10, // MB
  voice: 5, // MB
};

const MAX_FILE_SIZES_BYTES = {
  image: MAX_FILE_SIZES_MB.image * 1024 * 1024,
  video: MAX_FILE_SIZES_MB.video * 1024 * 1024,
  voice: MAX_FILE_SIZES_MB.voice * 1024 * 1024,
};

const ChatClient = () => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [clientId] = useState('1'); // Set client_id to '1'
  const [pagination, setPagination] = useState({
    offset: 0,
    limit: 50,
    total: 0,
    hasMore: false,
    loading: false
  });
  const fileInputRef = useRef(null);
  const clientRef = useRef(null);
  const messagesEndRef = useRef(null);
  const audioRefs = useRef({}); // To store refs to audio elements
  const [audioStates, setAudioStates] = useState({}); // To store play/pause, currentTime, duration
  
  // Keep track of connection state in a ref for immediate access in callbacks
  const connectedRef = useRef(false);
  
  // Keep track of queued messages
  const queuedMessagesRef = useRef([]);

  const scrollToBottom = useCallback(() => { // Memoize scrollToBottom
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const handlePlayPause = (index) => {
    const audioEl = audioRefs.current[index];
    if (audioEl) {
      if (audioEl.paused || audioEl.ended) {
        audioEl.play();
        setAudioStates(prev => ({ ...prev, [index]: { ...prev[index], isPlaying: true } }));
      } else {
        audioEl.pause();
        setAudioStates(prev => ({ ...prev, [index]: { ...prev[index], isPlaying: false } }));
      }
    }
  };

  const handleLoadedMetadata = (e, index) => {
    const duration = e.target.duration;
    setAudioStates(prev => ({
      ...prev,
      [index]: { ...prev[index], duration: duration, currentTime: 0, isPlaying: false }
    }));
  };

  const handleTimeUpdate = useCallback((e, index) => {
    // Throttle updates to every 500ms and use RAF for smoother updates
    const now = Date.now();
    if (!e.target.lastUpdate || now - e.target.lastUpdate >= 500) {
      requestAnimationFrame(() => {
        const currentTime = e.target.currentTime;
        setAudioStates(prev => {
          if (prev[index]?.currentTime === currentTime) return prev;
          return { ...prev, [index]: { ...prev[index], currentTime } };
        });
      });
      e.target.lastUpdate = now;
    }
  }, []);

  const handleAudioEnded = (index) => {
    setAudioStates(prev => ({ ...prev, [index]: { ...prev[index], isPlaying: false, currentTime: 0 } }));
     // Optionally, reset to beginning if you want the progress bar to reset fully
    if (audioRefs.current[index]) {
        audioRefs.current[index].currentTime = 0;
    }
  };

  // Update the ref whenever the connected state changes
  useEffect(() => {
    connectedRef.current = connected;
  }, [connected]);

  // Separate the message processing logic from the handler
  const processWebSocketMessage = useCallback((data) => {
    // Format server messages to match expected structure
    let formattedMessages = [];
    if (Array.isArray(data.data?.replies)) {
      formattedMessages = data.data.replies.map(reply => ({
        type: 'server',
        content: reply.reply_type === 'text' ? reply.content : {
          url: reply.content,
          filename: reply.content.split('/').pop()
        },
        reply_type: reply.reply_type,
        timestamp: new Date().toISOString()
      }));
    } else {
      formattedMessages = [{
        type: 'server',
        content: data.data?.reply_type === 'text' ?
          (data.data?.content || data.data?.message || data.message || 'No content') :
          {
            url: data.data?.content,
            filename: data.data?.content?.split('/').pop() || 'Server Reply',
            mime_type: data.data?.mime_type
          },
        reply_type: data.data?.reply_type || 'text',
        timestamp: new Date().toISOString()
      }];
    }

    // Batch update messages
    setMessages(prev => {
      const updatedMessages = [...prev];
      formattedMessages.forEach(msg => {
        updatedMessages.push(msg);
      });
      return updatedMessages;
    });

    // Schedule scroll after state update
    setTimeout(scrollToBottom, 10);
  }, [scrollToBottom]);
  
  const processQueuedMessages = useCallback(() => {
    if (queuedMessagesRef.current.length > 0) {
      console.log(`Processing ${queuedMessagesRef.current.length} queued messages`);
      const messages = [...queuedMessagesRef.current];
      queuedMessagesRef.current = [];
      messages.forEach(msg => {
        try {
          const data = JSON.parse(msg.data);
          processWebSocketMessage(data);
        } catch (error) {
          console.error('Error parsing queued message:', error);
        }
      });
    }
  }, [processWebSocketMessage]);

  const handleSystemMessage = useCallback(async (data) => {
    if (data.type === 'system' && data.data?.message === 'Connected successfully') {
      // Update both the state and the ref
      setConnected(true);
      connectedRef.current = true;
      console.log('Connection established successfully, updating state');
      
      try {
        const response = await fetch(`http://localhost:8082/chat-history/${clientId}?limit=${pagination.limit}&offset=${pagination.offset}`);
        if (response.ok) {
          const historyData = await response.json();
          if (historyData.status === 'success' && Array.isArray(historyData.data)) {
            // Update pagination info
            setPagination(prev => ({
              ...prev,
              total: historyData.pagination.total,
              hasMore: historyData.pagination.has_more,
              offset: historyData.pagination.offset
            }));

            const sortedHistory = [...historyData.data]
              .filter(item => !item.is_system)
              .sort((a, b) => new Date(a.client_timestamp) - new Date(b.client_timestamp));

            const formattedHistory = sortedHistory
              .map(item => {
                const messageGroup = [{
                  type: 'user',
                  content: item.message_type === 'text' ? item.content : {
                    filename: item.content,
                    url: item.content
                  },
                  reply_type: item.message_type,
                  timestamp: item.client_timestamp
                }];

                if (item.replies?.length) {
                  item.replies
                    .filter(reply => !reply.is_system)
                    .forEach(reply => {
                      messageGroup.push({
                        type: 'server',
                        content: reply.reply_type === 'text' ? reply.content : {
                          url: reply.content,
                          filename: reply.content.split('/').pop()
                        },
                        reply_type: reply.reply_type
                      });
                    });
                }
                return messageGroup;
              })
              .flat();

            setMessages(formattedHistory);
            scrollToBottom();
            
            // Process any queued messages now that we're connected
            processQueuedMessages();
          }
        }
      } catch (error) {
        console.error('Error fetching chat history:', error);
      }
    }
  }, [clientId, scrollToBottom, processQueuedMessages, pagination.limit, pagination.offset]);

  const handleWebSocketMessage = useCallback((message) => {
    let data;
    try {
      data = JSON.parse(message.data);
      console.log('Received websocket message:', data);
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
      return;
    }
    
    // Always handle system messages, regardless of connection state
    if (data.type === 'system' || data.is_system) {
      handleSystemMessage(data);
      return;
    }

    // Handle heartbeat/ping messages if socket is open
    if ((data.type === 'heartbeat' || data.type === 'ping') && clientRef.current?.readyState === WebSocket.OPEN) {
      clientRef.current.send(JSON.stringify({
        type: 'heartbeat',
        data: {
          message: 'pong',
          timestamp: data.data?.timestamp || new Date().toISOString()
        }
      }));
      return;
    }

    // Check connection using the ref for immediate access
    const isCurrentlyConnected = connectedRef.current;
    console.log(`Processing message with connection state: ${isCurrentlyConnected}`);

    // Queue messages received before connection is established
    if (!isCurrentlyConnected && data.type === 'message') {
      queuedMessagesRef.current.push(message);
      console.log('Queuing message until connected');
      return;
    }

    // Only process regular messages if connected
    if (!isCurrentlyConnected || !clientRef.current) {
      console.log('Skipping non-system message - not connected');
      return;
    }

    // Process the message
    processWebSocketMessage(data);
  }, [handleSystemMessage, processWebSocketMessage]);

  // Process message queue and cleanup on connection state changes
  useEffect(() => {
    if (connected && queuedMessagesRef.current.length > 0) {
      processQueuedMessages();
    }
  }, [connected, processQueuedMessages]);

  // Define cleanup function
  const cleanup = useCallback(() => {
    // Carefully close the connection if it's still open
    if (clientRef.current) {
      // Remove event listeners first to prevent callbacks during closure
      clientRef.current.onclose = null;
      clientRef.current.onerror = null;
      clientRef.current.onmessage = null;
      clientRef.current.onopen = null;

      // Only attempt to close if the connection is still active
      if (clientRef.current.readyState === WebSocket.OPEN || clientRef.current.readyState === WebSocket.CONNECTING) {
        try {
          console.log('Closing WebSocket connection...');
          clientRef.current.close(1000, 'Normal closure');
        } catch (err) {
          console.error('Error closing WebSocket:', err);
        }
      }
    }
    
    // Reset states
    setConnecting(false);
    setConnected(false);
    connectedRef.current = false;
    clientRef.current = null;
    queuedMessagesRef.current = [];
  }, []);

  const connect = useCallback(() => {
    // Prevent multiple connection attempts
    if (connecting || connected) {
      console.log('Already connected or connecting');
      return;
    }

    console.log('Initiating WebSocket connection...');
    
    try {
      // Set connecting state before attempting connection
      setConnecting(true);
      
      const ws = new W3CWebSocket(`ws://localhost:8082/ws`);
      ws.binaryType = 'arraybuffer';
      clientRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket Client Connected');
        setConnecting(false);
        ws.send(JSON.stringify({
          client_id: clientId,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        }));
      };

      ws.onclose = (event) => {
        console.log('WebSocket Client Disconnected');
        cleanup();
      };

      ws.onerror = (error) => {
        console.error('WebSocket connection error:', error);
        cleanup();
      };

      ws.onmessage = handleWebSocketMessage;
    } catch (error) {
      console.error('Error initiating connection:', error);
      setConnecting(false);
    }
  }, [connecting, connected, clientId, handleWebSocketMessage, cleanup]);

  const disconnect = () => {
    if (clientRef.current) {
      clientRef.current.close();
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Check file type
    const fileType = file.type;
    const isAllowed = Object.values(ALLOWED_FILE_TYPES).flat().includes(fileType);
    
    if (!isAllowed) {
      alert('File type not supported. Please select an image, video, or audio file.');
      return;
    }

    if (file.size === 0) {
      alert('Empty files are not allowed.');
      e.target.value = ''; // Clear the file input
      setSelectedFile(null); // Clear any previously selected file state
      return;
    }

    // Check file size
    const messageTypeForSizeCheck = getMessageType(file.type);
    if (messageTypeForSizeCheck !== 'text') { // Only check size for media files
        const maxSize = MAX_FILE_SIZES_BYTES[messageTypeForSizeCheck];
        if (file.size > maxSize) {
            alert(`File is too large. Maximum size for ${messageTypeForSizeCheck} is ${MAX_FILE_SIZES_MB[messageTypeForSizeCheck]}MB.`);
            e.target.value = ''; // Clear the file input
            setSelectedFile(null); // Clear any previously selected file state
            return;
        }
    }

    setSelectedFile(file);
  };

  const getMessageType = (fileType) => {
    if (ALLOWED_FILE_TYPES.image.includes(fileType)) return 'image';
    if (ALLOWED_FILE_TYPES.video.includes(fileType)) return 'video';
    if (ALLOWED_FILE_TYPES.voice.includes(fileType)) return 'voice';
    return 'text';
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if ((!inputMessage.trim() && !selectedFile) || !connectedRef.current) return;

    let messageData;
    
    if (selectedFile) {
      const reader = new FileReader();
      reader.readAsDataURL(selectedFile);
      
      reader.onload = () => {
        const messageType = getMessageType(selectedFile.type);
        // Extract base64 data without data URL prefix
        const base64Data = reader.result.split(',')[1];
        
        messageData = {
          message_type: messageType,
          content: base64Data,  // Send base64 string directly as content
          filename: selectedFile.name,
          timestamp: new Date().toISOString()
        };

        // Add user message to local state with local preview
        const userMessage = {
          type: 'user',
          reply_type: messageType,
          content: {
            content: reader.result,  // Full data URL for local preview
            filename: selectedFile.name,
            isLocalPreview: true  // Flag to identify local previews
          },
          timestamp: new Date().toISOString()
        };
        setMessages(prev => [...prev, userMessage]);
        
        if (clientRef.current && clientRef.current.readyState === WebSocket.OPEN) {
          clientRef.current.send(JSON.stringify(messageData));
        } else {
          console.error('Cannot send message - WebSocket not connected');
        }
        
        setSelectedFile(null);
        fileInputRef.current.value = '';
      };
    } else {
      messageData = {
        message_type: 'text',
        content: inputMessage.trim(),
        timestamp: new Date().toISOString()
      };
      
      // Add user message to local state
      const userMessage = {
        type: 'user',
        content: inputMessage.trim(),
        reply_type: 'text',
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, userMessage]);
      
      if (clientRef.current && clientRef.current.readyState === WebSocket.OPEN) {
        clientRef.current.send(JSON.stringify(messageData));
      } else {
        console.error('Cannot send message - WebSocket not connected');
      }
      
      setInputMessage('');
    }
  };

  // Scroll to bottom whenever messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Add debug logging for connected state changes
  useEffect(() => {
    console.log(`Connected state changed to: ${connected}`);
  }, [connected]);

  const loadMoreMessages = useCallback(async () => {
    if (pagination.loading || !pagination.hasMore) return;
    
    setPagination(prev => ({ ...prev, loading: true }));
    
    try {
      const nextOffset = pagination.offset + pagination.limit;
      const response = await fetch(`http://localhost:8082/chat-history/${clientId}?limit=${pagination.limit}&offset=${nextOffset}`);
      
      if (response.ok) {
        const historyData = await response.json();
        if (historyData.status === 'success' && Array.isArray(historyData.data)) {
          // Update pagination info
          setPagination(prev => ({
            ...prev,
            total: historyData.pagination.total,
            hasMore: historyData.pagination.has_more,
            offset: nextOffset,
            loading: false
          }));

          const sortedHistory = [...historyData.data]
            .filter(item => !item.is_system)
            .sort((a, b) => new Date(a.client_timestamp) - new Date(b.client_timestamp));

          const formattedHistory = sortedHistory
            .map(item => {
              const messageGroup = [{
                type: 'user',
                content: item.message_type === 'text' ? item.content : {
                  filename: item.content,
                  url: item.content
                },
                reply_type: item.message_type,
                timestamp: item.client_timestamp
              }];

              if (item.replies?.length) {
                item.replies
                  .filter(reply => !reply.is_system)
                  .forEach(reply => {
                    messageGroup.push({
                      type: 'server',
                      content: reply.reply_type === 'text' ? reply.content : {
                        url: reply.content,
                        filename: reply.content.split('/').pop()
                      },
                      reply_type: reply.reply_type
                    });
                  });
              }
              return messageGroup;
            })
            .flat();

          setMessages(prev => [...prev, ...formattedHistory]);
          scrollToBottom();
        }
      }
    } catch (error) {
      console.error('Error loading more messages:', error);
    } finally {
      setPagination(prev => ({ ...prev, loading: false }));
    }
  }, [clientId, pagination.offset, pagination.limit, pagination.hasMore, pagination.loading, scrollToBottom]);

  return (
    <div className="chat-container">
      {pagination.hasMore && (
        <div className="load-more">
          <button
            onClick={loadMoreMessages}
            disabled={pagination.loading}
          >
            {pagination.loading ? 'Loading...' : 'Load More Messages'}
          </button>
        </div>
      )}
      <div className="chat-messages">
        {messages.map((msg, index) => {
          const isMedia = msg.reply_type && ['image', 'video', 'voice'].includes(msg.reply_type);
          let mediaContent = null;
          // Populate mediaContent if the message is media and content is an object (for any type: user or server)
          if (isMedia && typeof msg.content === 'object') {
            mediaContent = msg.content;
          }
          
          let displaySrc = null;
          if (mediaContent) {
            if (mediaContent.isLocalPreview) {
              // Use data URL for local preview
              displaySrc = mediaContent.content;
            } else if (mediaContent.url) {
              // Use server URL for received/historical media (port 8082)
              const url = mediaContent.url.replace(/\\/g, '/');
              // Handle different media paths
              displaySrc = url.startsWith('http') ? url :
                          url.startsWith('/static_replies/') ? `http://localhost:8082/static_replies/${url.split('/static_replies/')[1]}` :
                          url.startsWith('/') ? `http://localhost:8082${url}` :
                          url.includes('static_replies/') ? `http://localhost:8082/static_replies/${url.split('static_replies/')[1]}` :
                          `http://localhost:8082/${url}`;
            }
          }
          
          return (
            <div key={index} className={`message ${msg.type || ''} ${msg.reply_type || ''}`}>
              {msg.type === 'error' ? (
                <p className="error-message">{msg.data.message}</p>
              ) : (
                <div className="message-content">
                  <span className="sender">{msg.type === 'user' ? 'You' : 'Server'}: </span>
                  {mediaContent ? (
                    <div className="media-content">
                      {mediaContent && displaySrc && (
                        <>
                          {msg.reply_type === 'image' && (
                            <img
                              src={displaySrc}
                              alt={mediaContent.filename}
                              className="media-preview"
                            />
                          )}
                          {msg.reply_type === 'video' && (
                            <video controls className="media-preview">
                              <source
                                src={displaySrc}
                                type={mediaContent.mime_type || 'video/quicktime'}
                              />
                              <source
                                src={displaySrc}
                                type="video/mp4"
                              />
                              Your browser does not support the video tag or this video format.
                            </video>
                          )}
                          {msg.reply_type === 'voice' && (
                            <div className="custom-audio-player media-preview">
                              {/* Hidden audio element for playback control */}
                              <audio
                                ref={el => audioRefs.current[index] = el}
                                src={displaySrc}
                                preload="metadata"
                                style={{ display: 'none' }}
                                onLoadedMetadata={(e) => handleLoadedMetadata(e, index)}
                                onTimeUpdate={(e) => handleTimeUpdate(e, index)}
                                onEnded={() => handleAudioEnded(index)}
                              >
                                <source
                                  src={displaySrc}
                                  type={mediaContent.filename?.includes('.mp3') ? 'audio/mpeg' : `audio/${mediaContent.filename?.split('.').pop() || 'mp3'}`}
                                />
                                Your browser does not support the audio tag.
                              </audio>
                              <button
                                className="play-pause-button"
                                onClick={() => handlePlayPause(index)}
                              >
                                {audioStates[index]?.isPlaying ? '\u23F8' : '\u25B6'} {/* Pause or Play icon */}
                              </button>
                              <div className="progress-bar-container">
                                <div
                                  className="progress-bar"
                                  style={{ width: `${audioStates[index]?.duration ? (audioStates[index]?.currentTime / audioStates[index]?.duration) * 100 : 0}%` }}
                                ></div>
                              </div>
                            </div>
                          )}
                        </>
                      )}
                      <span className="media-filename">
                        {mediaContent.filename?.includes('reply') ? 'Server Reply' : mediaContent.filename}
                      </span>
                    </div>
                  ) : (
                    <span>{msg.content}</span>
                  )}
                </div>
              )}
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={sendMessage} className="chat-input">
        <div className="input-container">
          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder="Type a message..."
            disabled={!connected}
          />
          <input
            ref={fileInputRef}
            type="file"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
            accept=".jpg,.jpeg,.png,.gif,.mp4,.webm,.mov,.avi,.mkv,.3gp,.mp3,.wav,.m4a"
          />
          <button
            type="button"
            className="attach-btn"
            onClick={() => fileInputRef.current.click()}
            disabled={!connected || inputMessage.trim() !== ''}
          >
            📎
          </button>
        </div>
        {selectedFile && (
          <div className="file-preview">
            Selected: {selectedFile.name}
            <button type="button" onClick={() => {
              setSelectedFile(null);
              fileInputRef.current.value = '';
            }}>×</button>
          </div>
        )}
        <button type="submit" disabled={!connected || (!inputMessage.trim() && !selectedFile)}>
          Send
        </button>
      </form>
      <div className="connection-controls">
        {!connected && !connecting ? (
          <button onClick={connect} className="connect-btn">
            Connect
          </button>
        ) : connected ? (
          <button onClick={disconnect} className="disconnect-btn">
            Disconnect
          </button>
        ) : null}
        <div className="connection-status">
          Status: {connecting ? 'Connecting...' : connected ? 'Connected' : 'Disconnected'}
        </div>
      </div>
    </div>
  );
};

export default ChatClient;