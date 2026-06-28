import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import PartyQuestsSetupScreen, { defaultPartyQuestsConfig, type PartyQuestSetupConfig } from '../organizer/PartyQuestsSetupScreen';

const providers = [{ id: 'gemini', name: 'Gemini 2.5 Flash Lite', description: '', available: true }];

describe('PartyQuestsSetupScreen', () => {
    it('renders editable numbered quest cards and lets hosts reorder them', () => {
        const initialConfig = defaultPartyQuestsConfig('mingling');
        render(
            <PartyQuestsSetupScreen
                initialConfig={initialConfig}
                provider="gemini"
                setProvider={() => {}}
                providers={providers}
                onGenerateQuests={async () => null}
                onCreate={() => {}}
                onBack={() => {}}
            />,
        );

        const firstQuest = screen.getByLabelText('Quest 1') as HTMLTextAreaElement;
        expect(firstQuest.value).toBe(initialConfig.quests[0].display);

        fireEvent.click(screen.getAllByRole('button', { name: 'Down' })[0]);

        expect((screen.getByLabelText('Quest 1') as HTMLTextAreaElement).value).toBe(initialConfig.quests[1].display);
        expect((screen.getByLabelText('Quest 2') as HTMLTextAreaElement).value).toBe(initialConfig.quests[0].display);
    });

    it('replaces the quest block with generated AI quests for host review', async () => {
        const generated: PartyQuestSetupConfig = {
            ...defaultPartyQuestsConfig('birthday'),
            game_title: 'Generated Party Quests',
            quests: [
                { display: 'Find someone who can recommend a party song.', category: 'birthday', points: 100 },
                { display: 'Ask someone for a tiny toast idea.', category: 'birthday', points: 100 },
                { display: 'Meet someone who knows the guest of honor well.', category: 'birthday', points: 150 },
            ],
        };
        const onGenerateQuests = vi.fn(async () => generated);
        render(
            <PartyQuestsSetupScreen
                initialConfig={defaultPartyQuestsConfig('mingling')}
                provider="gemini"
                setProvider={() => {}}
                providers={providers}
                onGenerateQuests={onGenerateQuests}
                onCreate={() => {}}
                onBack={() => {}}
            />,
        );

        fireEvent.change(screen.getByPlaceholderText('Example: outdoor birthday, cousins and school friends, silly but family friendly'), {
            target: { value: 'birthday cousins and family friends' },
        });
        fireEvent.click(screen.getByRole('button', { name: 'Generate Quest Block' }));

        await waitFor(() => expect(onGenerateQuests).toHaveBeenCalled());
        expect((screen.getByLabelText('Quest 1') as HTMLTextAreaElement).value).toBe('Find someone who can recommend a party song.');
        expect(screen.getByText('3 quests available')).toBeInTheDocument();
    });
});
