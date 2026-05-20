import { useState } from 'react';

interface GameImageProps {
    src: string;
    alt: string;
    aspect?: '16:9' | '4:3' | '1:1' | 'contain';
    mode?: 'question' | 'hero' | 'thumbnail' | 'tv';
}

export default function GameImage({ src, alt, aspect = '16:9', mode = 'question' }: GameImageProps) {
    const [loaded, setLoaded] = useState(false);
    const [failed, setFailed] = useState(false);

    return (
        <figure className={`game-image game-image-${mode} game-image-aspect-${aspect.replace(':', '-')}`}>
            {!loaded && !failed && <div className="game-image-skeleton" aria-hidden="true" />}
            {failed ? (
                <div className="game-image-error" role="img" aria-label={alt || 'Image unavailable'}>
                    Image unavailable
                </div>
            ) : (
                <img
                    src={src}
                    alt={alt}
                    loading="eager"
                    onLoad={() => setLoaded(true)}
                    onError={() => setFailed(true)}
                />
            )}
        </figure>
    );
}
