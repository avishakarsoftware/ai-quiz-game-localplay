import { act, renderHook } from '@testing-library/react';
import { useTokenBalance } from '../useTokenBalance';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('../../utils/api', () => ({ apiFetch }));

it('a slow anonymous response cannot overwrite the signed-in wallet balance', async () => {
    const pending: Array<(response: Response) => void> = [];
    apiFetch.mockImplementation(() => new Promise<Response>((resolve) => pending.push(resolve)));
    const { result } = renderHook(() => useTokenBalance());
    act(() => { window.dispatchEvent(new Event('refresh-sparks')); });
    await act(async () => { pending[1](Response.json({ balance: 999 })); });
    expect(result.current.tokenStatus.balance).toBe(999);
    await act(async () => { pending[0](Response.json({ balance: 3 })); });
    expect(result.current.tokenStatus.balance).toBe(999);
    expect(result.current.loading).toBe(false);
});
