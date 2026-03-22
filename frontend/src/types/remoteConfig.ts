export interface Announcement {
  id: string;
  text: string;
  type: 'info' | 'warning';
  dismissible: boolean;
}

export interface RemoteConfig {
  version: number;
  welcome_message: string;
  cache_ttl_seconds?: number;
  operations: {
    maintenance: boolean;
    maintenance_message: string;
    maintenance_until: string | null;
    kill_generate?: boolean;
    kill_payments?: boolean;
    force_config_refresh?: boolean;
  };
  pricing: {
    pass_price: string;
    games: number;
    duration_hours: number;
    label: string;
  };
  feature_flags: {
    show_upgrade_button: boolean;
    enable_image_generation: boolean;
  };
  announcements: Announcement[];
}

export const DEFAULT_CONFIG: RemoteConfig = {
  version: 0,
  welcome_message: '',
  cache_ttl_seconds: 86400,
  operations: {
    maintenance: false,
    maintenance_message: '',
    maintenance_until: null,
    kill_generate: false,
    kill_payments: false,
    force_config_refresh: false,
  },
  pricing: {
    pass_price: '$0.99',
    games: 10,
    duration_hours: 720,
    label: '10-Game Pack',
  },
  feature_flags: {
    show_upgrade_button: true,
    enable_image_generation: true,
  },
  announcements: [],
};
