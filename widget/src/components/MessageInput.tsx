import { useState } from 'react';
import { Send } from 'lucide-react';

export default function MessageInput({ onSend, disabled }: { onSend: (val: string) => void, disabled: boolean }) {
  const [val, setVal] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (val.trim() && !disabled) {
      onSend(val.trim());
      setVal('');
    }
  };

  return (
    <form className="input-container" onSubmit={handleSubmit}>
      <input 
        type="text" 
        value={val} 
        onChange={e => setVal(e.target.value)} 
        placeholder="Type your message..."
        disabled={disabled}
      />
      <button type="submit" className="send-button" disabled={!val.trim() || disabled}>
        <Send size={18} />
      </button>
    </form>
  );
}
