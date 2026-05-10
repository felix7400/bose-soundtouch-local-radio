import type {
  AppPreferences,
  DiscoveredDevice,
  NetworkInfo,
  PlayStationResponse,
  SpeakerConfig,
  SpeakerStatus,
  Station,
  StationMetadata,
  StationPayload
} from "./types";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {})
    }
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      const text = await response.text();
      if (text) {
        message = text;
      }
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export const api = {
  getNetwork: () => request<NetworkInfo>("/api/network"),
  getSpeakerConfig: () => request<SpeakerConfig>("/api/speaker/config"),
  saveSpeakerConfig: (payload: SpeakerConfig) =>
    request<SpeakerConfig>("/api/speaker/config", { method: "POST", body: JSON.stringify(payload) }),
  discoverSpeakers: () => request<DiscoveredDevice[]>("/api/speaker/discover"),
  getSpeakerStatus: () => request<SpeakerStatus>("/api/speaker/status"),
  getPreferences: () => request<AppPreferences>("/api/preferences"),
  savePreferences: (payload: AppPreferences) =>
    request<AppPreferences>("/api/preferences", { method: "POST", body: JSON.stringify(payload) }),
  standby: () => request<Record<string, unknown>>("/api/speaker/standby", { method: "POST", body: "{}" }),
  playback: (action: "play" | "pause" | "stop" | "next" | "previous") =>
    request<Record<string, unknown>>("/api/speaker/playback", {
      method: "POST",
      body: JSON.stringify({ action })
    }),
  setVolume: (level: number) =>
    request<Record<string, unknown>>("/api/speaker/volume", {
      method: "POST",
      body: JSON.stringify({ level })
    }),
  setMute: (enabled: boolean) =>
    request<Record<string, unknown>>("/api/speaker/mute", {
      method: "POST",
      body: JSON.stringify({ enabled })
    }),
  selectSource: (source: string, sourceAccount = "") =>
    request<Record<string, unknown>>("/api/speaker/source", {
      method: "POST",
      body: JSON.stringify({ source, source_account: sourceAccount })
    }),
  selectPreset: (presetId: number) =>
    request<Record<string, unknown>>(`/api/speaker/preset/${presetId}`, { method: "POST", body: "{}" }),
  listStations: () => request<Station[]>("/api/stations"),
  createStation: (payload: StationPayload) =>
    request<Station>("/api/stations", { method: "POST", body: JSON.stringify(payload) }),
  updateStation: (id: string, payload: StationPayload) =>
    request<Station>(`/api/stations/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteStation: (id: string) => request<Record<string, unknown>>(`/api/stations/${id}`, { method: "DELETE" }),
  getStationMetadata: (id: string) => request<StationMetadata>(`/api/stations/${id}/metadata`),
  playStation: (id: string, mode: "direct" | "proxy" | "auto") =>
    request<PlayStationResponse>(`/api/stations/${id}/play`, {
      method: "POST",
      body: JSON.stringify({ mode })
    }),
};
