// API and WebSocket URLs
// In production, set VITE_API_URL (e.g. https://api.revelryapp.me)
// In dev/LAN mode, auto-detect from current hostname
const API_URL = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;
const WS_URL = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/^http/, 'ws')
  : `ws://${window.location.hostname}:8000`;
const API_HOST = window.location.hostname;

export { API_URL, WS_URL, API_HOST };
