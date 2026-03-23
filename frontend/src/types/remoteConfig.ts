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
    kill_switch?: boolean;
    kill_switch_message?: string;
    kill_generate?: boolean;
    kill_payments?: boolean;
    force_config_refresh?: boolean;
    min_supported_version?: string;
  };
  pricing: {
    token_pack_price: string;
    token_pack_amount: number;
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
    kill_switch: false,
    kill_switch_message: '',
    kill_generate: false,
    kill_payments: false,
    force_config_refresh: false,
    min_supported_version: '1.0.0',
  },
  pricing: {
    token_pack_price: '$0.99',
    token_pack_amount: 110,
    label: '110 Spark Pack',
  },
  feature_flags: {
    show_upgrade_button: true,
    enable_image_generation: true,
  },
  announcements: [],
};
