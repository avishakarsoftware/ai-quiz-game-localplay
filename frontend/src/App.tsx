import { useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './index.css';
import OrganizerPage from './pages/OrganizerPage';
import PlayerPage from './pages/PlayerPage';
import SpectatorPage from './pages/SpectatorPage';
import ErrorBoundary from './components/ErrorBoundary';
import { soundManager } from './utils/sound';

function MuteToggle() {
  const [muted, setMuted] = useState(soundManager.muted);
  return (
    <button
      onClick={() => setMuted(soundManager.toggleMute())}
      className="mute-toggle"
      title={muted ? 'Unmute' : 'Mute'}
    >
      {muted ? '🔇' : '🔊'}
    </button>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <MuteToggle />
        <Routes>
          <Route path="/" element={<OrganizerPage />} />
          <Route path="/organizer" element={<OrganizerPage />} />
          <Route path="/join" element={<PlayerPage />} />
          <Route path="/spectator" element={<SpectatorPage />} />
        </Routes>
      </Router>
    </ErrorBoundary>
  );
}

export default App;
