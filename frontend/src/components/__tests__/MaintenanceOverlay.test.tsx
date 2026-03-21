import { render, screen } from '@testing-library/react';
import MaintenanceOverlay from '../MaintenanceOverlay';
import { RemoteConfigProvider } from '../../context/RemoteConfigContext';
import { DEFAULT_CONFIG } from '../../types/remoteConfig';

let mockConfig = { ...DEFAULT_CONFIG };

vi.mock('../../hooks/useRemoteConfig', () => ({
  useRemoteConfig: () => ({ config: mockConfig, loading: false }),
}));

function renderWithProvider(ui: React.ReactElement) {
  return render(<RemoteConfigProvider>{ui}</RemoteConfigProvider>);
}

describe('MaintenanceOverlay', () => {
  afterEach(() => {
    mockConfig = { ...DEFAULT_CONFIG };
  });

  it('renders nothing when maintenance is false', () => {
    mockConfig.operations = { ...DEFAULT_CONFIG.operations, maintenance: false };
    const { container } = renderWithProvider(<MaintenanceOverlay />);
    expect(container.firstChild).toBeNull();
  });

  it('renders overlay when maintenance is true', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      operations: { maintenance: true, maintenance_message: 'Upgrading servers!', maintenance_until: null },
    };
    renderWithProvider(<MaintenanceOverlay />);
    expect(screen.getByText('Under Maintenance')).toBeInTheDocument();
    expect(screen.getByText(/Upgrading servers!/)).toBeInTheDocument();
  });

  it('shows maintenance_until time when provided', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      operations: {
        maintenance: true,
        maintenance_message: 'Down for updates.',
        maintenance_until: '2026-03-22T04:00:00Z',
      },
    };
    renderWithProvider(<MaintenanceOverlay />);
    expect(screen.getByText(/Back by/)).toBeInTheDocument();
  });
});
