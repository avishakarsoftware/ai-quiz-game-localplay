// API and WebSocket URLs.
// Local dev scripts set VITE_API_URL explicitly. Backend-served builds leave it
// empty so REST and WebSocket traffic use the current origin.
const explicitApiUrl = import.meta.env.VITE_API_URL;
const API_URL = explicitApiUrl || '';
const WS_URL = explicitApiUrl
  ? explicitApiUrl.replace(/^http/, 'ws')
  : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
const API_HOST = explicitApiUrl ? new URL(explicitApiUrl).hostname : window.location.hostname;

export { API_URL, WS_URL, API_HOST };
