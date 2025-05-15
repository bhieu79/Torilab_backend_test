import React from 'react';
import './App.css';
import ChatClient from './components/ChatClient';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>Chat Application</h1>
      </header>
      <main>
        <ChatClient />
      </main>
    </div>
  );
}

export default App;
