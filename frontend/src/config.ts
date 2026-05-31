// API and WebSocket URLs.
// Local dev scripts set VITE_API_URL explicitly. Backend-served builds leave it
// empty so REST and WebSocket traffic use the current origin.
const explicitApiUrl = import.meta.env.VITE_API_URL;
const API_URL = explicitApiUrl || '';
const WS_URL = explicitApiUrl
  ? explicitApiUrl.replace(/^http/, 'ws')
  : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
const API_HOST = explicitApiUrl ? new URL(explicitApiUrl).hostname : window.location.hostname;
const ENABLE_BINGO =
  import.meta.env.VITE_ENABLE_BINGO === 'true'
  || API_HOST === 'localhost'
  || API_HOST === '127.0.0.1'
  || API_HOST.includes('gamma');

export { API_URL, WS_URL, API_HOST, ENABLE_BINGO };
