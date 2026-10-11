import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import PhotoClueGame from '../PhotoClueGame';
import { apiFetch } from '../../utils/api';
import type { PhotoClueState } from '../../types';

vi.mock('../../utils/api', () => ({ apiFetch: vi.fn() }));

const state: PhotoClueState = {
    phase: 'PHOTO_WAITING_FOR_PHOTO',
    current_round_index: 0,
    round_count: 3,
    clue_giver_id: 'Alice',
    secret_prompt: { answer: 'Birthday cake' },
};

function jsonResponse(body: unknown): Response {
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function signedUpload(attachmentToken?: string) {
    return {
        asset: { id: 'img_clue' },
        upload: { url: 'https://media.example.test/upload.php', fields: { token: 'upload-hmac' } },
        ...(attachmentToken ? { attachment_token: attachmentToken } : {}),
    };
}

describe('PhotoClueGame upload attachment', () => {
    afterEach(() => {
        vi.clearAllMocks();
        vi.unstubAllGlobals();
    });

    it('hands the signed attachment token to the socket callback after finalize', async () => {
        const onPhotoReady = vi.fn();
        const uploadFetch = vi.fn().mockResolvedValue(new Response('', { status: 200 }));
        vi.stubGlobal('fetch', uploadFetch);
        vi.mocked(apiFetch)
            .mockResolvedValueOnce(jsonResponse(signedUpload('signed-photo-capability')))
            .mockResolvedValueOnce(jsonResponse({ asset: { id: 'img_clue', status: 'ready', public_url: 'https://media.example.test/photo.webp' } }));
        const { container } = render(<PhotoClueGame state={state} role="player" nickname="Alice" onPhotoReady={onPhotoReady} />);
        fireEvent.change(container.querySelector('input[type="file"]')!, {
            target: { files: [new File(['photo'], 'photo.webp', { type: 'image/webp' })] },
        });

        await waitFor(() => expect(onPhotoReady).toHaveBeenCalledWith('img_clue', 'signed-photo-capability'));
        expect(apiFetch).toHaveBeenNthCalledWith(1, '/media/upload-url', expect.objectContaining({
            body: expect.stringContaining('"purpose":"photo_clue_submission"'),
        }));
        expect(apiFetch).toHaveBeenNthCalledWith(2, '/media/img_clue/finalize', expect.any(Object));
        expect(uploadFetch).toHaveBeenCalledOnce();
        expect(screen.getByText('Photo submitted')).toBeInTheDocument();
    });

    it('rejects a signing response without an attachment token before uploading', async () => {
        const onPhotoReady = vi.fn();
        const uploadFetch = vi.fn();
        vi.stubGlobal('fetch', uploadFetch);
        vi.mocked(apiFetch).mockResolvedValueOnce(jsonResponse(signedUpload()));
        const { container } = render(<PhotoClueGame state={state} role="player" nickname="Alice" onPhotoReady={onPhotoReady} />);
        fireEvent.change(container.querySelector('input[type="file"]')!, {
            target: { files: [new File(['photo'], 'photo.webp', { type: 'image/webp' })] },
        });

        expect(await screen.findByText('Photo upload failed. Try another image.')).toBeInTheDocument();
        expect(uploadFetch).not.toHaveBeenCalled();
        expect(onPhotoReady).not.toHaveBeenCalled();
        expect(apiFetch).toHaveBeenCalledOnce();
    });

    it('does not submit an asset that finalize leaves pending', async () => {
        const onPhotoReady = vi.fn();
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 200 })));
        vi.mocked(apiFetch)
            .mockResolvedValueOnce(jsonResponse(signedUpload('signed-photo-capability')))
            .mockResolvedValueOnce(jsonResponse({ asset: { id: 'img_clue', status: 'pending' } }));
        const { container } = render(<PhotoClueGame state={state} role="player" nickname="Alice" onPhotoReady={onPhotoReady} />);
        fireEvent.change(container.querySelector('input[type="file"]')!, {
            target: { files: [new File(['photo'], 'photo.webp', { type: 'image/webp' })] },
        });

        expect(await screen.findByText('Photo upload failed. Try another image.')).toBeInTheDocument();
        expect(onPhotoReady).not.toHaveBeenCalled();
    });
});
