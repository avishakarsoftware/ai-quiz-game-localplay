import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'me.revelryapp.quiz',
  appName: 'Revelry Quiz',
  webDir: 'dist',
  server: {
    // Load the bundled web app from local files (default behavior)
    // API calls go to the remote backend via VITE_API_URL baked at build time
    androidScheme: 'https',
  },
  ios: {
    contentInset: 'automatic',
    preferredContentMode: 'mobile',
  },
  android: {
    backgroundColor: '#1a1a2e',
  },
};

export default config;
