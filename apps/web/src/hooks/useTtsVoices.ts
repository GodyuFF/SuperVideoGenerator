/**
 * 从 AI 配置与 /api/ai/tts/voices 加载当前 TTS 服务商音色列表。
 */

import { useEffect, useState } from "react";

const API = "/api";

export interface TtsVoiceConfig {
  provider: string;
  locale: string;
  defaultVoice: string;
}

export interface UseTtsVoicesResult {
  voices: string[];
  config: TtsVoiceConfig | null;
  loading: boolean;
  error: string | null;
}

/** 拉取当前 TTS 配置下的可选音色。 */
export function useTtsVoices(enabled = true): UseTtsVoicesResult {
  const [voices, setVoices] = useState<string[]>([]);
  const [config, setConfig] = useState<TtsVoiceConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const cfgRes = await fetch(`${API}/ai/config`);
        const cfg = cfgRes.ok ? await cfgRes.json() : null;
        const provider = String(cfg?.tts?.provider ?? "edge");
        const locale = String(cfg?.tts?.default_language ?? "zh-CN");
        const defaultVoice = String(cfg?.tts?.default_voice ?? "");
        if (!cancelled) {
          setConfig({ provider, locale, defaultVoice });
        }
        const params = new URLSearchParams({ provider, locale });
        const voiceRes = await fetch(`${API}/ai/tts/voices?${params}`);
        if (!voiceRes.ok) {
          throw new Error(`加载音色失败 (${voiceRes.status})`);
        }
        const data = await voiceRes.json();
        if (!cancelled) {
          setVoices((data.voices as string[]) ?? []);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setVoices([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { voices, config, loading, error };
}

/** 请求短文本 TTS 试听 URL。 */
export async function previewTtsVoice(
  text: string,
  voice: string,
  provider?: string,
): Promise<string | null> {
  const sample = text.trim() || "这是一段配音试听。";
  const res = await fetch(`${API}/ai/tts/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: sample.slice(0, 120),
      voice: voice || undefined,
      provider: provider || undefined,
    }),
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { url?: string };
  return data.url ?? null;
}
