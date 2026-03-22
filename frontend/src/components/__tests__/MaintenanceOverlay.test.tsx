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
      operations: { ...DEFAULT_CONFIG.operations, maintenance: true, maintenance_message: 'Upgrading servers!' },
    };
    renderWithProvider(<MaintenanceOverlay />);
    expect(screen.getByText('Under Maintenance')).toBeInTheDocument();
    expect(screen.getByText(/Upgrading servers!/)).toBeInTheDocument();
  });

  it('shows maintenance_until time when provided', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      operations: {
        ...DEFAULT_CONFIG.operations,
        maintenance: true,
        maintenance_message: 'Down for updates.',
        maintenance_until: '2026-03-22T04:00:00Z',
      },
    };
    renderWithProvider(<MaintenanceOverlay />);
    expect(screen.getByText(/Back by/)).toBeInTheDocument();
  });

  it('shows kill switch overlay when kill_switch is true', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      operations: { ...DEFAULT_CONFIG.operations, kill_switch: true, kill_switch_message: 'App has been disabled.' },
    };
    renderWithProvider(<MaintenanceOverlay />);
    expect(screen.getByText('App Unavailable')).toBeInTheDocument();
    expect(screen.getByText('App has been disabled.')).toBeInTheDocument();
  });

  it('shows default kill switch message when none provided', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      operations: { ...DEFAULT_CONFIG.operations, kill_switch: true },
    };
    renderWithProvider(<MaintenanceOverlay />);
    expect(screen.getByText('App Unavailable')).toBeInTheDocument();
    expect(screen.getByText(/temporarily unavailable/)).toBeInTheDocument();
  });

  it('kill switch takes priority over maintenance', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      operations: { ...DEFAULT_CONFIG.operations, kill_switch: true, maintenance: true, maintenance_message: 'Maintenance!' },
    };
    renderWithProvider(<MaintenanceOverlay />);
    expect(screen.getByText('App Unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Under Maintenance')).toBeNull();
  });

  it('shows force update when app version is below min_supported_version', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      operations: { ...DEFAULT_CONFIG.operations, min_supported_version: '99.0.0' },
    };
    renderWithProvider(<MaintenanceOverlay />);
    expect(screen.getByText('Update Required')).toBeInTheDocument();
    expect(screen.getByText(/update to the latest version/)).toBeInTheDocument();
  });

  it('does not show force update when app version meets min_supported_version', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      operations: { ...DEFAULT_CONFIG.operations, min_supported_version: '1.0.0' },
    };
    const { container } = renderWithProvider(<MaintenanceOverlay />);
    expect(container.firstChild).toBeNull();
  });

  it('kill switch takes priority over force update', () => {
    mockConfig = {
      ...DEFAULT_CONFIG,
      operations: { ...DEFAULT_CONFIG.operations, kill_switch: true, min_supported_version: '99.0.0' },
    };
    renderWithProvider(<MaintenanceOverlay />);
    expect(screen.getByText('App Unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Update Required')).toBeNull();
  });
});
