import { useEffect, useState } from 'react';

export default function StreamingMessage({ apiUrl, prompt, conversationId, widgetId, onComplete }: { apiUrl: string, prompt: string, conversationId: string, widgetId: string, onComplete: (t: string, id?: string) => void }) {
  const [text, setText] = useState('');

  useEffect(() => {
    let active = true;
    let fullText = '';
    let newConvId = conversationId;

    const streamResponse = async () => {
      try {
        const response = await fetch(`${apiUrl}/chat/message`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ conversation_id: conversationId || undefined, message: prompt, widget_id: widgetId })
        });

        if (!response.body) throw new Error("No readable stream");

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          
          if (chunk.startsWith('CONVERSATION_ID:')) {
            newConvId = chunk.split(':')[1].trim();
            continue;
          }

          fullText += chunk;
          if (active) setText(fullText);
        }
      } catch (e) {
        console.error(e);
        fullText = "Error connecting to the copilot.";
      } finally {
        if (active) {
          onComplete(fullText, newConvId);
        }
      }
    };

    streamResponse();

    return () => { active = false; };
  }, [apiUrl, conversationId, onComplete, prompt, widgetId]);

  return (
    <div className="message assistant">
      {text}
      <span style={{ animation: 'blink 1s step-end infinite' }}>▌</span>
    </div>
  );
}
