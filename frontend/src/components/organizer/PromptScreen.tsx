import { useState, useEffect } from 'react';

export interface AIProvider {
    id: string;
    name: string;
    description: string;
    available: boolean;
}

interface PromptScreenProps {
    prompt: string;
    setPrompt: (v: string) => void;
    difficulty: string;
    setDifficulty: (v: string) => void;
    numQuestions: number;
    setNumQuestions: (v: number) => void;
    provider: string;
    setProvider: (v: string) => void;
    providers: AIProvider[];
    onGenerate: () => void;
    sdAvailable: boolean;
}

const DIFFICULTIES = [
    { value: 'easy', label: 'Easy', icon: '🟢' },
    { value: 'medium', label: 'Medium', icon: '🟡' },
    { value: 'hard', label: 'Hard', icon: '🔴' },
];

const PROVIDER_ICONS: Record<string, string> = {
    ollama: '🦙',
    gemini: '✨',
    claude: '🤖',
};

const TOPIC_IDEAS = [
    // Science & Space
    'The solar system and space exploration',
    'Black holes, dark matter, and the mysteries of the universe',
    'Famous scientists and their discoveries',
    'The human body and how organs work',
    'Dinosaurs and prehistoric life',
    'Chemistry in everyday life',
    'Weather phenomena and natural disasters',
    'The periodic table and elements',
    'Genetics, DNA, and heredity',
    'Volcanoes, earthquakes, and plate tectonics',

    // Geography & World
    'World capitals and geography',
    'Famous landmarks and wonders of the world',
    'Flags of the world',
    'Rivers, mountains, and natural formations',
    'Countries and their currencies',
    'Deserts, rainforests, and extreme environments',

    // History
    'Ancient Egyptian history and mythology',
    'Famous inventions that changed the world',
    'World War II key events and figures',
    'Ancient Rome and the Roman Empire',
    'The Renaissance and its greatest artists',
    'History of the Silk Road and trade routes',
    'The Age of Exploration and famous voyages',
    'Cold War history and the Space Race',
    'Ancient Greek civilization and philosophy',
    'Medieval castles, knights, and feudalism',

    // Pop Culture & Entertainment
    '90s pop culture and music',
    'Marvel and DC superheroes',
    'Disney and Pixar movies',
    'Harry Potter wizarding world',
    'Classic rock bands of the 70s and 80s',
    'Video game history and iconic characters',
    'Studio Ghibli films and Japanese animation',
    'Broadway musicals and theater history',
    'Star Wars universe trivia',
    'The Lord of the Rings and Tolkien lore',
    'Hip hop history and iconic albums',
    'Netflix and streaming era TV shows',
    'K-pop bands and Korean pop culture',
    'Classic TV sitcoms from the 80s and 90s',
    'James Bond movies and spy fiction',
    'Stranger Things and 80s nostalgia',
    'The Batman and DC cinematic universe',
    'Succession, Yellowstone, and prestige TV dramas',
    'The Bear, Fleabag, and critically acclaimed comedies',
    'Squid Game and international TV hits',
    'Bridgerton and period drama adaptations',
    'The Hunger Games and dystopian fiction',
    'Percy Jackson and Greek mythology in fiction',
    'Dune universe and Frank Herbert lore',
    'Stephen King novels and adaptations',
    'The Witcher books, games, and TV series',
    'Sherlock Holmes adaptations through the decades',
    'The Crown and British royal history on screen',
    'Rick and Morty and adult animated shows',
    'One Piece and the big three of anime',
    'Wes Anderson films and visual storytelling',
    'Christopher Nolan films and mind-bending plots',
    'Oscar Best Picture winners through the years',
    'Beyonce, Rihanna, and modern pop icons',
    'Travis Scott, Drake, and modern hip hop',
    'The Beatles and the British Invasion',
    'Pixar easter eggs and connected universe theories',

    // Sports
    'World Cup football trivia',
    'Olympic Games records and moments',
    'NBA legends and basketball history',
    'Formula 1 racing and legendary drivers',
    'Tennis Grand Slam champions',
    'Cricket World Cup history',
    'Extreme sports and adventure racing',

    // Nature & Animals
    'Ocean creatures and marine biology',
    'Dog breeds and fun animal facts',
    'Mythical creatures from around the world',
    'Endangered species and conservation',
    'Birds of the world and their migrations',
    'Insects, spiders, and creepy crawlies',
    'Cats throughout history and culture',
    'Apex predators and the food chain',

    // Food & Culture
    'Food and cuisine around the world',
    'The history of chocolate and coffee',
    'World religions and spiritual traditions',
    'Famous painters and art movements',
    'Classical music composers and their masterpieces',
    'Festivals and celebrations around the world',
    'Street food from different countries',
    'Wine regions and the history of winemaking',
    'Spices and the history of the spice trade',

    // Technology & Innovation
    'Technology milestones of the 21st century',
    'The history of the internet',
    'Artificial intelligence and robotics',
    'Famous tech founders and startups',
    'The evolution of smartphones and gadgets',
    'Cybersecurity and famous hacks',
    'Space missions and rocket science',
    'Electric vehicles and the future of transport',

    // Literature & Language
    'Shakespeare plays and Elizabethan theater',
    'Famous novels and their authors',
    'Fairy tales and their dark origins',
    'Mythology from Greece, Norse, and beyond',
    'Comic book history and graphic novels',
    'World languages and linguistics fun facts',
    'Poetry through the ages',

    // Math & Logic
    'Famous mathematicians and unsolved problems',
    'Optical illusions and how perception works',
    'Cryptography and secret codes throughout history',
    'Probability, statistics, and surprising facts',

    // Trending & Modern
    'Taylor Swift eras and album trivia',
    'Famous memes and internet culture',
    'Reality TV shows and iconic moments',
    'TikTok trends and viral moments',
    'Crypto, blockchain, and Web3 milestones',
    'Climate change facts and green energy',
    'Recent Mars missions and space discoveries',
    'AI breakthroughs and tech headlines',
    'Viral moments from recent Olympics',

    // Regional: South Asia
    'Bollywood movies and iconic actors',
    'Indian history from Maurya to modern era',
    'Cricket legends and IPL trivia',
    'Indian cuisine and regional dishes',
    'Festivals of India and their origins',
    'Mughal Empire architecture and history',

    // Regional: East Asia
    'Anime and manga classics',
    'Chinese dynasties and ancient history',
    'Japanese samurai, ninjas, and feudal history',
    'Korean drama and K-culture trivia',
    'Martial arts styles and their origins',
    'Chinese inventions that shaped the world',

    // Regional: Middle East & Africa
    'Ancient Mesopotamia and the cradle of civilization',
    'African kingdoms and empires',
    'Middle Eastern cuisine and culinary traditions',
    'The history of Arabic science and mathematics',
    'African wildlife safaris and national parks',
    'Egyptian pharaohs and the pyramids',

    // Regional: Latin America
    'Aztec and Mayan civilizations',
    'Latin American music genres: salsa, bossa nova, reggaeton',
    'Famous Latin American authors and magical realism',
    'Carnival and Latin American festivals',
    'The Inca Empire and Machu Picchu',

    // Niche Deep-Cuts
    'The Office quotes and episode trivia',
    'Friends TV show trivia',
    'Seinfeld episodes and catchphrases',
    'Minecraft, Roblox, and sandbox games',
    'Dungeons & Dragons lore and monsters',
    'True crime famous cases and investigations',
    'Pokémon generations and evolution trivia',
    'The Simpsons predictions and episodes',
    'Game of Thrones houses and lore',
    'Breaking Bad and Better Call Saul trivia',
    'Formula 1 technical rules and pit strategy',
    'Astronomy: constellations and stargazing',
    'Cheese varieties from around the world',
    'The history of tattoos and body art',
    'Famous heists and bank robberies',
    'Horror movies and slasher film history',
    'Roller coasters and theme park engineering',
    'Whiskey, bourbon, and spirits trivia',

    // Miscellaneous & Fun
    'World records and bizarre achievements',
    'Urban legends and strange true stories',
    'Board games and their origins',
    'The history of fashion and iconic designers',
    'Architecture marvels ancient and modern',
    'Pirates, treasure, and the golden age of piracy',
    'Conspiracy theories debunked by science',
    'Unusual laws from around the world',
    'The psychology of color and emotions',
    'Famous heists and unsolved mysteries',
];

