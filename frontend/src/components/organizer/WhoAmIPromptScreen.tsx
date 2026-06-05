import DrawingPromptScreen from './DrawingPromptScreen';
import { type AIProvider } from './PromptScreen';

interface WhoAmIPromptScreenProps {
    prompt: string;
    setPrompt: (value: string) => void;
    difficulty: string;
    setDifficulty: (value: string) => void;
    numRounds: number;
    setNumRounds: (value: number) => void;
    provider: string;
    setProvider: (value: string) => void;
    providers: AIProvider[];
    onGenerate: () => void;
    onCreateCustom: () => void;
    onQuickStart: () => void;
    onBack: () => void;
}

export default function WhoAmIPromptScreen(props: WhoAmIPromptScreenProps) {
    return (
        <DrawingPromptScreen
            prompt={props.prompt}
            setPrompt={props.setPrompt}
            difficulty={props.difficulty}
            setDifficulty={props.setDifficulty}
            numPrompts={props.numRounds}
            setNumPrompts={props.setNumRounds}
            provider={props.provider}
            setProvider={props.setProvider}
            providers={props.providers}
            onGenerate={props.onGenerate}
            onBack={props.onBack}
            title="Who Am I?"
            icon="❓"
            subtitle="Generate mystery answers with progressive clues"
            placeholder="Theme, category, or vibe"
            countLabel="Rounds"
            countOptions={[5, 8, 10, 15, 20]}
            generateLabel="Generate Clues"
            secondaryActions={[
                { label: 'Create Your Own', onClick: props.onCreateCustom },
                { label: 'Quick Start', onClick: props.onQuickStart },
            ]}
        />
    );
}
