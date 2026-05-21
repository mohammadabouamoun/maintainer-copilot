import { MessageCircle } from 'lucide-react';

export default function ChatBubble({ onClick }: { onClick: () => void }) {
  return (
    <div className="chat-bubble" onClick={onClick}>
      <MessageCircle size={32} />
    </div>
  );
}
