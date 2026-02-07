// API and WebSocket URLs - use current hostname for network access
const API_HOST = window.location.hostname;
const API_URL = `http://${API_HOST}:8000`;
const WS_URL = `ws://${API_HOST}:8000`;

export { API_URL, WS_URL, API_HOST };
