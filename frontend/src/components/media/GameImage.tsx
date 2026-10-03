import { useState } from 'react';

interface GameImageProps {
    src: string;
    alt: string;
    aspect?: '16:9' | '4:3' | '1:1' | 'contain';
    mode?: 'question' | 'hero' | 'thumbnail' | 'tv';
}

export default function GameImage({ src, alt, aspect = '16:9', mode = 'question' }: GameImageProps) {
    const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
    const [failedSrc, setFailedSrc] = useState<string | null>(null);
    const loaded = loadedSrc === src;
    const failed = failedSrc === src;

    return (
        <figure className={`game-image game-image-${mode} game-image-aspect-${aspect.replace(':', '-')}`}>
            {!loaded && !failed && <div className="game-image-skeleton" aria-hidden="true" />}
            {failed ? (
                <div className="game-image-error" role="img" aria-label={alt || 'Image unavailable'}>
                    Image unavailable
                </div>
            ) : (
                <img
                    key={src}
                    src={src}
                    alt={alt}
                    loading="eager"
                    onLoad={() => setLoadedSrc(src)}
                    onError={() => setFailedSrc(src)}
                />
            )}
        </figure>
    );
}
