import { ImagePlus, Plus, Trash2, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import GameImage from '../media/GameImage';
import { mediaUrl } from '../../utils/media';
import { apiFetch } from '../../utils/api';
import type { BingoDeckItem } from '../../types';

const STARTER_ITEMS = [
    'Dance floor', 'Group photo', 'Someone laughs', 'Snack table', 'Party playlist',
    'Inside joke', 'A toast', 'Late arrival', 'New friend', 'Dessert',
    'Someone sings', 'Sparkly outfit', 'Favorite song', 'Big hug', 'Phone photo',
    'Someone cheers', 'Cake', 'Gift bag', 'Funny story', 'Matching colors',
    'Table games', 'A surprise', 'Best dressed', 'Last call', 'Confetti',
];

function makeTextItem(display: string, index: number): BingoDeckItem {
    const trimmed = display.trim().slice(0, 40);
    return {
        id: `item_${Date.now()}_${index}`,
        kind: trimmed.match(/\p{Emoji}/u) && trimmed.length <= 6 ? 'emoji' : 'text',
        value: trimmed.toLowerCase(),
        display: trimmed,
    };
}

export default function BingoSetupScreen({
    title,
    setTitle,
    deck,
    setDeck,
    freeCenter,
    setFreeCenter,
    claimRequiresLatest,
    setClaimRequiresLatest,
    onCreateRoom,
    onBack,
}: {
    title: string;
    setTitle: (value: string) => void;
    deck: BingoDeckItem[];
    setDeck: (value: BingoDeckItem[]) => void;
    freeCenter: boolean;
    setFreeCenter: (value: boolean) => void;
    claimRequiresLatest: boolean;
    setClaimRequiresLatest: (value: boolean) => void;
    onCreateRoom: () => void;
    onBack: () => void;
}) {
    const [bulkText, setBulkText] = useState('');
    const [uploadingId, setUploadingId] = useState('');
    const [status, setStatus] = useState('');
    const minimum = freeCenter ? 24 : 25;
    const readyCount = useMemo(() => deck.filter((item) => item.display.trim() && (item.kind !== 'image' || item.image_url)).length, [deck]);
    const canCreate = readyCount >= minimum;

    const addFromText = () => {
        const lines = bulkText.split(/\n+/).map((line) => line.trim()).filter(Boolean);
        if (!lines.length) return;
        const existing = new Set(deck.map((item) => item.display.trim().toLowerCase()));
        const next = [...deck];
        lines.forEach((line, index) => {
            const key = line.toLowerCase();
            if (!existing.has(key)) {
                existing.add(key);
                next.push(makeTextItem(line, index));
            }
        });
        setDeck(next.slice(0, 120));
        setBulkText('');
    };

    const updateItem = (id: string, patch: Partial<BingoDeckItem>) => {
        setDeck(deck.map((item) => item.id === id ? { ...item, ...patch } : item));
    };

    const removeItem = (id: string) => {
        setDeck(deck.filter((item) => item.id !== id));
    };

    const resetTemplate = () => {
        setDeck(STARTER_ITEMS.map((item, index) => makeTextItem(item, index)));
    };

    const addBlank = () => {
        setDeck([...deck, makeTextItem('New square', deck.length)].slice(0, 120));
    };

    const uploadImage = async (item: BingoDeckItem, file: File) => {
        setUploadingId(item.id);
        setStatus('');
        try {
            const signRes = await apiFetch('/media/upload-url', {
                method: 'POST',
                body: JSON.stringify({
                    filename: file.name,
                    mime_type: file.type,
                    bytes: file.size,
                    purpose: 'bingo_item',
                }),
            });
            if (!signRes.ok) throw new Error('sign_failed');
            const signed = await signRes.json();
            const form = new FormData();
            Object.entries(signed.upload.fields as Record<string, string>).forEach(([key, value]) => form.append(key, value));
            form.append('file', file);
            const uploadRes = await fetch(signed.upload.url, { method: 'POST', body: form });
            if (!uploadRes.ok) throw new Error('upload_failed');
            const finalizeRes = await apiFetch(`/media/${signed.asset.id}/finalize`, {
                method: 'POST',
                body: JSON.stringify({ bytes: file.size, alt_text: item.display }),
            });
            if (!finalizeRes.ok) throw new Error('finalize_failed');
            const finalized = await finalizeRes.json();
            updateItem(item.id, {
                kind: 'image',
                image_asset_id: finalized.asset.id,
                image_url: finalized.asset.public_url,
                alt_text: item.display,
            });
            setStatus('Image uploaded');
        } catch {
            setStatus('Image upload failed');
        } finally {
            setUploadingId('');
        }
    };

    return (
        <div className="housie-setup min-h-dvh flex flex-col safe-top safe-bottom animate-in">
            <div className="housie-setup-hero">
                <div className="hero-icon mb-4">▦</div>
                <h1 className="hero-title">Set Up Bingo</h1>
                <p>Create a custom board with words, emojis, or photos.</p>
            </div>

            <div className="housie-setup-card">
                <div className="housie-field">
                    <label htmlFor="bingo-title">Game title</label>
                    <input id="bingo-title" className="input-field" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} />
                </div>

                <div className="housie-field">
                    <div className="housie-section-label">Board options</div>
                    <label className="housie-check-control">
                        <input type="checkbox" checked={freeCenter} onChange={(event) => setFreeCenter(event.target.checked)} />
                        <span>Use a free center square</span>
                    </label>
                    <label className="housie-check-control">
                        <input type="checkbox" checked={claimRequiresLatest} onChange={(event) => setClaimRequiresLatest(event.target.checked)} />
                        <span>Strict claims must use the latest call</span>
                    </label>
                </div>

                <div className="housie-field">
                    <div className="housie-section-label">Add items</div>
                    <textarea
                        className="input-field bingo-bulk-input"
                        value={bulkText}
                        onChange={(event) => setBulkText(event.target.value)}
                        placeholder="Paste one item per line"
                        rows={5}
                    />
                    <div className="housie-caller-actions">
                        <button type="button" className="btn btn-secondary" onClick={addFromText}><Plus size={16} /> Add List</button>
                        <button type="button" className="btn btn-secondary" onClick={addBlank}><Plus size={16} /> Add Item</button>
                        <button type="button" className="btn btn-secondary" onClick={resetTemplate}>Use Starter Template</button>
                    </div>
                </div>

                <div className="housie-field">
                    <div className="housie-section-label">Deck ({readyCount}/{minimum} ready)</div>
                    {status && <p className="housie-muted-copy">{status}</p>}
                    <div className="bingo-deck-editor">
                        {deck.map((item) => (
                            <div key={item.id} className="bingo-deck-row">
                                <div className="bingo-image-slot" aria-hidden={item.kind !== 'image'}>
                                    {item.kind === 'image' && item.image_url ? (
                                        <GameImage src={mediaUrl(item.image_url)} alt={item.alt_text || item.display} mode="thumbnail" />
                                    ) : (
                                        <ImagePlus size={18} />
                                    )}
                                </div>
                                <input
                                    className="input-field"
                                    value={item.display}
                                    onChange={(event) => updateItem(item.id, {
                                        display: event.target.value.slice(0, 40),
                                        value: event.target.value.trim().toLowerCase().slice(0, 40),
                                        alt_text: item.kind === 'image' ? event.target.value.slice(0, 40) : item.alt_text,
                                    })}
                                    maxLength={40}
                                />
                                <label className="btn btn-secondary custom-upload-button" title="Upload image">
                                    <ImagePlus size={16} aria-hidden="true" />
                                    <input
                                        type="file"
                                        accept="image/png,image/jpeg,image/webp"
                                        className="custom-file-input"
                                        disabled={uploadingId === item.id}
                                        onChange={(event) => {
                                            const file = event.target.files?.[0];
                                            event.target.value = '';
                                            if (file) void uploadImage(item, file);
                                        }}
                                    />
                                </label>
                                {item.kind === 'image' && (
                                    <button type="button" className="btn btn-secondary custom-upload-button" onClick={() => updateItem(item.id, { kind: 'text', image_asset_id: '', image_url: '', alt_text: '' })}>
                                        <X size={16} />
                                    </button>
                                )}
                                <button type="button" className="btn btn-secondary custom-upload-button" onClick={() => removeItem(item.id)}>
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            <div className="housie-setup-actions">
                <button onClick={onBack} className="btn btn-secondary" aria-label="Back">‹</button>
                <button onClick={onCreateRoom} disabled={!canCreate} className="btn btn-primary btn-glow">Create Room</button>
            </div>
        </div>
    );
}
