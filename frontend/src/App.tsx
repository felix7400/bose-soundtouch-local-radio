import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import type {
  AppPreferences,
  NetworkInfo,
  SpeakerConfig,
  SpeakerStatus,
  Station,
  StationMetadata,
  StationPayload
} from "./types";

const emptyStation: StationPayload = {
  name: "",
  stream_url: "",
  logo_url: "",
  tags: [],
  use_proxy_by_default: true
};

const LAST_STATION_KEY = "soundtouch:last-station";
const THEME_KEY = "soundtouch:theme";
const FILTER_LABELS: Record<string, string> = {
  all: "All",
  bavaria: "Bavaria",
  austria: "Austria",
  italy: "Italy",
  germany: "Germany",
  news: "News",
  pop: "Pop",
  rock: "Rock",
  culture: "Culture",
  talk: "Talk",
  classic: "Classic",
  classical: "Classical",
  folk: "Folk",
  schlager: "Schlager",
  nrw: "NRW",
  southwest: "Southwest",
  north: "North",
  international: "International",
  france: "France",
  usa: "USA",
  indie: "Indie",
  electronic: "Electronic",
  ambient: "Ambient",
  jazz: "Jazz",
  science: "Science",
  eclectic: "Eclectic"
};

const defaultPreferences: AppPreferences = {
  favorite_station_ids: ["bayern-1", "bayern-3", "rock-antenne"],
  quick_buttons: {}
};

