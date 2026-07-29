import { render, screen, fireEvent } from '@testing-library/react';
import GameSelectScreen from '../GameSelectScreen';
import { GAME_MODE_CONFIGS } from '../../../gameModes';

/**
 * The "One phone" filter (SPEC-PASS-AND-PLAY).
 *
 * With 38 games in the picker, spotting the one-phone games is not enough — a host whose guests
 * have no devices needs to NARROW to them. These tests pin two things that are easy to break:
 * the filter finds games via the catalog flag rather than a hardcoded id list, and it is
 * ORTHOGONAL to genre (a one-phone game must still appear under its own genre chip).
 */

describe('GameSelectScreen — One phone filter', () => {
    it('offers a One phone chip', () => {
        render(<GameSelectScreen onSelect={() => {}} />);
        expect(screen.getByTestId('category-chip-one_phone')).toBeInTheDocument();
    });

    it('narrows the list to pass-and-play games only', () => {
        render(<GameSelectScreen onSelect={() => {}} />);
        fireEvent.click(screen.getByTestId('category-chip-one_phone'));

        const passGames = GAME_MODE_CONFIGS.filter((m) => m.passAndPlay);
        expect(passGames.length).toBeGreaterThan(0);
        for (const game of passGames) {
            // The title span also holds the pill, so the text node is split — match on content.
            expect(
                screen.getByText((_t, el) => el?.className === 'game-select-title'
                    && (el.textContent || '').includes(game.title)),
            ).toBeInTheDocument();
        }

        // A per-phone game must be filtered OUT. Quiz is the safest control: it is always present
        // and is definitionally not pass-and-play.
        const quiz = GAME_MODE_CONFIGS.find((m) => m.id === 'quiz');
        if (quiz) {
            expect(
                screen.queryByText((_t, el) => el?.className === 'game-select-title'
                    && (el.textContent || '').includes(quiz.title)),
            ).not.toBeInTheDocument();
        }
    });

    it('is orthogonal to genre: a one-phone game still appears under All', () => {
        // The failure this prevents: implementing one_phone inside GAME_CATEGORY_BY_ID, which
        // permits a single category per game and would silently remove the game from its genre.
        render(<GameSelectScreen onSelect={() => {}} />);
        const impostor = GAME_MODE_CONFIGS.find((m) => m.id === 'impostor');
        expect(impostor).toBeDefined();
        expect(
            screen.getByText((_t, el) => el?.className === 'game-select-title'
                && (el.textContent || '').includes(impostor!.title)),
        ).toBeInTheDocument();
    });

    it('shows the pill on pass-and-play tiles so they are recognisable without filtering', () => {
        render(<GameSelectScreen onSelect={() => {}} />);
        for (const game of GAME_MODE_CONFIGS.filter((m) => m.passAndPlay)) {
            expect(screen.getByTestId(`one-phone-badge-${game.id}`)).toBeInTheDocument();
        }
    });

    it('does not show the AI sparkle on one-phone games in local fallback mode', () => {
        render(<GameSelectScreen onSelect={() => {}} />);

        const impostorTitle = screen.getByText((_text, el) => el?.className === 'game-select-title'
            && (el.textContent || '').includes('Impostor'));
        expect(impostorTitle.textContent).not.toContain('✨');

        const aiQuizTitle = screen.getByText((_text, el) => el?.className === 'game-select-title'
            && (el.textContent || '').includes('AI Quiz'));
        expect(aiQuizTitle.textContent).toContain('✨');
    });
});
