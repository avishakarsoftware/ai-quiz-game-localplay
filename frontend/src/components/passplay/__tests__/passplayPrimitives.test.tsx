import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import PrivacyGate from '../PrivacyGate';
import PassScreen from '../PassScreen';
import SeatRosterSetup from '../SeatRosterSetup';
import GroupScreenFrame from '../GroupScreenFrame';

/**
 * Pass-and-play primitives (SPEC-PASS-AND-PLAY §1).
 *
 * The security-relevant assertions are in PrivacyGate: with one device serving every player, a
 * secret that reaches the DOM early is a secret the next person can find. These tests assert it is
 * ABSENT from the document, not merely visually hidden.
 */

const SECRET = 'PINEAPPLE-42';

describe('PrivacyGate', () => {
    it('does not put the secret in the DOM at all before reveal', () => {
        const { container } = render(
            <PrivacyGate seatName="Maya" onDone={() => {}}>
                <p>{SECRET}</p>
            </PrivacyGate>,
        );
        // Not `toBeVisible` — a display:none secret is still in the DOM, still in the a11y tree,
        // and still one devtools glance from the next player.
        expect(container.textContent).not.toContain(SECRET);
        expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
    });

    it('names who should be looking, so the wrong person self-corrects', () => {
        render(<PrivacyGate seatName="Leo" seatEmoji="🦊" onDone={() => {}}><p>{SECRET}</p></PrivacyGate>);
        expect(screen.getByTestId('privacy-gate-seat-name')).toHaveTextContent('Leo');
    });

    it('a tap does NOT reveal — only a sustained hold does', async () => {
        vi.useFakeTimers();
        try {
            const { container } = render(
                <PrivacyGate seatName="Maya" holdMs={400} onDone={() => {}}>
                    <p>{SECRET}</p>
                </PrivacyGate>,
            );
            const hold = screen.getByTestId('privacy-gate-hold');
            // A tap is exactly what a phone being handed over receives by accident.
            act(() => { fireEvent.pointerDown(hold); });
            fireEvent.pointerUp(hold);
            act(() => { vi.advanceTimersByTime(1000); });
            expect(container.textContent).not.toContain(SECRET);
        } finally {
            vi.useRealTimers();
        }
    });

    it('reveals after the hold completes', async () => {
        vi.useFakeTimers();
        try {
            render(
                <PrivacyGate seatName="Maya" holdMs={400} onDone={() => {}}>
                    <p>{SECRET}</p>
                </PrivacyGate>,
            );
            act(() => { fireEvent.pointerDown(screen.getByTestId('privacy-gate-hold')); });
            act(() => { vi.advanceTimersByTime(450); });
        } finally {
            vi.useRealTimers();
        }
        await waitFor(() => expect(screen.getByTestId('privacy-gate-revealed')).toBeInTheDocument());
        expect(screen.getByText(SECRET)).toBeInTheDocument();
    });

    it('releasing early cancels the reveal', () => {
        vi.useFakeTimers();
        try {
            const { container } = render(
                <PrivacyGate seatName="Maya" holdMs={400} onDone={() => {}}>
                    <p>{SECRET}</p>
                </PrivacyGate>,
            );
            const hold = screen.getByTestId('privacy-gate-hold');
            act(() => { fireEvent.pointerDown(hold); });
            act(() => { vi.advanceTimersByTime(200); });      // let go before the threshold
            fireEvent.pointerUp(hold);
            act(() => { vi.advanceTimersByTime(1000); });
            expect(container.textContent).not.toContain(SECRET);
        } finally {
            vi.useRealTimers();
        }
    });

    it('the pointer leaving the button cancels the reveal', () => {
        vi.useFakeTimers();
        try {
            const { container } = render(
                <PrivacyGate seatName="Maya" holdMs={400} onDone={() => {}}>
                    <p>{SECRET}</p>
                </PrivacyGate>,
            );
            const hold = screen.getByTestId('privacy-gate-hold');
            act(() => { fireEvent.pointerDown(hold); });
            fireEvent.pointerLeave(hold);
            act(() => { vi.advanceTimersByTime(1000); });
            expect(container.textContent).not.toContain(SECRET);
        } finally {
            vi.useRealTimers();
        }
    });

    it('re-shields and un-renders the secret when done, then reports done', async () => {
        const onDone = vi.fn();
        vi.useFakeTimers();
        try {
            render(
                <PrivacyGate seatName="Maya" holdMs={400} onDone={onDone}>
                    <p>{SECRET}</p>
                </PrivacyGate>,
            );
            act(() => { fireEvent.pointerDown(screen.getByTestId('privacy-gate-hold')); });
            act(() => { vi.advanceTimersByTime(450); });
        } finally {
            vi.useRealTimers();
        }
        const done = await screen.findByTestId('privacy-gate-done');
        fireEvent.click(done);
        expect(onDone).toHaveBeenCalledOnce();
        // The next player must receive a shielded screen, not the previous person's role.
        expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
        expect(screen.getByTestId('privacy-gate-shield')).toBeInTheDocument();
    });

    it('re-shields when the seat changes, so a pass mid-reveal cannot leak', async () => {
        vi.useFakeTimers();
        const { rerender } = render(
            <PrivacyGate seatName="Maya" holdMs={400} onDone={() => {}}><p>{SECRET}</p></PrivacyGate>,
        );
        try {
            act(() => { fireEvent.pointerDown(screen.getByTestId('privacy-gate-hold')); });
            act(() => { vi.advanceTimersByTime(450); });
        } finally {
            vi.useRealTimers();
        }
        await screen.findByTestId('privacy-gate-revealed');

        rerender(<PrivacyGate seatName="Leo" holdMs={400} onDone={() => {}}><p>{SECRET}</p></PrivacyGate>);
        expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
        expect(screen.getByTestId('privacy-gate-shield')).toBeInTheDocument();
    });
});