export default function PromptScreen({
    prompt, setPrompt, difficulty, setDifficulty,
    numQuestions, setNumQuestions, provider, setProvider,
    providers, onGenerate, sdAvailable: _sdAvailable,
}: PromptScreenProps) {
    const shuffleTopic = () => {
        let next: string;
        do {
            next = TOPIC_IDEAS[Math.floor(Math.random() * TOPIC_IDEAS.length)];
        } while (next === prompt && TOPIC_IDEAS.length > 1);
        setPrompt(next);
    };

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 flex flex-col justify-center py-8">
                {/* Hero header */}
                <div className="text-center mb-8">
                    <div className="hero-icon mb-4">⚡</div>
                    <h1 className="hero-title">Create Quiz</h1>
                    <p className="text-[--text-tertiary] mt-2">What should your players be quizzed on?</p>
                </div>

                <div className="space-y-4">
                    {/* Prompt textarea with glass border */}
                    <div className="prompt-input-wrapper" style={{ position: 'relative' }}>
                        <textarea
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value.slice(0, 140))}
                            placeholder="Enter any topic for your quiz, or tap the dice for a random one!"
                            className="input-field input-large"
                            maxLength={140}
                        />
                        <button
                            type="button"
                            onClick={shuffleTopic}
                            className="shuffle-btn"
                            title="Suggest a random topic"
                        >
                            🎲
                        </button>
                        <div className="text-xs text-right mt-1" style={{ color: prompt.length > 450 ? 'var(--color-error, #ef4444)' : 'var(--text-tertiary)' }}>
                            {prompt.length}/500
                        </div>
                    </div>

                    {/* AI Provider selector */}
                    {import.meta.env.DEV && providers.length > 0 && (
                        <div>
                            <p className="section-header mb-2">AI Provider</p>
                            <div className="provider-selector">
                                {providers.map((p) => (
                                    <button
                                        key={p.id}
                                        onClick={() => p.available && setProvider(p.id)}
                                        className={`provider-option ${provider === p.id ? 'active' : ''} ${!p.available ? 'unavailable' : ''}`}
                                        disabled={!p.available}
                                    >
                                        <span className="text-lg">{PROVIDER_ICONS[p.id] || '🧠'}</span>
                                        <span className="provider-name">{p.name}</span>
                                        {!p.available && <span className="provider-badge">{p.id === 'ollama' ? 'Offline' : 'No key'}</span>}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Difficulty selector */}
                    <div>
                        <p className="section-header mb-2">Difficulty</p>
                        <div className="difficulty-selector">
                            {DIFFICULTIES.map((d) => (
                                <button
                                    key={d.value}
                                    onClick={() => setDifficulty(d.value)}
                                    className={`difficulty-option ${difficulty === d.value ? 'active' : ''}`}
                                >
                                    <span className="text-lg">{d.icon}</span>
                                    <span>{d.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Question count */}
                    <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
                        <p className="font-medium">Questions</p>
                        <div style={{ display: 'flex', gap: 8 }}>
                            {[5, 10, 15, 20, 25].map(n => (
                                <button
                                    key={n}
                                    onClick={() => setNumQuestions(n)}
                                    className={`btn ${numQuestions === n ? 'btn-primary' : 'btn-secondary'}`}
                                    style={{ flex: 1, padding: '8px 0', fontSize: '1rem' }}
                                >
                                    {n}
                                </button>
                            ))}
                        </div>
                    </div>

                </div>
            </div>

            <div className="mt-auto pb-4 space-y-2">
                <button
                    onClick={onGenerate}
                    disabled={!prompt.trim()}
                    className="btn btn-primary btn-glow w-full"
                >
                    Generate Quiz
                </button>

            </div>
        </div>
    );
}
