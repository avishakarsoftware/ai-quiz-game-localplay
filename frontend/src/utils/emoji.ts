export function hasEmoji(value: string | undefined | null): boolean {
    if (!value) return false;
    return /\p{Extended_Pictographic}/u.test(value);
}

export function isEmojiForwardGame(gameType: string | undefined | null): boolean {
    return gameType === 'rebus' || gameType === 'emoji_charades';
}
