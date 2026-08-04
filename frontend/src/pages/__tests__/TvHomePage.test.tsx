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
                    bucket: 'tv_remote',
                    companion_mode: 'none',
                    min_companion_devices: 0,
                    private_screen: false,
                    text_input_for_customization: false,
                    requirement_label: 'TV only',
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
                    bucket: 'shared_phone',
                    companion_mode: 'shared_phone',
                    min_companion_devices: 1,
                    private_screen: true,
                    text_input_for_customization: false,
                    requirement_label: 'TV + 1 shared phone',
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
                    bucket: 'phone_host',
                    companion_mode: 'phone_host',
                    min_companion_devices: 0,
                    private_screen: false,
                    text_input_for_customization: true,
                    requirement_label: 'Start on phone',
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
                    bucket: 'per_player_phone',
                    companion_mode: 'per_player_phone',
                    min_companion_devices: 2,
                    private_screen: false,
                    text_input_for_customization: true,
                    requirement_label: 'TV + player phones',
                    reason_chip: 'Needs 2 phones',
                },
            },
        ],
    };
}

const tvRoomState = {
    roomCode: '', joinUrl: '', players: [] as Array<{ nickname: string }>,
    connectedPhones: 0, status: 'idle' as const, error: '',
    host: vi.fn(), leave: vi.fn(),
};

vi.mock('../useTvRoom', () => ({ useTvRoom: () => tvRoomState }));

function mockTvRoom(patch: Partial<typeof tvRoomState>) {
    Object.assign(tvRoomState, patch);
}

beforeEach(() => {
    mockTvRoom({ roomCode: '', joinUrl: '', players: [], connectedPhones: 0, status: 'idle', error: '' });
});

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
        // The phone count comes from the TV's own organizer socket via useTvRoom. There is no
        // manual stepper any more: a fake counter would un-grey a game that then cannot start.
        mockTvRoom({ connectedPhones: 1 });
        render(<TvHomePage />);
        await screen.findByRole('button', { name: /Housie/ });

        expect(screen.getByRole('button', { name: /Impostor/ })).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: /Impostor/ }));
        expect(screen.getByText('TV + 1 shared phone')).toBeInTheDocument();
    });

    it('keeps phone-host games visible in their own filter with a handoff sheet', async () => {
        render(<TvHomePage />);
        await screen.findByRole('button', { name: /Housie/ });

        fireEvent.click(screen.getByRole('button', { name: 'Phone host' }));
        fireEvent.click(screen.getByRole('button', { name: /Photo Clue/ }));

        expect(screen.getByRole('heading', { name: 'Play this one on your phone' })).toBeInTheDocument();
        // The reason comes from the catalog's own tv_play_note, so it stays correct if the
        // classification changes rather than being duplicated copy.
        expect(screen.getAllByText(/camera|capture/i).length).toBeGreaterThan(0);
        // THE point of this sheet (SPEC-TV-APP §4b): a game the TV can never host sends the host
        // to the APP, not to a join link. A join QR here would be a dead end — there is no room
        // on the TV to join.
        const qr = screen.getByTestId('qr-code');
        expect(qr).toHaveTextContent(/play\.google\.com|apps\.apple\.com/);
        expect(qr).not.toHaveTextContent('/join');
        // And it must promise sparks carry over, or a host assumes installing means paying twice.
        expect(screen.getByText(/sparks come with you/i)).toBeInTheDocument();
    });

    it('opens game rules from the selected sheet', async () => {
        render(<TvHomePage />);
        await screen.findByRole('button', { name: /Housie/ });

        fireEvent.click(screen.getByRole('button', { name: /Housie/ }));
        fireEvent.click(screen.getByRole('button', { name: 'Rules' }));

        await waitFor(() => expect(screen.getByRole('dialog', { name: 'Housie Rules' })).toBeInTheDocument());
    });
});
