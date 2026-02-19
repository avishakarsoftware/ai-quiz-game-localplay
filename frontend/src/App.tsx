import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './index.css';
import OrganizerPage from './pages/OrganizerPage';
import PlayerPage from './pages/PlayerPage';
import SpectatorPage from './pages/SpectatorPage';
import ErrorBoundary from './components/ErrorBoundary';
import SettingsDrawer from './components/SettingsDrawer';

function App() {
  return (
    <ErrorBoundary>
      <Router basename={import.meta.env.BASE_URL}>
        <SettingsDrawer />
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
