export interface Announcement {
  id: string;
  text: string;
  type: 'info' | 'warning';
  dismissible: boolean;
}

export interface RemoteConfig {
  version: number;
  welcome_message: string;
  operations: {
    maintenance: boolean;
    maintenance_message: string;
    maintenance_until: string | null;
  };
  pricing: {
    pass_price: string;
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
  operations: {
    maintenance: false,
    maintenance_message: '',
    maintenance_until: null,
  },
  pricing: {
    pass_price: '$2.99',
    duration_hours: 12,
    label: '12-Hour Party Pass',
  },
  feature_flags: {
    show_upgrade_button: false,
    enable_image_generation: true,
  },
  announcements: [],
};
