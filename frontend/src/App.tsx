import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './index.css';
import OrganizerPage from './pages/OrganizerPage';
import PlayerPage from './pages/PlayerPage';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<OrganizerPage />} />
        <Route path="/organizer" element={<OrganizerPage />} />
        <Route path="/join" element={<PlayerPage />} />
      </Routes>
    </Router>
  );
}

export default App;
