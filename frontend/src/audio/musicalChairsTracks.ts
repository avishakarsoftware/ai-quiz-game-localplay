import { type MusicalChairsMusicStyle } from '../types';

export interface MusicalChairsTrack {
    id: string;
    title: string;
    style: MusicalChairsMusicStyle;
    bpm: number;
    url: string;
}

const MUSIC_BASE_URL = (import.meta.env.VITE_MUSICAL_CHAIRS_MUSIC_BASE_URL || 'https://media.revelryapp.me/apps/localplay/music').replace(/\/$/, '');

const TRACK_DEFS: Array<Omit<MusicalChairsTrack, 'url'>> = [
    { id: 'upbeat-confetti', title: 'Confetti Pop', style: 'upbeat', bpm: 126 },
    { id: 'upbeat-bounce', title: 'Bounce Around', style: 'upbeat', bpm: 132 },
    { id: 'upbeat-neon', title: 'Neon Hop', style: 'upbeat', bpm: 122 },
    { id: 'upbeat-sprinkles', title: 'Sprinkles', style: 'upbeat', bpm: 128 },
    { id: 'jazzy-lounge', title: 'Lounge Shuffle', style: 'jazzy', bpm: 104 },
    { id: 'jazzy-swing', title: 'Tiny Swing', style: 'jazzy', bpm: 112 },
    { id: 'jazzy-walk', title: 'Walking Bass', style: 'jazzy', bpm: 108 },
    { id: 'jazzy-wink', title: 'Piano Wink', style: 'jazzy', bpm: 116 },
    { id: 'suspense-tiptoe', title: 'Tiptoe Tension', style: 'suspenseful', bpm: 92 },
    { id: 'suspense-clock', title: 'Clock Chase', style: 'suspenseful', bpm: 98 },
    { id: 'suspense-pulse', title: 'Pulse Runner', style: 'suspenseful', bpm: 102 },
    { id: 'suspense-sting', title: 'Sting Loop', style: 'suspenseful', bpm: 88 },
    { id: 'retro-arcade', title: 'Arcade Glow', style: 'retro', bpm: 118 },
    { id: 'retro-wave', title: 'Wave Runner', style: 'retro', bpm: 124 },
    { id: 'retro-pixel', title: 'Pixel Steps', style: 'retro', bpm: 120 },
    { id: 'retro-cassette', title: 'Cassette Dash', style: 'retro', bpm: 114 },
    { id: 'tropical-island', title: 'Island Steps', style: 'tropical', bpm: 108 },
    { id: 'tropical-sun', title: 'Sun Parade', style: 'tropical', bpm: 112 },
    { id: 'tropical-breeze', title: 'Breeze Bounce', style: 'tropical', bpm: 104 },
    { id: 'tropical-mango', title: 'Mango Walk', style: 'tropical', bpm: 110 },
];

export const MUSICAL_CHAIRS_TRACKS: MusicalChairsTrack[] = TRACK_DEFS.map((track) => ({
    ...track,
    url: `${MUSIC_BASE_URL}/${track.id}.wav`,
}));

export function tracksForMusicalChairsStyle(style: MusicalChairsMusicStyle): MusicalChairsTrack[] {
    return MUSICAL_CHAIRS_TRACKS.filter((track) => track.style === style);
}

export function defaultMusicalChairsTrackId(style: MusicalChairsMusicStyle): string {
    return tracksForMusicalChairsStyle(style)[0]?.id || MUSICAL_CHAIRS_TRACKS[0].id;
}

export function getMusicalChairsTrack(trackId: string | undefined, style: MusicalChairsMusicStyle): MusicalChairsTrack {
    return MUSICAL_CHAIRS_TRACKS.find((track) => track.id === trackId)
        || MUSICAL_CHAIRS_TRACKS.find((track) => track.style === style)
        || MUSICAL_CHAIRS_TRACKS[0];
}
