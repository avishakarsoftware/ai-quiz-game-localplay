import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import TvHomePage from '../TvHomePage';

const mockApiFetch = vi.fn();

vi.mock('../../utils/api', () => ({
    apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

vi.mock('qrcode.react', () => ({
    QRCodeSVG: ({ value }: { value: string }) => <div data-testid="qr-code">{value}</div>,
}));

function catalogFixture() {
    return {
        games: [
            {
                id: 'housie',
                game_type: 'housie',
                title: 'Housie',
                description: 'Classic calls',
                launchable: true,
                tv_capability: {
                    hostable: true,
                    companion_mode: 'none',
                    min_companion_devices: 0,
                    private_screen: false,
                    text_input_for_customization: false,
                    reason_chip: 'TV ready',
                },
            },
            {
                id: 'impostor',
                game_type: 'impostor',
                title: 'Impostor',
                description: 'One phone, passed around',
                launchable: true,
                tv_capability: {
                    hostable: true,
                    companion_mode: 'shared_phone',
                    min_companion_devices: 1,
                    private_screen: true,
                    text_input_for_customization: false,
                    reason_chip: 'Needs 1 shared phone',
                },
            },
            {
                id: 'photo_clue',
                game_type: 'photo_clue',
                title: 'Photo Clue',
                description: 'Camera clues',
                launchable: true,
                tv_capability: {
                    hostable: false,
                    companion_mode: 'phone_host',
                    min_companion_devices: 0,
                    private_screen: false,
                    text_input_for_customization: true,
                    reason_chip: 'Start from a phone',
                },
            },
            {
                id: 'drawing',
                game_type: 'drawing',
                title: 'Drawing Game',
                description: 'Draw and guess',
                launchable: true,
                tv_capability: {
                    hostable: true,
                    companion_mode: 'per_player_phone',
                    min_companion_devices: 2,
                    private_screen: false,
                    text_input_for_customization: true,
                    reason_chip: 'Needs 2 phones',
                },
            },
        ],
    };
}

describe('TvHomePage', () => {
    beforeEach(() => {
        mockApiFetch.mockResolvedValue(Response.json(catalogFixture()));
    });

    afterEach(() => {
        vi.clearAllMocks();
    });

    it('loads the capability-aware catalog and starts on games playable now', async () => {
        render(<TvHomePage />);

        expect(await screen.findByRole('button', { name: /Housie/ })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Impostor/ })).toBeNull();
        expect(screen.getByRole('button', { name: /Play now/ })).toHaveClass('active');
    });

    it('shows shared-phone games once a phone is connected', async () => {
        render(<TvHomePage />);
        await screen.findByRole('button', { name: /Housie/ });

        fireEvent.click(screen.getByRole('button', { name: '1' }));

        expect(screen.getByRole('button', { name: /Impostor/ })).toBeInTheDocument();
        expect(screen.getByText('Needs 1 shared phone')).toBeInTheDocument();
    });

    it('keeps phone-host games visible in their own filter with a handoff sheet', async () => {
        render(<TvHomePage />);
        await screen.findByRole('button', { name: /Housie/ });

        fireEvent.click(screen.getByRole('button', { name: 'Phone host' }));
        fireEvent.click(screen.getByRole('button', { name: /Photo Clue/ }));

        expect(screen.getByRole('heading', { name: 'Use a phone for this one' })).toBeInTheDocument();
        expect(screen.getByText(/Photo capture and upload/)).toBeInTheDocument();
        expect(screen.getByTestId('qr-code')).toHaveTextContent('/join');
    });

    it('opens game rules from the selected sheet', async () => {
        render(<TvHomePage />);
        await screen.findByRole('button', { name: /Housie/ });

        fireEvent.click(screen.getByRole('button', { name: /Housie/ }));
        fireEvent.click(screen.getByRole('button', { name: 'Rules' }));

        await waitFor(() => expect(screen.getByRole('dialog', { name: 'Housie Rules' })).toBeInTheDocument());
    });
});
