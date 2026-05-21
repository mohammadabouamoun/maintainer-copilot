import { useState } from 'react';
import { X } from 'lucide-react';
import MessageInput from './MessageInput.tsx';
import StreamingMessage from './StreamingMessage.tsx';
import type { WidgetConfig } from '../types';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatPanel({ config, onClose, apiUrl, widgetId }: { config: WidgetConfig, onClose: () => void, apiUrl: string, widgetId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState(false);

  const handleSend = async (text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setIsStreaming(true);
  };

  const handleStreamEnd = (finalText: string, newConvId?: string) => {
    setMessages(prev => [...prev, { role: 'assistant', content: finalText }]);
    if (newConvId) setConversationId(newConvId);
    setIsStreaming(false);
  };

  return (
    <div className="glass-panel chat-panel">
      <div className="panel-header">
        <span style={{ fontWeight: 600 }}>Maintainer's Copilot</span>
        <X size={20} style={{ cursor: 'pointer' }} onClick={onClose} />
      </div>
      
      <div className="messages-container">
        <div className="message assistant">
          {config.greeting || "Hi! How can I help you?"}
        </div>
        
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            {m.content}
          </div>
        ))}
        
        {isStreaming && (
          <StreamingMessage 
            apiUrl={apiUrl}
            prompt={messages[messages.length-1].content} 
            conversationId={conversationId} 
            widgetId={widgetId}
            onComplete={handleStreamEnd} 
          />
        )}
      </div>

      <MessageInput onSend={handleSend} disabled={isStreaming} />
    </div>
  );
}
