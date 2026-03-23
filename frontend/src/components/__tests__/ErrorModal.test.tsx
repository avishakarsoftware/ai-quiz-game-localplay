import { render, screen, fireEvent } from '@testing-library/react';
import ErrorModal from '../ErrorModal';
import { RemoteConfigProvider } from '../../context/RemoteConfigContext';
import { type RemoteConfig, DEFAULT_CONFIG } from '../../types/remoteConfig';

// Mock the useRemoteConfig hook to control config
const mockConfig: RemoteConfig = {
  ...DEFAULT_CONFIG,
  feature_flags: { ...DEFAULT_CONFIG.feature_flags, show_upgrade_button: true },
  pricing: { ...DEFAULT_CONFIG.pricing },
};

vi.mock('../../hooks/useRemoteConfig', () => ({
  useRemoteConfig: () => ({ config: mockConfig, loading: false }),
}));

function renderWithProvider(ui: React.ReactElement) {
  return render(<RemoteConfigProvider>{ui}</RemoteConfigProvider>);
}

describe('ErrorModal', () => {
  it('renders title and message', () => {
    renderWithProvider(
      <ErrorModal title="Test Error" message="Something went wrong" onDismiss={() => {}} />
    );
    expect(screen.getByText('Test Error')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('calls onDismiss when OK button clicked', () => {
    const onDismiss = vi.fn();
    renderWithProvider(
      <ErrorModal title="Error" message="msg" onDismiss={onDismiss} />
    );
    fireEvent.click(screen.getByText('OK'));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('shows upgrade button when upgradeAvailable and feature flag enabled', () => {
    const onUpgrade = vi.fn();
    renderWithProvider(
      <ErrorModal
        title="Limit"
        message="Free tier limit reached"
        upgradeAvailable
        onDismiss={() => {}}
        onUpgrade={onUpgrade}
      />
    );
    const upgradeBtn = screen.getByText(/110 Sparks/);
    expect(upgradeBtn).toBeInTheDocument();
    expect(screen.getByText('Maybe Later')).toBeInTheDocument();
    fireEvent.click(upgradeBtn);
    expect(onUpgrade).toHaveBeenCalledOnce();
  });

  it('hides upgrade button when upgradeAvailable is false', () => {
    renderWithProvider(
      <ErrorModal title="Error" message="msg" upgradeAvailable={false} onDismiss={() => {}} />
    );
    expect(screen.queryByText(/110 Sparks/)).not.toBeInTheDocument();
    expect(screen.getByText('OK')).toBeInTheDocument();
  });

  it('calls onDismiss when backdrop clicked', () => {
    const onDismiss = vi.fn();
    const { container } = renderWithProvider(
      <ErrorModal title="Error" message="msg" onDismiss={onDismiss} />
    );
    // Click the backdrop (outermost div)
    fireEvent.click(container.firstChild!);
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('does not dismiss when modal content clicked', () => {
    const onDismiss = vi.fn();
    renderWithProvider(
      <ErrorModal title="Error" message="msg" onDismiss={onDismiss} />
    );
    fireEvent.click(screen.getByText('Error'));
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it('shows promo badge and strikethrough amount when promo is active', () => {
    // Set promo on the mock config
    mockConfig.pricing = {
      ...mockConfig.pricing,
      promo: {
        id: 'launch_2026',
        original_amount: 110,
        token_pack_amount: 220,
        badge: 'LAUNCH DEAL',
        expires: new Date(Date.now() + 86400000).toISOString(), // tomorrow
      },
    };
    renderWithProvider(
      <ErrorModal
        title="Limit"
        message="Out of sparks"
        upgradeAvailable
        onDismiss={() => {}}
        onUpgrade={() => {}}
      />
    );
    expect(screen.getByText('LAUNCH DEAL')).toBeInTheDocument();
    // The strikethrough original amount
    expect(screen.getByText('110')).toBeInTheDocument();
    // The promo token amount
    expect(screen.getByText('220')).toBeInTheDocument();
    // Button shows promo amount
    expect(screen.getByText(/Get 220 Sparks/)).toBeInTheDocument();
  });

  it('shows standard pricing when no promo is active', () => {
    // Clear promo
    mockConfig.pricing = {
      ...mockConfig.pricing,
      token_pack_amount: 110,
      promo: undefined,
    };
    renderWithProvider(
      <ErrorModal
        title="Limit"
        message="Out of sparks"
        upgradeAvailable
        onDismiss={() => {}}
        onUpgrade={() => {}}
      />
    );
    // No promo badge
    expect(screen.queryByText('LAUNCH DEAL')).not.toBeInTheDocument();
    // Standard amount in button
    expect(screen.getByText(/Get 110 Sparks/)).toBeInTheDocument();
  });
});
