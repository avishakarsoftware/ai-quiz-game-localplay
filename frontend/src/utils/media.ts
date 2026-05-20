import { API_URL } from '../config';

export function mediaUrl(path?: string): string {
    if (!path) return '';
    if (/^https?:\/\//i.test(path) || path.startsWith('data:')) return path;
    return `${API_URL}${path}`;
}
