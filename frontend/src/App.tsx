import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './index.css';
import OrganizerPage from './pages/OrganizerPage';
import PlayerPage from './pages/PlayerPage';
import SpectatorPage from './pages/SpectatorPage';
import PartyHubPage from './pages/PartyHubPage';
import RevelryAuthoringPage from './pages/RevelryAuthoringPage';
import ErrorBoundary from './components/ErrorBoundary';
import SettingsDrawer from './components/SettingsDrawer';
import { RemoteConfigProvider } from './context/RemoteConfigContext';
import { AuthProvider } from './context/AuthContext';
import MaintenanceOverlay from './components/MaintenanceOverlay';
import AnnouncementBanner from './components/AnnouncementBanner';

function AppShell() {
  const isHostAppSurface = window.location.pathname.startsWith('/revelry/');

  return (
    <>
      <MaintenanceOverlay />
      {!isHostAppSurface && <AnnouncementBanner />}
      {!isHostAppSurface && <SettingsDrawer />}
      <Routes>
        <Route path="/" element={<OrganizerPage />} />
        <Route path="/organizer" element={<OrganizerPage />} />
        <Route path="/join" element={<PlayerPage />} />
        <Route path="/join/:code" element={<PlayerPage />} />
        <Route path="/spectator" element={<SpectatorPage />} />
        <Route path="/tv" element={<SpectatorPage />} />
        <Route path="/tv/:code" element={<SpectatorPage />} />
        <Route path="/revelry/games" element={<PartyHubPage />} />
        <Route path="/revelry/author" element={<RevelryAuthoringPage />} />
      </Routes>
    </>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <RemoteConfigProvider>
        <AuthProvider>
        <Router basename={import.meta.env.BASE_URL}>
          <AppShell />
        </Router>
        </AuthProvider>
      </RemoteConfigProvider>
    </ErrorBoundary>
  );
}

export default App;
