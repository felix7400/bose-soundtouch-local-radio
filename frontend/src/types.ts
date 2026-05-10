export type SpeakerConfig = {
  host: string | null;
  port: number;
};

export type DiscoveredDevice = {
  host: string;
  port: number;
  name?: string | null;
  model?: string | null;
  device_id?: string | null;
  source: string;
  location?: string | null;
};

export type SpeakerStatus = {
  configured: boolean;
  reachable: boolean;
  error?: string | null;
  info?: Record<string, unknown> | null;
  now_playing?: Record<string, unknown> | null;
  volume?: Record<string, unknown> | null;
  sources: Array<Record<string, unknown>>;
  presets: Array<Record<string, unknown>>;
  app_playback?: AppPlayback | null;
};

export type Station = {
  id: string;
  name: string;
  stream_url: string;
  logo_url?: string | null;
  tags: string[];
  use_proxy_by_default: boolean;
  created_at: string;
  updated_at: string;
};

export type StationMetadata = {
  station_id: string;
  station_name: string;
  title?: string | null;
  artist?: string | null;
  track?: string | null;
  stream_url?: string | null;
  icy_name?: string | null;
  icy_genre?: string | null;
  raw?: string | null;
  error?: string | null;
};

export type StationPayload = {
  name: string;
  stream_url: string;
  logo_url?: string | null;
  tags: string[];
  use_proxy_by_default: boolean;
};

export type AppPlayback = {
  station_id?: string | null;
  playing: boolean;
  mode?: "direct" | "proxy" | null;
  stream_url?: string | null;
  updated_at?: string | null;
};

export type AppPreferences = {
  favorite_station_ids: string[];
  quick_buttons: Record<string, string | null>;
};

export type PlayStationResponse = {
  station: Station;
  mode: "direct" | "proxy";
  stream_url: string;
  speaker_response: Record<string, unknown>;
};

export type NetworkInfo = {
  local_ips: string[];
  port: number;
  alias_host?: string | null;
};
