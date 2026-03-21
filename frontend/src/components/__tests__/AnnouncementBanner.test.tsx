import { render, screen, fireEvent } from '@testing-library/react';
import AnnouncementBanner from '../AnnouncementBanner';
import { RemoteConfigProvider } from '../../context/RemoteConfigContext';
import { DEFAULT_CONFIG } from '../../types/remoteConfig';

let mockConfig = { ...DEFAULT_CONFIG };

vi.mock('../../hooks/useRemoteConfig', () => ({
  useRemoteConfig: () => ({ config: mockConfig, loading: false }),
}));

// Mock localStorage for tests
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true });

function renderWithProvider(ui: React.ReactElement) {
  return render(<RemoteConfigProvider>{ui}</RemoteConfigProvider>);
}

describe('AnnouncementBanner', () => {
  beforeEach(() => {
    localStorageMock.clear();
    mockConfig = { ...DEFAULT_CONFIG, announcements: [] };
  });

  it('renders nothing when no announcements', () => {
    const { container } = renderWithProvider(<AnnouncementBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('renders announcement text', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      announcements: [{ id: 'test-1', text: 'New game mode available!', type: 'info' as const, dismissible: true }],
    };
    renderWithProvider(<AnnouncementBanner />);
    expect(screen.getByText('New game mode available!')).toBeInTheDocument();
  });

  it('dismisses announcement on click', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      announcements: [{ id: 'test-2', text: 'Dismiss me', type: 'info' as const, dismissible: true }],
    };
    renderWithProvider(<AnnouncementBanner />);
    expect(screen.getByText('Dismiss me')).toBeInTheDocument();

    fireEvent.click(screen.getByText('×'));
    expect(screen.queryByText('Dismiss me')).not.toBeInTheDocument();

    // Verify persisted
    const dismissed = JSON.parse(localStorageMock.getItem('revelry_dismissed_announcements') || '[]');
    expect(dismissed).toContain('test-2');
  });

  it('does not show dismiss button for non-dismissible announcements', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      announcements: [{ id: 'test-3', text: 'Important!', type: 'warning' as const, dismissible: false }],
    };
    renderWithProvider(<AnnouncementBanner />);
    expect(screen.getByText('Important!')).toBeInTheDocument();
    expect(screen.queryByText('×')).not.toBeInTheDocument();
  });

  it('filters out previously dismissed announcements', () => {
    localStorageMock.setItem('revelry_dismissed_announcements', JSON.stringify(['old-1']));
    mockConfig = {
      ...DEFAULT_CONFIG,
      announcements: [
        { id: 'old-1', text: 'Already dismissed', type: 'info' as const, dismissible: true },
        { id: 'new-1', text: 'Still showing', type: 'info' as const, dismissible: true },
      ],
    };
    renderWithProvider(<AnnouncementBanner />);
    expect(screen.queryByText('Already dismissed')).not.toBeInTheDocument();
    expect(screen.getByText('Still showing')).toBeInTheDocument();
  });
});
