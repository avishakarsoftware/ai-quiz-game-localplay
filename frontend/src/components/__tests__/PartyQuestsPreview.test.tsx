import { fireEvent, render, screen } from '@testing-library/react';
import PartyQuestsPreview from '../PartyQuestsPreview';
import { defaultPartyQuestsConfig } from '../organizer/PartyQuestsSetupScreen';

describe('PartyQuestsPreview', () => {
    it('previews player, host, and TV surfaces without creating a room', () => {
        const onBack = vi.fn();
        const onEdit = vi.fn();
        const onStart = vi.fn();
        render(
            <PartyQuestsPreview
                config={{ ...defaultPartyQuestsConfig('birthday'), game_title: 'Birthday Missions' }}
                onBack={onBack}
                onEdit={onEdit}
                onStart={onStart}
            />,
        );

        expect(screen.getByText("Maya's sample board")).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Host' }));
        expect(screen.getByText('Host controls')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'TV' }));
        expect(screen.getByText('Party screen · Private quests stay on phones')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Edit setup' }));
        fireEvent.click(screen.getByRole('button', { name: 'Back to games' }));
        fireEvent.click(screen.getByRole('button', { name: 'Start this setup' }));
        expect(onEdit).toHaveBeenCalledOnce();
        expect(onBack).toHaveBeenCalledOnce();
        expect(onStart).toHaveBeenCalledOnce();
    });
});
