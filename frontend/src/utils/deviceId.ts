const DEVICE_ID_KEY = 'revelry_device_id';
const PREMIUM_TOKEN_KEY = 'revelry_premium_token';

export function getDeviceId(): string {
    let id = localStorage.getItem(DEVICE_ID_KEY);
    if (!id) {
        id = crypto.randomUUID();
        localStorage.setItem(DEVICE_ID_KEY, id);
    }
    return id;
}

export function getPremiumToken(): string | null {
    return localStorage.getItem(PREMIUM_TOKEN_KEY);
}

export function setPremiumToken(token: string): void {
    localStorage.setItem(PREMIUM_TOKEN_KEY, token);
}

export function clearPremiumToken(): void {
    localStorage.removeItem(PREMIUM_TOKEN_KEY);
}
