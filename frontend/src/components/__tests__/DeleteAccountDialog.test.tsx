import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import DeleteAccountDialog from '../DeleteAccountDialog';

/**
 * SPEC-ACCOUNT-DELETION §4.2.1 — the unspent-Sparks warning.
 *
 * Losing paid-for currency is the least obvious consequence of deletion and the one users are
 * most likely to regret, so the warning must be concrete and conditional: the exact live
 * balance when there is one, nothing at all when there isn't (warning about losing nothing
 * trains people to skip the dialog).
 */

function mockBalance(balance: number | null, ok = true) {
    globalThis.fetch = vi.fn((url: string, init?: RequestInit) => {
        if (String(url).includes('/tokens/balance')) {
            return Promise.resolve({
                ok,
                status: ok ? 200 : 500,
                json: () => Promise.resolve(balance === null ? {} : { balance }),
            } as Response);
        }
        if (String(url).includes('/account') && init?.method === 'DELETE') {
            return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ deleted: true }) } as Response);
        }
        return Promise.reject(new Error(`unexpected fetch: ${url}`));
    }) as unknown as typeof fetch;
}

describe('DeleteAccountDialog — Sparks warning', () => {
    afterEach(() => vi.restoreAllMocks());

    it('shows the exact balance when the user has Sparks', async () => {
        mockBalance(240);
        render(<DeleteAccountDialog onDeleted={() => {}} onClose={() => {}} />);
        const warning = await screen.findByTestId('delete-account-spark-warning');
        expect(warning).toHaveTextContent('240');
        expect(warning).toHaveTextContent(/permanently destroyed/i);
    });

    it('uses singular wording for exactly one Spark', async () => {
        mockBalance(1);
        render(<DeleteAccountDialog onDeleted={() => {}} onClose={() => {}} />);
        const warning = await screen.findByTestId('delete-account-spark-warning');
        expect(warning).toHaveTextContent('1 Spark.');
        expect(warning).not.toHaveTextContent('1 Sparks');
    });

    it('omits the warning entirely at zero balance', async () => {
        mockBalance(0);
        render(<DeleteAccountDialog onDeleted={() => {}} onClose={() => {}} />);
        // Wait for the balance fetch to settle before asserting absence.
        await screen.findByTestId('delete-account-confirm-input');
        await waitFor(() => {
            expect(screen.queryByTestId('delete-account-spark-warning')).not.toBeInTheDocument();
        });
    });

    it('falls back to non-numeric copy when the balance cannot be fetched', async () => {
        mockBalance(null, false);
        render(<DeleteAccountDialog onDeleted={() => {}} onClose={() => {}} />);
        const fallback = await screen.findByTestId('delete-account-spark-warning-fallback');
        expect(fallback).toHaveTextContent(/any unspent sparks will be permanently destroyed/i);
    });
});

describe('DeleteAccountDialog — confirmation gate', () => {
    afterEach(() => vi.restoreAllMocks());

    it('keeps the destructive action disabled until DELETE is typed', async () => {
        mockBalance(10);
        render(<DeleteAccountDialog onDeleted={() => {}} onClose={() => {}} />);
        const button = await screen.findByTestId('delete-account-confirm');
        expect(button).toBeDisabled();

        fireEvent.change(screen.getByTestId('delete-account-confirm-input'), { target: { value: 'delete' } });
        expect(button).toBeDisabled();  // case-sensitive on purpose

        fireEvent.change(screen.getByTestId('delete-account-confirm-input'), { target: { value: 'DELETE' } });
        expect(button).toBeEnabled();
    });

    it('calls onDeleted after a successful delete', async () => {
        mockBalance(0);
        const onDeleted = vi.fn();
        render(<DeleteAccountDialog onDeleted={onDeleted} onClose={() => {}} />);
        fireEvent.change(await screen.findByTestId('delete-account-confirm-input'), { target: { value: 'DELETE' } });
        fireEvent.click(screen.getByTestId('delete-account-confirm'));
        await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    });

    it('can be cancelled without deleting', async () => {
        mockBalance(50);
        const onClose = vi.fn();
        render(<DeleteAccountDialog onDeleted={() => {}} onClose={onClose} />);
        fireEvent.click(await screen.findByText('Cancel'));
        expect(onClose).toHaveBeenCalled();
        expect(globalThis.fetch).not.toHaveBeenCalledWith(
            expect.stringContaining('/account'),
            expect.objectContaining({ method: 'DELETE' }),
        );
    });
});
