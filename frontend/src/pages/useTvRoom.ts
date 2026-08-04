import { useCallback, useEffect, useRef, useState } from 'react';
import { WS_URL } from '../config';
import { apiFetch } from '../utils/api';

export interface TvRoomPlayer {
    nickname: string;
    avatar?: string;
}

export interface TvRoomState {
    roomCode: string;
    joinUrl: string;
    players: TvRoomPlayer[];
    /** Live count of connected guest phones. Drives which tiles are unlocked. */
    connectedPhones: number;
    status: 'idle' | 'creating' | 'lobby' | 'error';
    error: string;
}

const EMPTY: TvRoomState = {
    roomCode: '',
    joinUrl: '',
    players: [],
    connectedPhones: 0,
    status: 'idle',
    error: '',
};

const RECONNECT_INITIAL_MS = 1000;
const RECONNECT_MAX_MS = 8000;

/**
 * The TV hosting its own room (SPEC-TV-APP §7a).
 *
 * The key realisation that made this small: **the TV can simply BE the organizer.** It creates the
 * room through the ordinary `/room/create`, keeps the `organizer_token`, and connects on the
 * organizer socket. No TV-specific endpoint, no claim-host handshake, no new auth path — and the
 * room genuinely belongs to the TV's wallet, which is correct, because the TV is the host and the
 * host is who pays.
 *
 * It also fixes two things that were previously impossible:
 *   - The join QR carries a REAL room code. Before this, the TV rendered a bare `/join` link, which
 *     is a dead end: the guest lands on a code prompt with no code to enter.
 *   - `connectedPhones` becomes real, because the organizer socket is already told when players
 *     join and leave. That is what lets locked game tiles un-grey live as guests arrive — the
 *     single most useful piece of feedback on the TV surface.
 */
export function useTvRoom() {
    const [state, setState] = useState<TvRoomState>(EMPTY);
    const wsRef = useRef<WebSocket | null>(null);
    const tokenRef = useRef<string>('');
    const roomRef = useRef<string>('');
    const reconnectDelayRef = useRef(RECONNECT_INITIAL_MS);
    const reconnectTimerRef = useRef<number | ReturnType<typeof setTimeout> | null>(null);

    const clearReconnectTimer = useCallback(() => {
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }
    }, []);

    const closeSocket = useCallback(() => {
        clearReconnectTimer();
        if (wsRef.current) {
            wsRef.current.onclose = null;   // don't treat a deliberate close as a drop
            wsRef.current.close();
            wsRef.current = null;
        }
    }, [clearReconnectTimer]);

    useEffect(() => closeSocket, [closeSocket]);

    const connect = useCallback((roomCode: string, organizerToken: string) => {
        clearReconnectTimer();
        if (wsRef.current) {
            wsRef.current.onclose = null;
            wsRef.current.close();
        }
        roomRef.current = roomCode;
        tokenRef.current = organizerToken;
        // WS_URL is the same constant OrganizerPage uses, so the TV inherits whatever
        // gamma/prod/native base the build was configured with.
        const ws = new WebSocket(`${WS_URL}/ws/${roomCode}/tv-host?organizer=true`);
        wsRef.current = ws;

        ws.onopen = () => {
            reconnectDelayRef.current = RECONNECT_INITIAL_MS;
            setState((prev) => (prev.status === 'lobby' && prev.error === 'Reconnecting…'
                ? { ...prev, error: '' }
                : prev));
            ws.send(JSON.stringify({ type: 'AUTH', token: organizerToken }));
        };

        ws.onmessage = (event) => {
            let msg: Record<string, unknown>;
            try {
                msg = JSON.parse(event.data as string);
            } catch {
                return;   // a malformed frame must never take the TV down mid-party
            }
            // Any message carrying a roster is authoritative for the phone count. Player-count
            // messages arrive under several types (joined, left, disconnected, sync), so key off
            // the payload rather than enumerating types — a missed type would silently freeze
            // the unlock behaviour.
            const players = msg.players;
            if (Array.isArray(players)) {
                setState((prev) => ({
                    ...prev,
                    players: players as TvRoomPlayer[],
                    connectedPhones: typeof msg.player_count === 'number'
                        ? (msg.player_count as number)
                        : (players as TvRoomPlayer[]).length,
                }));
            }
        };

        ws.onclose = () => {
            if (wsRef.current !== ws) return;
            wsRef.current = null;
            // Keep the room code on screen: guests may still be mid-join, and blanking the QR
            // because a socket blipped would be worse than a stale-but-correct code.
            setState((prev) => (prev.status === 'lobby' ? { ...prev, error: 'Reconnecting…' } : prev));
            const delay = reconnectDelayRef.current;
            reconnectDelayRef.current = Math.min(delay * 2, RECONNECT_MAX_MS);
            reconnectTimerRef.current = window.setTimeout(() => {
                reconnectTimerRef.current = null;
                if (roomRef.current && tokenRef.current) {
                    connect(roomRef.current, tokenRef.current);
                }
            }, delay);
        };
    }, [clearReconnectTimer]);

    /** Create a room owned by the TV and enter the lobby. */
    const host = useCallback(async (gameType: string, extra: Record<string, unknown> = {}) => {
        closeSocket();
        roomRef.current = '';
        tokenRef.current = '';
        reconnectDelayRef.current = RECONNECT_INITIAL_MS;
        setState({ ...EMPTY, status: 'creating' });
        try {
            const res = await apiFetch('/room/create', {
                method: 'POST',
                body: JSON.stringify({ game_type: gameType, ...extra }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.room_code) {
                roomRef.current = '';
                tokenRef.current = '';
                setState({
                    ...EMPTY,
                    status: 'error',
                    // Surface the backend's own message: "not enough sparks" is the most likely
                    // failure and the host needs to know that specifically.
                    error: data.detail || 'Could not start a room.',
                });
                return null;
            }
            tokenRef.current = data.organizer_token || '';
            const joinUrl = `${window.location.origin}/join/${data.room_code}`;
            setState({
                ...EMPTY,
                roomCode: data.room_code,
                joinUrl,
                status: 'lobby',
            });
            connect(data.room_code, tokenRef.current);
            return data.room_code as string;
        } catch {
            roomRef.current = '';
            tokenRef.current = '';
            setState({ ...EMPTY, status: 'error', error: 'Network error — check the TV connection.' });
            return null;
        }
    }, [connect]);

    const leave = useCallback(() => {
        closeSocket();
        roomRef.current = '';
        tokenRef.current = '';
        reconnectDelayRef.current = RECONNECT_INITIAL_MS;
        setState(EMPTY);
    }, [closeSocket]);

    return { ...state, host, leave };
}
