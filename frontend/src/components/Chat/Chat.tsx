import { useState, useRef, useEffect } from 'react';
import type { ChatMessage } from '../../types';
import './Chat.css';

interface Props {
  chatHistory: ChatMessage[];
  selectedPath: string[] | null;
  onSendMessage: (text: string) => void;
}

export function Chat({ chatHistory, selectedPath, onSendMessage }: Props) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory.length]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    onSendMessage(text);
    setInput('');
  };

  const contextLabel = selectedPath
    ? selectedPath[selectedPath.length - 1]
    : null;

  return (
    <div className="chat">
      <div className="chat-header">
        <h4 className="chat-title">🤖 AI-ассистент</h4>
        <span className="chat-context">
          Контекст: {contextLabel ? <strong>{contextLabel}</strong> : <em>общий</em>}
        </span>
      </div>

      <div className="chat-messages">
        {chatHistory.length === 0 && (
          <div className="chat-empty">
            Начните диалог — задайте вопрос или поставьте задачу.
          </div>
        )}
        {chatHistory.map((msg, i) => (
          <div key={i} className={`chat-bubble ${msg.role === 'user' ? 'user' : 'ai'}`}>
            <span className="chat-icon">{msg.role === 'user' ? '👤' : '🤖'}</span>
            <span className="chat-text">{msg.text}</span>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-bar" onSubmit={handleSubmit}>
        <input
          type="text"
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Задайте вопрос или поставьте задачу…"
        />
        <button type="submit" className="chat-send" disabled={!input.trim()}>
          ➤
        </button>
      </form>
    </div>
  );
}
