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
  // NOTE: the legacy single-pack `pricing` block (token_pack_*, label, promo) was removed
  // 2026-07-21 — it described the retired one-pack economy (110-for-$0.99) that no longer
  // exists (the live ladder is 50/200/500, store-localized on native via RevenueCat). No
  // component read it after the ErrorModal promo UI was deleted. Extra `pricing` keys still
  // present in served config.json / /config/public are simply ignored.
  feature_flags: {
    show_upgrade_button: boolean;
    enable_image_generation: boolean;
    ads_enabled?: boolean;
    referral_enabled?: boolean;
    gifting_enabled?: boolean;
    achievements_enabled?: boolean;
  };
  // Catalog gating: when present + non-empty, only these game ids are offered (absent ⇒ all enabled).
  enabled_game_types?: string[];
  // Tunable spark costs (informational mirror of the backend; balance endpoint remains authoritative).
  economy?: {
    cost_room?: number;
    cost_generate?: number;
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
  feature_flags: {
    show_upgrade_button: true,
    enable_image_generation: true,
    ads_enabled: false,
    referral_enabled: false,
    gifting_enabled: false,
    achievements_enabled: false,
  },
  enabled_game_types: undefined,   // absent ⇒ all games enabled
  economy: { cost_room: 10, cost_generate: 1 },
  announcements: [],
};