describe('PassScreen', () => {
    it('names the next player and nothing else sensitive', () => {
        const { container } = render(
            <PassScreen seatName="Ada" seatEmoji="🐙" context="Round 2 of 3" onReady={() => {}} />,
        );
        expect(screen.getByTestId('pass-screen-seat')).toHaveTextContent('Ada');
        expect(container.textContent).toContain('Round 2 of 3');
        // This screen is the one most likely to be visible to the whole room.
        expect(container.textContent).not.toMatch(/impostor|secret/i);
    });

    it('advances only on explicit confirmation that the phone changed hands', () => {
        const onReady = vi.fn();
        render(<PassScreen seatName="Ada" onReady={onReady} />);
        fireEvent.click(screen.getByTestId('pass-screen-ready'));
        expect(onReady).toHaveBeenCalledOnce();
    });
});

describe('SeatRosterSetup', () => {
    it('shows enough rows to reach the minimum up front', () => {
        render(<SeatRosterSetup minSeats={3} maxSeats={12} onStart={() => {}} />);
        expect(screen.getByTestId('seat-input-0')).toBeInTheDocument();
        expect(screen.getByTestId('seat-input-2')).toBeInTheDocument();
    });

    it('cannot start below the minimum, and says how many are needed', () => {
        render(<SeatRosterSetup minSeats={3} maxSeats={12} onStart={() => {}} />);
        expect(screen.getByTestId('seat-start')).toBeDisabled();
        expect(screen.getByTestId('seat-need-more')).toHaveTextContent('at least 3');
    });

    it('starts once enough names are filled, passing only the filled ones', () => {
        const onStart = vi.fn();
        render(<SeatRosterSetup minSeats={3} maxSeats={12} onStart={onStart} />);
        fireEvent.change(screen.getByTestId('seat-input-0'), { target: { value: 'Maya' } });
        fireEvent.change(screen.getByTestId('seat-input-1'), { target: { value: 'Leo' } });
        fireEvent.change(screen.getByTestId('seat-input-2'), { target: { value: '  Ada  ' } });
        fireEvent.click(screen.getByTestId('seat-start'));
        expect(onStart).toHaveBeenCalledWith(['Maya', 'Leo', 'Ada'], expect.any(Array));
    });

    it('allows duplicate names, because two guests really can both be Sam', () => {
        const onStart = vi.fn();
        render(<SeatRosterSetup minSeats={3} maxSeats={12} onStart={onStart} />);
        for (const i of [0, 1, 2]) {
            fireEvent.change(screen.getByTestId(`seat-input-${i}`), { target: { value: 'Sam' } });
        }
        fireEvent.click(screen.getByTestId('seat-start'));
        expect(onStart).toHaveBeenCalledWith(['Sam', 'Sam', 'Sam'], expect.any(Array));
    });

    it('caps the roster at the maximum', () => {
        render(<SeatRosterSetup minSeats={3} maxSeats={4} onStart={() => {}} />);
        fireEvent.click(screen.getByTestId('seat-add'));
        expect(screen.getByTestId('seat-add')).toBeDisabled();
    });

    it('removing never drops below the minimum row count', () => {
        render(<SeatRosterSetup minSeats={3} maxSeats={12} onStart={() => {}} />);
        fireEvent.change(screen.getByTestId('seat-input-0'), { target: { value: 'Maya' } });
        fireEvent.click(screen.getByTestId('seat-remove-0'));
        // Row survives (cleared, not deleted) so the form can't become unstartable.
        expect(screen.getByTestId('seat-input-2')).toBeInTheDocument();
        expect((screen.getByTestId('seat-input-0') as HTMLInputElement).value).toBe('');
    });

    it('publishes roster changes so a reconnecting host does not lose their typing', () => {
        const onChange = vi.fn();
        render(<SeatRosterSetup minSeats={3} maxSeats={12} onStart={() => {}} onChange={onChange} />);
        fireEvent.change(screen.getByTestId('seat-input-0'), { target: { value: 'Maya' } });
        expect(onChange).toHaveBeenCalledWith(['Maya'], expect.any(Array));
    });

    it('sells the no-download angle, which is the whole point of the mode', () => {
        const { container } = render(<SeatRosterSetup minSeats={3} maxSeats={12} onStart={() => {}} />);
        expect(container.textContent).toMatch(/one phone/i);
    });
});

describe('GroupScreenFrame', () => {
    it('renders a table-readable title and its children', () => {
        render(
            <GroupScreenFrame title="Who's faking?" subtitle="Discuss, then vote">
                <p>vote list</p>
            </GroupScreenFrame>,
        );
        expect(screen.getByTestId('group-screen')).toBeInTheDocument();
        expect(screen.getByText("Who's faking?")).toBeInTheDocument();
        expect(screen.getByText('Discuss, then vote')).toBeInTheDocument();
        expect(screen.getByText('vote list')).toBeInTheDocument();
    });
});
