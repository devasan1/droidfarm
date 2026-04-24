export type PhoneStatus = "stopped" | "starting" | "running" | "stopping" | "crashed";
export type ProxyMode = "tun2socks" | "system-http" | "none";

export interface Proxy {
  id: number;
  label: string;
  scheme: "http" | "https" | "socks5";
  host: string;
  port: number;
  username: string | null;
  has_password: boolean;
  country: string | null;
  region: string | null;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
  timezone: string | null;
  asn: string | null;
  provider: string | null;
  is_healthy: boolean;
  last_checked_at: string | null;
  last_error: string | null;
  latency_ms: number | null;
  created_at: string;
  notes: string;
  assigned_to_phone_id: number | null;
  assigned_to_phone_name: string | null;
}

export interface ProxyIn {
  label?: string;
  scheme?: "http" | "https" | "socks5";
  host: string;
  port: number;
  username?: string;
  password?: string;
  notes?: string;
}

export interface Phone {
  id: number;
  name: string;
  ldplayer_index: number | null;
  device_profile: string;
  android_version: string;
  resolution: string;
  dpi: number;
  cpu: number;
  ram_mb: number;
  status: PhoneStatus;
  autostart: boolean;
  show_setup_wizard: boolean;
  proxy_mode: ProxyMode;
  proxy: Proxy | null;
  geo_overrides: Record<string, unknown>;
  preinstall_apks: number[];
  created_at: string;
  last_started_at: string | null;
  last_error: string | null;
}

export interface PhoneIn {
  name: string;
  device_profile?: string;
  android_version?: string;
  resolution?: string;
  dpi?: number;
  cpu?: number;
  ram_mb?: number;
  autostart?: boolean;
  proxy_mode?: ProxyMode;
  proxy_id?: number | null;
  auto_assign_proxy?: boolean;
  bypass_ip?: boolean;
  show_setup_wizard?: boolean;
  preinstall_apks?: number[];
  geo_override_country?: string | null;
  geo_override_city?: string | null;
}

export interface HostGeo {
  ok: boolean;
  error: string | null;
  ip: string | null;
  country: string | null;
  region: string | null;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
  timezone: string | null;
  provider: string | null;
}

export interface Apk {
  id: number;
  filename: string;
  package_name: string | null;
  version_name: string | null;
  size_bytes: number;
  sha256: string | null;
  added_at: string;
}
