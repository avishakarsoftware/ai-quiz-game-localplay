import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import GiftSection from '../GiftSection';

/**
 * Spark gifting (SPEC-GIFTING). The two behaviours worth locking down are the success/error copy
 * and the idempotency-key contract: the SAME key is replayed while an attempt is failing (so a
 * retry can't double-send) and only rotates after a confirmed success.
 */

interface GiftCall { code: string; amount: number; idempotency_key: string }

function mockGift(handler: (call: GiftCall) => { ok: boolean; status?: number; body: unknown }) {
    const calls: GiftCall[] = [];
    globalThis.fetch = vi.fn((url: string, init?: RequestInit) => {
        if (String(url).includes('/tokens/gift')) {
            const call = JSON.parse(String(init?.body)) as GiftCall;
            calls.push(call);
            const res = handler(call);
            return Promise.resolve({
                ok: res.ok,
                status: res.status ?? (res.ok ? 200 : 400),
                json: () => Promise.resolve(res.body),
            } as Response);
        }
        return Promise.reject(new Error(`unexpected fetch: ${url}`));
    }) as unknown as typeof fetch;
    return calls;
}

function fillAndSend(code: string, amount: string) {
    fireEvent.change(screen.getByLabelText("Friend's code"), { target: { value: code } });
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: amount } });
    fireEvent.click(screen.getByText('Send'));
}

describe('GiftSection', () => {
    afterEach(() => vi.restoreAllMocks());

    it('sends the gift and confirms the amount, then clears the form', async () => {
        const calls = mockGift(() => ({ ok: true, body: { sent: true, amount: 25, new_balance: 75, duplicate: false } }));
        render(<GiftSection />);
        fillAndSend('friend1', '25');
        await screen.findByText('🎁 Sent 25 sparks!');
        expect(calls[0]).toMatchObject({ code: 'FRIEND1', amount: 25 });
        // form cleared after success
        expect((screen.getByLabelText("Friend's code") as HTMLInputElement).value).toBe('');
        expect((screen.getByLabelText('Amount') as HTMLInputElement).value).toBe('');
    });

    it('surfaces the backend error detail and does not clear the form', async () => {
        mockGift(() => ({ ok: false, status: 402, body: { detail: "You don't have enough sparks for that gift." } }));
        render(<GiftSection />);
        fillAndSend('friend2', '999');
        await screen.findByText("You don't have enough sparks for that gift.");
        expect((screen.getByLabelText("Friend's code") as HTMLInputElement).value).toBe('FRIEND2');
    });

    it('reuses the idempotency key on a retry after failure, and rotates it after success', async () => {
        let failFirst = true;
        const calls = mockGift(() =>
            failFirst
                ? { ok: false, status: 500, body: { detail: 'Server error' } }
                : { ok: true, body: { sent: true, amount: 5, new_balance: 10, duplicate: false } },
        );
        render(<GiftSection />);

        // First attempt fails.
        fillAndSend('pal', '5');
        await screen.findByText('Server error');

        // Retry the same attempt (form still populated) — succeeds this time.
        failFirst = false;
        fireEvent.click(screen.getByText('Send'));
        await screen.findByText('🎁 Sent 5 sparks!');

        // The failed send and its retry share ONE idempotency key (safe retry, no double-send).
        expect(calls).toHaveLength(2);
        expect(calls[0].idempotency_key).toBe(calls[1].idempotency_key);

        // A brand-new gift after success uses a DIFFERENT key.
        fillAndSend('pal', '3');
        await waitFor(() => expect(calls).toHaveLength(3));
        expect(calls[2].idempotency_key).not.toBe(calls[1].idempotency_key);
    });

    it('reports a duplicate replay without claiming a fresh charge', async () => {
        mockGift(() => ({ ok: true, body: { sent: true, amount: 25, new_balance: 75, duplicate: true } }));
        render(<GiftSection />);
        fillAndSend('friend3', '25');
        await screen.findByText('Already sent — no charge.');
    });
});
