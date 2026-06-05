import { type ChitPullSafeLevel } from '../../types';
import DrawingPromptScreen from './DrawingPromptScreen';
import { type AIProvider } from './PromptScreen';

interface ChitPullPromptScreenProps {
    prompt: string;
    setPrompt: (value: string) => void;
    difficulty: string;
    setDifficulty: (value: string) => void;
    numChits: number;
    setNumChits: (value: number) => void;
    safeLevel: ChitPullSafeLevel;
    setSafeLevel: (value: ChitPullSafeLevel) => void;
    provider: string;
    setProvider: (value: string) => void;
    providers: AIProvider[];
    onGenerate: () => void;
    onCreateCustom: () => void;
    onQuickStart: () => void;
    onBack: () => void;
}

export default function ChitPullPromptScreen({
    safeLevel,
    setSafeLevel,
    ...props
}: ChitPullPromptScreenProps) {
    return (
        <DrawingPromptScreen
            prompt={props.prompt}
            setPrompt={props.setPrompt}
            difficulty={props.difficulty}
            setDifficulty={props.setDifficulty}
            numPrompts={props.numChits}
            setNumPrompts={props.setNumChits}
            provider={props.provider}
            setProvider={props.setProvider}
            providers={props.providers}
            onGenerate={props.onGenerate}
            onBack={props.onBack}
            title="Chit Pull"
            icon="🎟️"
            subtitle="Generate funny questions, actions, and mini challenges"
            placeholder="Birthday party, cousins, silly but clean..."
            countLabel="Chits"
            countOptions={[10, 20, 30, 50, 75]}
            generateLabel="Generate Chits"
            extraControls={
                <div>
                    <p className="text-[--text-tertiary] text-sm font-semibold mb-2">Safety</p>
                    <div className="time-preset-selector" style={{ marginBottom: 18 }}>
                        {(['kids', 'family', 'work_safe', 'spicy'] as ChitPullSafeLevel[]).map((level) => (
                            <button
                                key={level}
                                type="button"
                                onClick={() => setSafeLevel(level)}
                                className={`time-preset-option ${safeLevel === level ? 'active' : ''}`}
                            >
                                {level === 'work_safe' ? 'Work' : level[0].toUpperCase() + level.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>
            }
            secondaryActions={[
                { label: 'Create Your Own', onClick: props.onCreateCustom },
                { label: 'Quick Start', onClick: props.onQuickStart },
            ]}
        />
    );
}
