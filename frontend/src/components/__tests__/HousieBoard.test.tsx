import { fireEvent, render, screen } from '@testing-library/react';
import { HousieClaimButtons, HousieTicketGrid } from '../HousieBoard';
import type { HousiePattern, HousieTicket } from '../../types';

const ticket: HousieTicket = {
    id: 'ticket-1',
    player_id: 'player-1',
    player_name: 'Avi',
    layout: 'housie_3x9_15',
    rows: [
        [{ kind: 'number', value: 1, display: '1' }, null, { kind: 'number', value: 23, display: '23' }, null, { kind: 'number', value: 45, display: '45' }, null, { kind: 'number', value: 67, display: '67' }, null, { kind: 'number', value: 90, display: '90' }],
        [null, { kind: 'number', value: 12, display: '12' }, null, { kind: 'number', value: 34, display: '34' }, null, { kind: 'number', value: 56, display: '56' }, null, { kind: 'number', value: 78, display: '78' }, null],
        [{ kind: 'number', value: 8, display: '8' }, null, { kind: 'number', value: 28, display: '28' }, null, { kind: 'number', value: 48, display: '48' }, null, { kind: 'number', value: 68, display: '68' }, null, { kind: 'number', value: 88, display: '88' }],
    ],
};

const patterns: HousiePattern[] = [
    { id: 'full_house', label: 'Full House' },
    { id: 'top_line', label: 'Top Line' },
];

describe('HousieBoard', () => {
    it('fires ticket cell taps', () => {
        const onToggle = vi.fn();
        render(
            <HousieTicketGrid
                ticket={ticket}
                calledValues={new Set(['1'])}
                marked={new Set()}
                onToggle={onToggle}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Column 1, row 1, number 1, called' }));

        expect(onToggle).toHaveBeenCalledWith({ kind: 'number', value: 1, display: '1' });
    });

    it('fires unclaimed prize taps and disables claimed prizes', () => {
        const onClaim = vi.fn();
        render(
            <HousieClaimButtons
                patterns={patterns}
                winners={[{ pattern_id: 'top_line', label: 'Top Line', nickname: 'Avi', called_count: 12 }]}
                onClaim={onClaim}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Full House' }));

        expect(onClaim).toHaveBeenCalledWith('full_house');
        expect(screen.getByRole('button', { name: 'Top Line claimed by Avi' })).toBeDisabled();
    });
});
