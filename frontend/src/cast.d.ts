// Google Cast SDK type declarations

declare namespace cast {
  namespace framework {
    class CastContext {
      static getInstance(): CastContext;
      setOptions(options: CastContextOptions): void;
      getCurrentSession(): CastSession | null;
      requestSession(): Promise<void>;
      addEventListener(type: string, listener: (event: CastStateEvent) => void): void;
      removeEventListener(type: string, listener: (event: CastStateEvent) => void): void;
      getCastState(): string;
    }

    class CastSession {
      getSessionObj(): chrome.cast.Session;
      sendMessage(namespace: string, message: string): Promise<void>;
      addMessageListener(namespace: string, listener: (namespace: string, message: string) => void): void;
      removeMessageListener(namespace: string, listener: (namespace: string, message: string) => void): void;
    }

    interface CastContextOptions {
      receiverApplicationId: string;
      autoJoinPolicy?: string;
    }

    interface CastStateEvent {
      castState: string;
    }

    enum CastContextEventType {
      CAST_STATE_CHANGED = 'caststatechanged',
      SESSION_STATE_CHANGED = 'sessionstatechanged',
    }

    enum CastState {
      NO_DEVICES_AVAILABLE = 'NO_DEVICES_AVAILABLE',
      NOT_CONNECTED = 'NOT_CONNECTED',
      CONNECTING = 'CONNECTING',
      CONNECTED = 'CONNECTED',
    }

    enum SessionState {
      NO_SESSION = 'NO_SESSION',
      SESSION_STARTING = 'SESSION_STARTING',
      SESSION_STARTED = 'SESSION_STARTED',
      SESSION_START_FAILED = 'SESSION_START_FAILED',
      SESSION_ENDING = 'SESSION_ENDING',
      SESSION_ENDED = 'SESSION_ENDED',
      SESSION_RESUMED = 'SESSION_RESUMED',
    }

    // Cast Receiver Framework
    class CastReceiverContext {
      static getInstance(): CastReceiverContext;
      start(): void;
      stop(): void;
      addCustomMessageListener(namespace: string, listener: (event: CustomMessageEvent) => void): void;
      sendCustomMessage(namespace: string, senderId: string | undefined, message: string): void;
    }

    interface CustomMessageEvent {
      type: string;
      senderId: string;
      data: string;
    }
  }
}

declare namespace chrome {
  namespace cast {
    class Session {
      sessionId: string;
      addMessageListener(namespace: string, listener: (namespace: string, message: string) => void): void;
      sendMessage(namespace: string, message: string, successCallback?: () => void, errorCallback?: (error: Error) => void): void;
    }

    enum AutoJoinPolicy {
      TAB_AND_ORIGIN_SCOPED = 'tab_and_origin_scoped',
      ORIGIN_SCOPED = 'origin_scoped',
      PAGE_SCOPED = 'page_scoped',
    }
  }
}

interface Window {
  __onGCastApiAvailable?: (isAvailable: boolean) => void;
}
