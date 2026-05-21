import { useEffect, useState } from 'react';
import ChatBubble from './components/ChatBubble.tsx';
import ChatPanel from './components/ChatPanel.tsx';
import type { WidgetConfig } from './types';

function App() {
  const [isOpen, setIsOpen] = useState(false);
  const [config, setConfig] = useState<WidgetConfig | null>(null);
  
  // Extract WIDGET_ID from URL parameter (e.g. ?widgetId=123)
  const queryParams = new URLSearchParams(window.location.search);
  const widgetId = queryParams.get('widgetId') || 'test-widget';
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    // Fetch widget config
    fetch(`${apiUrl}/widgets/${widgetId}/public`)
      .then(res => res.json())
      .then((data: WidgetConfig) => {
        setConfig(data);
        if (data.theme?.primary_color) {
          document.documentElement.style.setProperty('--primary-color', data.theme.primary_color);
        }
      })
      .catch(err => {
        console.error("Failed to fetch widget config", err);
        // Fallback for dev testing
        setConfig({
            theme: { primary_color: '#0066cc' },
            greeting: "Hi! How can I help you?",
            enabled_tools: []
        });
      });
  }, [widgetId, apiUrl]);

  useEffect(() => {
    // Resize iframe in parent window
    if (isOpen) {
      window.parent.postMessage({ type: 'resize', width: 400, height: 600 }, '*');
    } else {
      window.parent.postMessage({ type: 'resize', width: 100, height: 100 }, '*');
    }
  }, [isOpen]);

  if (!config) return null;

  return (
    <>
      {!isOpen && <ChatBubble onClick={() => setIsOpen(true)} />}
      {isOpen && <ChatPanel config={config} onClose={() => setIsOpen(false)} apiUrl={apiUrl} widgetId={widgetId} />}
    </>
  );
}

export default App;
