import { useCallback } from 'react';
import { API_HOST } from '../config';

interface CastButtonProps {
  roomCode: string;
  joinUrl: string;
  displayUrl?: string; // Optional URL to display textually
}

export default function CastButton({ roomCode, joinUrl, displayUrl }: CastButtonProps) {

  const openTVView = useCallback(() => {
    // Use displayUrl if provided, otherwise derive from joinUrl
    const urlToDisplay = displayUrl || joinUrl.replace('http://', '').replace('https:///', '');

    const tvWindow = window.open('', 'LocalPlayTV', 'fullscreen=yes,toolbar=no,menubar=no,scrollbars=no');
    if (!tvWindow) return;

    tvWindow.document.write(getTVViewHTML(roomCode, joinUrl, urlToDisplay));
    tvWindow.document.close();
  }, [roomCode, joinUrl, displayUrl]);

  return (
    <button onClick={openTVView} className="btn btn-secondary w-full">
      📺 Open TV View
    </button>
  );
}

function getTVViewHTML(roomCode: string, joinUrl: string, displayUrl: string): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LocalPlay - Join Screen</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      min-height: 100vh;
      background: #000;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 40px;
    }
    .container {
      text-align: center;
      max-width: 900px;
    }
    h1 {
      font-size: 3.5rem;
      font-weight: 700;
      margin-bottom: 0.5rem;
      color: #fff;
    }
    .subtitle {
      font-size: 1.5rem;
      color: #8e8e93;
      margin-bottom: 3rem;
    }
    .main-content {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 60px;
      margin-bottom: 2rem;
    }
    .qr-section {
      text-align: center;
    }
    .qr-container {
      display: inline-block;
      padding: 20px;
      background: white;
      border-radius: 20px;
      margin-bottom: 1rem;
    }
    .qr-container canvas {
      display: block;
    }
    .or-divider {
      font-size: 1.5rem;
      color: #636366;
      font-weight: 500;
    }
    .code-section {
      text-align: center;
    }
    .room-code {
      font-family: 'SF Mono', 'Menlo', monospace;
      font-size: 5rem;
      font-weight: 800;
      letter-spacing: 0.1em;
      color: #fff;
      margin-bottom: 0.5rem;
    }
    .join-url {
      font-size: 1.3rem;
      color: #8e8e93;
    }
    .instructions {
      display: flex;
      gap: 40px;
      justify-content: center;
      margin-top: 3rem;
    }
    .step {
      background: #1c1c1e;
      border-radius: 16px;
      padding: 24px 32px;
      min-width: 140px;
    }
    .step-num {
      font-size: 2rem;
      font-weight: 700;
      color: #007AFF;
      margin-bottom: 8px;
    }
    .step-text {
      font-size: 1.1rem;
      color: #ebebf5;
    }
    .cast-hint {
      position: fixed;
      bottom: 24px;
      left: 0;
      right: 0;
      text-align: center;
      font-size: 0.9rem;
      color: #636366;
    }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js"></script>
</head>
<body>
  <div class="container">
    <h1>🎮 Join the Quiz!</h1>
    <p class="subtitle">Scan the QR code or enter the game PIN</p>
    
    <div class="main-content">
      <div class="qr-section">
        <div class="qr-container">
          <canvas id="qr"></canvas>
        </div>
        <p style="color: #8e8e93; font-size: 0.9rem;">Scan with your phone</p>
      </div>
      
      <div class="or-divider">or</div>
      
      <div class="code-section">
        <div class="room-code">${roomCode}</div>
        <p class="join-url">${displayUrl}</p>
      </div>
    </div>
    
    <div class="instructions">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-text">Scan or visit</div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-text">Enter nickname</div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-text">Get ready!</div>
      </div>
    </div>
  </div>
  
  <div class="cast-hint">
    💡 Use AirPlay or Chromecast from your browser menu to display on TV
  </div>
  
  <script>
    QRCode.toCanvas(document.getElementById('qr'), '${joinUrl}', {
      width: 200,
      margin: 0,
      color: { dark: '#000000', light: '#ffffff' }
    });
  </script>
</body>
</html>`;
}
