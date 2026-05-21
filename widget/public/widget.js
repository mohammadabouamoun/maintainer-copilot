(function() {
  const script = document.currentScript;
  if (!script) return;
  
  const widgetId = script.getAttribute('data-widget-id');
  const scriptUrl = new URL(script.src);
  const apiBase = scriptUrl.origin; // http://localhost:8000
  
  // For development, Vite is running on port 3000. 
  // In production, the static files would be served on the same domain or a configured CDN.
  // We check if we are on localhost to determine the dev port.
  const widgetBase = apiBase.includes('localhost') ? apiBase.replace('8000', '3000') : apiBase;

  const iframe = document.createElement('iframe');
  iframe.id = 'maintainer-copilot-widget';
  iframe.src = `${widgetBase}/?widgetId=${widgetId}`;
  iframe.style.cssText = 'position:fixed;bottom:0;right:0;width:100px;height:100px;border:none;z-index:999999;transition:width 0.3s ease, height 0.3s ease;background:transparent;';
  
  document.body.appendChild(iframe);

  window.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'resize') {
      iframe.style.width = `${e.data.width}px`;
      iframe.style.height = `${e.data.height}px`;
    }
  });
})();
