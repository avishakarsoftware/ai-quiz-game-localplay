export default function LoadingScreen() {
    return (
        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
            <div className="w-12 h-12 border-4 border-[--bg-tertiary] border-t-[--accent-primary] rounded-full animate-spin mb-6" />
            <p className="text-lg font-semibold">Generating quiz...</p>
            <p className="text-[--text-tertiary] mt-2">This may take a moment</p>
        </div>
    );
}