export function App() {
  const [network, setNetwork] = useState<NetworkInfo | null>(null);
  const [config, setConfig] = useState<SpeakerConfig>({ host: "", port: 8090 });
  const [status, setStatus] = useState<SpeakerStatus | null>(null);
  const [stations, setStations] = useState<Station[]>([]);
  const [lastStationId, setLastStationId] = useState<string | null>(() => localStorage.getItem(LAST_STATION_KEY));
  const [preferences, setPreferences] = useState<AppPreferences>(defaultPreferences);
  const [activeFilter, setActiveFilter] = useState("all");
  const [metadata, setMetadata] = useState<Record<string, StationMetadata>>({});
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem(THEME_KEY);
    return saved === "dark" || saved === "light" ? saved : "dark";
  });
  const [draft, setDraft] = useState<StationPayload>(emptyStation);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void boot();
    const timer = window.setInterval(() => {
      void refreshStatus();
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    const activeStation = findActiveStation(stations, status, lastStationId);
    if (!activeStation || !isPlaying(status)) {
      return;
    }
    void loadMetadata(activeStation.id);
    const timer = window.setInterval(() => {
      void loadMetadata(activeStation.id);
    }, 20000);
    return () => window.clearInterval(timer);
  }, [
    stations,
    status?.now_playing?.source,
    status?.now_playing?.playStatus,
    status?.app_playback?.station_id,
    status?.app_playback?.playing,
    lastStationId
  ]);

  async function boot() {
    await run("Loading", async () => {
      const [networkInfo, speakerConfig, speakerStatus, stationList] = await Promise.all([
        api.getNetwork(),
        api.getSpeakerConfig(),
        api.getSpeakerStatus(),
        api.listStations()
      ]);
      const savedPreferences = await api.getPreferences().catch(() => defaultPreferences);
      setNetwork(networkInfo);
      setConfig({ host: speakerConfig.host ?? "", port: speakerConfig.port });
      setStatus(speakerStatus);
      setStations(stationList);
      const nextPreferences = normalizePreferences(savedPreferences, stationList);
      setPreferences(nextPreferences);
      if (savedPreferences.favorite_station_ids.length === 0 && Object.keys(savedPreferences.quick_buttons).length === 0) {
        await api.savePreferences(nextPreferences);
      }
      if (!stationList.some((station) => station.id === lastStationId) && stationList[0]) {
        localStorage.setItem(LAST_STATION_KEY, stationList[0].id);
        setLastStationId(stationList[0].id);
      }
    });
  }

  async function refreshStatus() {
    try {
      setStatus(await api.getSpeakerStatus());
    } catch {
      // Status polling should not interrupt the main controls.
    }
  }

  async function run(label: string, operation: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try {
      await operation();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  }

  async function loadMetadata(stationId: string) {
    try {
      const nextMetadata = await api.getStationMetadata(stationId);
      setMetadata((current) => ({ ...current, [stationId]: nextMetadata }));
    } catch {
      // Some streams do not expose ICY metadata; station playback should remain unaffected.
    }
  }

  async function savePreferences(nextPreferences: AppPreferences) {
    const normalized = normalizePreferences(nextPreferences, stations);
    setPreferences(normalized);
    try {
      setPreferences(await api.savePreferences(normalized));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  function toggleFavorite(station: Station) {
    const current = preferences.favorite_station_ids;
    const favorite_station_ids = current.includes(station.id)
      ? current.filter((stationId) => stationId !== station.id)
      : [...current, station.id];
    void savePreferences({ ...preferences, favorite_station_ids });
  }

  async function playStation(station: Station) {
    await run(`Playing ${station.name}`, async () => {
      const response = await api.playStation(station.id, "auto");
      localStorage.setItem(LAST_STATION_KEY, response.station.id);
      setLastStationId(response.station.id);
      void loadMetadata(response.station.id);
      setStatus(await api.getSpeakerStatus());
    });
  }

  async function togglePlayback() {
    const playing = isPlaying(status);
    await run(playing ? "Pausing" : "Playing", async () => {
      if (playing) {
        await api.playback("stop");
      } else {
        const station = stations.find((item) => item.id === lastStationId) ?? stations[0];
        if (station) {
          const response = await api.playStation(station.id, "auto");
          localStorage.setItem(LAST_STATION_KEY, response.station.id);
          setLastStationId(response.station.id);
          void loadMetadata(response.station.id);
        } else {
          await api.playback("play");
        }
      }
      setStatus(await api.getSpeakerStatus());
    });
  }

  async function setVolume(level: number) {
    await run("Setting volume", async () => {
      await api.setVolume(level);
      setStatus(await api.getSpeakerStatus());
    });
  }

  async function saveSpeaker() {
    await run("Saving speaker", async () => {
      const saved = await api.saveSpeakerConfig({ host: config.host || null, port: config.port || 8090 });
      setConfig({ host: saved.host ?? "", port: saved.port });
      setStatus(await api.getSpeakerStatus());
    });
  }

  async function saveStation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(editingId ? "Saving station" : "Adding station", async () => {
      const payload = {
        ...draft,
        logo_url: draft.logo_url?.trim() || null,
        tags: draft.tags.map((tag) => tag.trim()).filter(Boolean),
        use_proxy_by_default: true
      };
      const saved = editingId ? await api.updateStation(editingId, payload) : await api.createStation(payload);
      setStations((current) =>
        editingId ? current.map((station) => (station.id === saved.id ? saved : station)) : [...current, saved]
      );
      setDraft(emptyStation);
      setEditingId(null);
    });
  }

  async function deleteStation(station: Station) {
    await run("Deleting station", async () => {
      await api.deleteStation(station.id);
      setStations((current) => current.filter((item) => item.id !== station.id));
      if (lastStationId === station.id) {
        localStorage.removeItem(LAST_STATION_KEY);
        setLastStationId(null);
      }
    });
  }

  function editStation(station: Station) {
    setEditingId(station.id);
    setDraft({
      name: station.name,
      stream_url: station.stream_url,
      logo_url: station.logo_url ?? "",
      tags: station.tags,
      use_proxy_by_default: true
    });
  }

  const speakerName = textFrom(status?.info?.name) || "Bose speaker";
  const reachable = Boolean(status?.reachable);
  const now = status?.now_playing ?? {};
  const volume = status?.volume ?? {};
  const currentVolume = numberFrom(volume.actualvolume) ?? numberFrom(volume.targetvolume) ?? 20;
  const playing = isPlaying(status);
  const activeStation = findActiveStation(stations, status, lastStationId);
  const activeMetadata = activeStation ? metadata[activeStation.id] : undefined;
  const filters = stationFilters(stations);
  const favoriteStations = preferences.favorite_station_ids
    .map((stationId) => stations.find((station) => station.id === stationId))
    .filter((station): station is Station => Boolean(station));
  const visibleStations = activeFilter === "all"
    ? stations
    : stations.filter((station) => station.tags.includes(activeFilter));
  const appUrl = network?.alias_host
    ? `http://${network.alias_host}:${network.port}`
    : network?.local_ips[0]
      ? `http://${network.local_ips[0]}:${network.port}`
      : "Loading local address";
  const displayTitle = activeMetadata?.track || activeMetadata?.title || activeStation?.name || statusTitle(now);
  const displaySubtitle = activeMetadata?.artist || activeStation?.name || statusSubtitle(now);

  return (
    <main className="app-shell">
      <div className="glow glow-a" />
      <div className="glow glow-b" />

      {(busy || error) && (
        <div className={error ? "notice error" : "notice"} role="status">
          {error || busy}
        </div>
      )}

      <section className="player glass-panel">
        <StationArtwork station={activeStation} title={displayTitle} className="disc" />
        <div className="player-copy">
          <p className="eyebrow">Now</p>
          <h2>{displayTitle}</h2>
          <p>{displaySubtitle}</p>
          {activeMetadata?.icy_name ? <span className="meta-pill">{activeMetadata.icy_name}</span> : null}
        </div>
        <button className="play-button" onClick={togglePlayback} disabled={!reachable}>
          {playing ? "Pause" : "Play"}
        </button>
        <div className="volume">
          <label htmlFor="volume">Volume {currentVolume}</label>
          <input
            id="volume"
            type="range"
            min="0"
            max="100"
            value={currentVolume}
            onChange={(event) => {
              const level = Number(event.currentTarget.value);
              setStatus((current) =>
                current ? { ...current, volume: { ...(current.volume ?? {}), actualvolume: String(level) } } : current
              );
            }}
            onMouseUp={(event) => setVolume(Number(event.currentTarget.value))}
            onTouchEnd={(event) => setVolume(Number(event.currentTarget.value))}
          />
        </div>
      </section>

      {favoriteStations.length > 0 ? (
        <section className="favorite-section" aria-label="Favorite stations">
          <h3>Favorites</h3>
          <div className="favorite-row">
            {favoriteStations.map((station) => (
              <button
                key={station.id}
                className={activeStation?.id === station.id && playing ? "favorite-pill active" : "favorite-pill"}
                onClick={() => playStation(station)}
              >
                <StationArtwork station={station} title={station.name} className="mini-mark" />
                {station.name}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <nav className="filter-bar" aria-label="Station filters">
        {filters.map((filter) => (
          <button
            key={filter}
            className={activeFilter === filter ? "filter-chip active" : "filter-chip"}
            onClick={() => setActiveFilter(filter)}
          >
            {FILTER_LABELS[filter] ?? titleCase(filter)}
          </button>
        ))}
      </nav>

      <section className="stations">
        {visibleStations.map((station) => (
          <article
            key={station.id}
            className={activeStation?.id === station.id && playing ? "station-card active" : "station-card"}
            onClick={() => playStation(station)}
            onKeyDown={(event) => {
              if ((event.key === "Enter" || event.key === " ") && reachable) {
                event.preventDefault();
                void playStation(station);
              }
            }}
            role="button"
            tabIndex={reachable ? 0 : -1}
            aria-disabled={!reachable}
          >
            <StationArtwork station={station} title={station.name} className="station-mark" />
            <button
              className={preferences.favorite_station_ids.includes(station.id) ? "favorite-toggle active" : "favorite-toggle"}
              onClick={(event) => {
                event.stopPropagation();
                toggleFavorite(station);
              }}
              aria-label={preferences.favorite_station_ids.includes(station.id) ? `Remove ${station.name} from favorites` : `Add ${station.name} to favorites`}
            >
              ★
            </button>
            <strong>{station.name}</strong>
            {metadata[station.id]?.title ? <em>{metadata[station.id]?.title}</em> : null}
            <small>{station.tags.join(" / ") || "radio"}</small>
          </article>
        ))}
      </section>

      <details className="settings glass-panel">
        <summary>Settings</summary>
        <div className="settings-grid">
          <section>
            <h3>Speaker</h3>
            <label>
              IP or hostname
              <input value={config.host ?? ""} onChange={(event) => setConfig({ ...config, host: event.target.value })} />
            </label>
            <label>
              Port
              <input type="number" value={config.port} onChange={(event) => setConfig({ ...config, port: Number(event.target.value) })} />
            </label>
            <button className="secondary" onClick={saveSpeaker}>Save speaker</button>
            <p className="settings-note">Phone URL: {appUrl}</p>
          </section>

          <section>
            <h3>{editingId ? "Edit station" : "Add station"}</h3>
            <form className="station-form" onSubmit={saveStation}>
              <label>
                Name
                <input required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
              </label>
              <label>
                Stream URL
                <input required value={draft.stream_url} onChange={(event) => setDraft({ ...draft, stream_url: event.target.value })} />
              </label>
              <label>
                Tags
                <input value={draft.tags.join(", ")} onChange={(event) => setDraft({ ...draft, tags: splitTags(event.target.value) })} />
              </label>
              <label>
                Image URL
                <input value={draft.logo_url ?? ""} onChange={(event) => setDraft({ ...draft, logo_url: event.target.value })} />
              </label>
              <div className="button-row">
                <button className="secondary" type="submit">{editingId ? "Save" : "Add"}</button>
                {editingId ? <button type="button" onClick={() => { setEditingId(null); setDraft(emptyStation); }}>Cancel</button> : null}
              </div>
            </form>
          </section>
        </div>

        <div className="manage-list">
          {stations.map((station) => (
            <div key={station.id} className="manage-row">
              <span>{station.name}</span>
              <button onClick={() => editStation(station)}>Edit</button>
              <button className="danger-text" onClick={() => deleteStation(station)}>Delete</button>
            </div>
          ))}
        </div>
      </details>

      <footer className="footer-status">
        <div className={reachable ? "status-badge online" : "status-badge"}>
          <span />
          {reachable ? `${speakerName} online` : "Speaker offline"}
        </div>
        <span>{appUrl}</span>
        <button className="theme-toggle" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
      </footer>
    </main>
  );
}

function isPlaying(status: SpeakerStatus | null): boolean {
  return Boolean(status?.app_playback?.playing) || textFrom(status?.now_playing?.playStatus) === "PLAY_STATE";
}

function StationArtwork({ station, title, className }: { station: Station | null; title: string; className: string }) {
  if (station?.logo_url) {
    return (
      <span className={className} aria-hidden="true">
        <img src={station.logo_url} alt="" />
      </span>
    );
  }
  return (
    <span className={className} aria-hidden="true">
      {initials(title)}
    </span>
  );
}

function findActiveStation(stations: Station[], status: SpeakerStatus | null, lastStationId: string | null): Station | null {
  const appStationId = status?.app_playback?.station_id;
  if (appStationId) {
    const appStation = stations.find((station) => station.id === appStationId);
    if (appStation) {
      return appStation;
    }
  }
  const source = textFrom(status?.now_playing?.source);
  if (source === "INVALID_SOURCE" || source === "STANDBY") {
    return stations.find((station) => station.id === lastStationId) ?? null;
  }
  const location = textFrom(status?.now_playing?.ContentItem).includes("/stream/")
    ? textFrom(status?.now_playing?.ContentItem)
    : textFrom(objectFrom(status?.now_playing?.ContentItem)?.location);
  const streamMatch = stations.find((station) => location.includes(station.id) || location === station.stream_url);
  return streamMatch ?? stations.find((station) => station.id === lastStationId) ?? null;
}

function statusTitle(now: Record<string, unknown>): string {
  const source = textFrom(now.source);
  if (!source || source === "STANDBY" || source === "INVALID_SOURCE") {
    return "Ready";
  }
  if (source === "UPNP") {
    return "Radio stream";
  }
  return source;
}

function statusSubtitle(now: Record<string, unknown>): string {
  const source = textFrom(now.source);
  if (source === "INVALID_SOURCE") {
    return "Choose a radio station below.";
  }
  if (source === "STANDBY") {
    return "Speaker is on standby.";
  }
  return textFrom(now.playStatus) || "Ready";
}

function textFrom(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (typeof value === "object" && "text" in value) {
    return textFrom((value as { text?: unknown }).text);
  }
  return "";
}

function objectFrom(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function numberFrom(value: unknown): number | null {
  const parsed = Number(textFrom(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function splitTags(value: string): string[] {
  return value.split(",").map((tag) => tag.trim()).filter(Boolean);
}

function stationFilters(stations: Station[]): string[] {
  const preferred = ["all", "bavaria", "austria", "italy", "germany", "international", "news", "pop", "rock", "culture", "classical", "electronic", "indie"];
  const tags = new Set(stations.flatMap((station) => station.tags));
  const ordered = preferred.filter((tag) => tag === "all" || tags.has(tag));
  const rest = [...tags].filter((tag) => !ordered.includes(tag)).sort();
  return [...ordered, ...rest];
}

function normalizePreferences(preferences: AppPreferences, stations: Station[]): AppPreferences {
  const stationIds = new Set(stations.map((station) => station.id));
  const fallback = stations.length > 0 ? defaultPreferences : preferences;
  const favorite_station_ids = (preferences.favorite_station_ids.length ? preferences.favorite_station_ids : fallback.favorite_station_ids)
    .filter((stationId, index, values) => stationIds.has(stationId) && values.indexOf(stationId) === index);
  const quick_buttons: Record<string, string | null> = {};
  Object.entries(preferences.quick_buttons).forEach(([slot, stationId]) => {
    if (stationId && stationIds.has(stationId)) {
      quick_buttons[slot] = stationId;
    }
  });
  return { favorite_station_ids, quick_buttons };
}

function titleCase(value: string): string {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

function initials(value: string): string {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "ST";
}
