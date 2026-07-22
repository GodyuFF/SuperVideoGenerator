/**
 * AI 配置页：分区管理 LLM / 图片 / 视频 / TTS。
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AiConfig, AiConfigPatch, AiConfigTab, ImageSourceMode } from "../types";
import { IMAGE_SOURCE_LABELS } from "../constants";
import { LocaleSwitcher } from "../i18n/LocaleSwitcher";
import { coerceAppLocale, applyAppLocale } from "../i18n/localeSync";
import { ThemeToggle } from "../components/theme/ThemeToggle";
import { AppShell } from "../components/layout/AppShell";
import { DesktopUpdateSection } from "../components/settings/DesktopUpdateSection";

interface AiSettingsPageProps {
  config: AiConfig | null;
  loading: boolean;
  loadError: string | null;
  onSave: (patch: AiConfigPatch) => Promise<AiConfig>;
  onBack: () => void;
  onRefresh: () => void;
}

const TAB_IDS: AiConfigTab[] = ["llm", "image", "video", "tts", "export", "embedding"];

const TAB_I18N_KEYS: Record<AiConfigTab, string> = {
  llm: "ai.tabs.llm",
  image: "ai.tabs.image",
  video: "ai.tabs.video",
  tts: "ai.tabs.tts",
  export: "ai.tabs.editExport",
  embedding: "ai.tabs.embedding",
};

const ARK_IMAGE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";
const ARK_SEEDREAM_MODEL = "doubao-seedream-5-0-pro";
const ARK_SEEDANCE_MODEL = "doubao-seedance-2-0";
const AGNES_IMAGE_BASE_URL = "https://apihub.agnes-ai.com/v1";
const AGNES_VIDEO_BASE_URL = "https://apihub.agnes-ai.com/v1";
const OPENAI_IMAGE_BASE_URL = "https://api.openai.com/v1";
const OPENAI_IMAGE_MODEL = "gpt-image-1";
const FAL_IMAGE_BASE_URL = "https://fal.run";
const FAL_IMAGE_MODEL = "fal-ai/flux-pro/v1.1";
const GEMINI_IMAGE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta";
const GEMINI_IMAGE_MODEL = "gemini-2.0-flash-preview-image-generation";
const KLING_VIDEO_BASE_URL = "https://api.klingai.com/v1";
const KLING_VIDEO_MODEL = "kling-v3-omni-video";
const RUNWAY_VIDEO_BASE_URL = "https://api.dev.runwayml.com/v1";
const RUNWAY_VIDEO_MODEL = "gen4.5";

/** 自定义尺寸在下拉中的哨兵值。 */
const CUSTOM_SIZE_VALUE = "__custom__";

/** Agnes / SD / 百炼默认尺寸。 */
const AGNES_IMAGE_SIZES = ["1024x768", "1024x1024", "768x1024"] as const;

/** 火山 SeedDream 推荐尺寸（总像素 ≥ 3686400）。 */
const SEEDREAM_IMAGE_SIZES = [
  "2K",
  "4K",
  "2048x2048",
  "2304x1728",
  "1728x2304",
  "2496x1664",
  "1664x2496",
  "2560x1440",
  "1440x2560",
  "3024x1296",
  "4096x4096",
  "4704x3520",
  "3520x4704",
  "5504x3040",
  "3040x5504",
] as const;

/** 尺寸选项展示标签（比例提示）。 */
const IMAGE_SIZE_LABELS: Record<string, string> = {
  "2K": "2K（模型自动比例）",
  "4K": "4K（模型自动比例）",
  "1024x768": "1024×768（4:3）",
  "1024x1024": "1024×1024（1:1）",
  "768x1024": "768×1024（3:4）",
  "2048x2048": "2048×2048（1:1）",
  "2304x1728": "2304×1728（4:3）",
  "1728x2304": "1728×2304（3:4）",
  "2496x1664": "2496×1664（3:2）",
  "1664x2496": "1664×2496（2:3）",
  "2560x1440": "2560×1440（16:9）",
  "1440x2560": "1440×2560（9:16）",
  "3024x1296": "3024×1296（21:9）",
  "4096x4096": "4096×4096（4K 1:1）",
  "4704x3520": "4704×3520（4K 4:3）",
  "3520x4704": "3520×4704（4K 3:4）",
  "5504x3040": "5504×3040（4K 16:9）",
  "3040x5504": "3040×5504（4K 9:16）",
};

/** 解析 WxH 文本。 */
function parseImageWh(size: string): { w: number; h: number } | null {
  const m = /^(\d+)\s*[x×]\s*(\d+)$/i.exec(size.trim());
  if (!m) return null;
  const w = Number(m[1]);
  const h = Number(m[2]);
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null;
  return { w, h };
}

/** 按生图服务商返回系统预设尺寸。 */
function imageSizesForProvider(provider: string, fromApi: string[] | undefined): string[] {
  if (provider === "volcengine") {
    return [...SEEDREAM_IMAGE_SIZES];
  }
  if (fromApi && fromApi.length > 0) {
    return fromApi;
  }
  return [...AGNES_IMAGE_SIZES];
}

/** 切换到火山时映射小尺寸；已是合法预设或自定义 WxH 则保留。 */
function mapSizeForImageProvider(provider: string, size: string): string {
  if (provider !== "volcengine") {
    return size;
  }
  const map: Record<string, string> = {
    "1024x1024": "2048x2048",
    "1024x768": "2304x1728",
    "768x1024": "1728x2304",
  };
  if (map[size]) {
    return map[size];
  }
  if ((SEEDREAM_IMAGE_SIZES as readonly string[]).includes(size)) {
    return size;
  }
  if (parseImageWh(size)) {
    return size.replace("×", "x");
  }
  return "2048x2048";
}

/** 组装自定义尺寸字符串。 */
function formatCustomImageSize(w: number, h: number): string {
  return `${Math.max(1, Math.round(w))}x${Math.max(1, Math.round(h))}`;
}

/** 切换生图服务商时回填推荐模型与 Base URL。 */
function imageDefaultsForProvider(
  provider: string,
  current: { model: string; baseUrl: string },
): { model: string; baseUrl: string } {
  if (provider === "volcengine") {
    return {
      model:
        !current.model || current.model.startsWith("agnes-")
          ? ARK_SEEDREAM_MODEL
          : current.model,
      baseUrl:
        !current.baseUrl || current.baseUrl.includes("agnes-ai.com")
          ? ARK_IMAGE_BASE_URL
          : current.baseUrl,
    };
  }
  if (provider === "agnes") {
    return {
      model:
        current.model === ARK_SEEDREAM_MODEL ? "agnes-image-2.1-flash" : current.model,
      baseUrl:
        current.baseUrl.includes("volces.com") ? AGNES_IMAGE_BASE_URL : current.baseUrl,
    };
  }
  if (provider === "openai") {
    return {
      model:
        !current.model || current.model.startsWith("agnes-") || current.model.startsWith("doubao-")
          ? OPENAI_IMAGE_MODEL
          : current.model,
      baseUrl:
        !current.baseUrl || current.baseUrl.includes("agnes-ai.com") || current.baseUrl.includes("volces.com")
          ? OPENAI_IMAGE_BASE_URL
          : current.baseUrl,
    };
  }
  if (provider === "fal") {
    return {
      model:
        !current.model || current.model.startsWith("agnes-") || current.model.startsWith("doubao-")
          ? FAL_IMAGE_MODEL
          : current.model,
      baseUrl:
        !current.baseUrl || current.baseUrl.includes("agnes-ai.com") || current.baseUrl.includes("openai.com")
          ? FAL_IMAGE_BASE_URL
          : current.baseUrl,
    };
  }
  if (provider === "gemini") {
    return {
      model:
        !current.model || current.model.startsWith("agnes-") || current.model.startsWith("doubao-")
          ? GEMINI_IMAGE_MODEL
          : current.model,
      baseUrl:
        !current.baseUrl || current.baseUrl.includes("agnes-ai.com")
          ? GEMINI_IMAGE_BASE_URL
          : current.baseUrl,
    };
  }
  return current;
}

/** 切换视频服务商时回填推荐模型与 Base URL。 */
function videoDefaultsForProvider(
  provider: string,
  current: { model: string; baseUrl: string },
): { model: string; baseUrl: string } {
  if (provider === "volcengine") {
    return {
      model:
        !current.model || current.model.startsWith("agnes-")
          ? ARK_SEEDANCE_MODEL
          : current.model,
      baseUrl:
        !current.baseUrl || current.baseUrl.includes("agnes-ai.com")
          ? ARK_IMAGE_BASE_URL
          : current.baseUrl,
    };
  }
  if (provider === "agnes") {
    return {
      model:
        current.model === ARK_SEEDANCE_MODEL ? "agnes-video-v2.0" : current.model,
      baseUrl:
        current.baseUrl.includes("volces.com") ? AGNES_VIDEO_BASE_URL : current.baseUrl,
    };
  }
  if (provider === "kling") {
    return {
      model:
        !current.model || current.model.startsWith("agnes-") || current.model.startsWith("doubao-")
          ? KLING_VIDEO_MODEL
          : current.model,
      baseUrl:
        !current.baseUrl || current.baseUrl.includes("agnes-ai.com") || current.baseUrl.includes("volces.com")
          ? KLING_VIDEO_BASE_URL
          : current.baseUrl,
    };
  }
  if (provider === "runway") {
    return {
      model:
        !current.model || current.model.startsWith("agnes-") || current.model.startsWith("doubao-")
          ? RUNWAY_VIDEO_MODEL
          : current.model,
      baseUrl:
        !current.baseUrl || current.baseUrl.includes("agnes-ai.com") || current.baseUrl.includes("volces.com")
          ? RUNWAY_VIDEO_BASE_URL
          : current.baseUrl,
    };
  }
  if (provider === "fal") {
    return {
      model:
        !current.model || current.model.startsWith("agnes-") || current.model.startsWith("doubao-")
          ? "fal-ai/kling-video/v2.1/master/image-to-video"
          : current.model,
      baseUrl:
        !current.baseUrl || current.baseUrl.includes("agnes-ai.com")
          ? FAL_IMAGE_BASE_URL
          : current.baseUrl,
    };
  }
  return current;
}

export function AiSettingsPage({
  config,
  loading,
  loadError,
  onSave,
  onBack,
  onRefresh,
}: AiSettingsPageProps) {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useState<AiConfigTab>("llm");

  /** TTS 默认语言若为 zh-CN/en，反向对齐界面语言与 ui-prefs。 */
  const syncUiFromTtsLanguage = useCallback(
    async (raw: string) => {
      const locale = coerceAppLocale(raw);
      if (!locale) return;
      const current = i18n.language === "en" ? "en" : "zh-CN";
      if (locale !== current) {
        await i18n.changeLanguage(locale);
      }
      await applyAppLocale(locale, { persistRemote: true, syncTts: false });
    },
    [i18n],
  );

  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [useLlmReact, setUseLlmReact] = useState(true);
  const [showReactDetails, setShowReactDetails] = useState(true);
  const [temperature, setTemperature] = useState(0.2);
  const [maxTokens, setMaxTokens] = useState(8192);
  const [contextWindowTokens, setContextWindowTokens] = useState(1_048_576);
  const [historyKeepMessages, setHistoryKeepMessages] = useState(10);

  const [imageEnabled, setImageEnabled] = useState(true);
  const [imageProvider, setImageProvider] = useState("agnes");
  const [imageModel, setImageModel] = useState("");
  const [imageBaseUrl, setImageBaseUrl] = useState("");
  const [imageApiKey, setImageApiKey] = useState("");
  const [imageSize, setImageSize] = useState("1024x768");
  const [imageSizeCustom, setImageSizeCustom] = useState(false);
  const [imageCustomW, setImageCustomW] = useState(2048);
  const [imageCustomH, setImageCustomH] = useState(2048);
  const [imageSourceDefault, setImageSourceDefault] = useState<ImageSourceMode>("generate");
  const [imageTextPreset, setImageTextPreset] = useState<"explainer" | "report" | "lecture">("explainer");
  const [comicPreset, setComicPreset] = useState<"manga" | "webtoon" | "ink">("manga");
  const [imageBatchPending, setImageBatchPending] = useState(true);
  const [imageSearchFallback, setImageSearchFallback] = useState(true);

  // SD fields
  const [sdDetected, setSdDetected] = useState(false);
  const [sdModels, setSdModels] = useState<string[]>([]);
  const [sdCurrentModel, setSdCurrentModel] = useState("");
  const [sdError, setSdError] = useState("");
  const [sdBaseUrl, setSdBaseUrl] = useState("http://127.0.0.1:7860");
  const [sdSteps, setSdSteps] = useState(20);
  const [sdCfgScale, setSdCfgScale] = useState(7.0);
  const [sdSampler, setSdSampler] = useState("Euler a");
  const [sdSamplers, setSdSamplers] = useState<string[]>(["Euler a"]);
  const [sdNegativePrompt, setSdNegativePrompt] = useState("");
  const [sdDetecting, setSdDetecting] = useState(false);

  // Bailian fields
  const [bailianWorkspaceId, setBailianWorkspaceId] = useState("");
  const [bailianTxt2imgModel, setBailianTxt2imgModel] = useState("qwen-image-2.0-pro");
  const [bailianImg2imgModel, setBailianImg2imgModel] = useState("qwen-image-2.0-pro");

  // Test image
  const [testPrompt, setTestPrompt] = useState("");
  const [testImageUrl, setTestImageUrl] = useState<string | null>(null);
  const [testImageLoading, setTestImageLoading] = useState(false);
  const [testImageError, setTestImageError] = useState<string | null>(null);

  const [videoEnabled, setVideoEnabled] = useState(false);
  const [videoProvider, setVideoProvider] = useState("agnes");
  const [videoModel, setVideoModel] = useState("");
  const [videoBaseUrl, setVideoBaseUrl] = useState("");
  const [videoApiKey, setVideoApiKey] = useState("");
  const [videoMaxDuration, setVideoMaxDuration] = useState(10);
  const [videoResolution, setVideoResolution] = useState("1080p");

  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [ttsProvider, setTtsProvider] = useState("edge");
  const [ttsModel, setTtsModel] = useState("");
  const [ttsBaseUrl, setTtsBaseUrl] = useState("");
  const [ttsApiKey, setTtsApiKey] = useState("");
  const [ttsLanguage, setTtsLanguage] = useState("zh-CN");
  const [ttsVoice, setTtsVoice] = useState("");
  const [ttsRate, setTtsRate] = useState(1);
  const [ttsVolume, setTtsVolume] = useState(1);
  const [ttsVoices, setTtsVoices] = useState<string[]>([]);
  const [ttsPreviewText, setTtsPreviewText] = useState("你好，这是一段配音试听。");
  const [ttsPreviewUrl, setTtsPreviewUrl] = useState<string | null>(null);
  const [ttsPreviewLoading, setTtsPreviewLoading] = useState(false);
  const [geminiApiKey, setGeminiApiKey] = useState("");
  const [mimoApiKey, setMimoApiKey] = useState("");
  const [siliconflowApiKey, setSiliconflowApiKey] = useState("");
  const [azureSpeechKey, setAzureSpeechKey] = useState("");
  const [azureSpeechRegion, setAzureSpeechRegion] = useState("");

  const [exportEnabled, setExportEnabled] = useState(true);
  const [exportFfmpegPath, setExportFfmpegPath] = useState("");
  const [exportFps, setExportFps] = useState(30);
  const [exportWidth, setExportWidth] = useState(1920);
  const [exportHeight, setExportHeight] = useState(1080);
  const [exportCrf, setExportCrf] = useState(23);

  const [embeddingEnabled, setEmbeddingEnabled] = useState(true);
  const [embeddingBaseUrl, setEmbeddingBaseUrl] = useState("https://api.openai.com/v1");
  const [embeddingModel, setEmbeddingModel] = useState("text-embedding-3-small");
  const [embeddingApiKey, setEmbeddingApiKey] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!config) return;
    const llm = config.llm;
    setProvider(llm.provider);
    setModel(llm.model);
    setBaseUrl(llm.base_url);
    setUseLlmReact(llm.use_llm_react);
    setShowReactDetails(llm.show_react_details ?? true);
    setTemperature(llm.temperature);
    setMaxTokens(llm.max_tokens);
    setContextWindowTokens(llm.context_window_tokens ?? 1_048_576);
    setHistoryKeepMessages(llm.history_keep_messages ?? 10);
    setLlmApiKey("");

    const img = config.image;
    setImageEnabled(img.enabled);
    setImageProvider(img.provider);
    setImageModel(img.model);
    setImageBaseUrl(img.base_url);
    const mappedSize = mapSizeForImageProvider(img.provider, img.default_size);
    const presets = imageSizesForProvider(img.provider, img.available_sizes);
    if (presets.includes(mappedSize)) {
      setImageSizeCustom(false);
      setImageSize(mappedSize);
    } else {
      const wh = parseImageWh(mappedSize) ?? { w: 2048, h: 2048 };
      setImageSizeCustom(true);
      setImageCustomW(wh.w);
      setImageCustomH(wh.h);
      setImageSize(formatCustomImageSize(wh.w, wh.h));
    }
    setImageApiKey("");
    const pipe = img.pipeline;
    setImageSourceDefault(pipe.source_mode);
    setImageTextPreset(pipe.image_text_preset);
    setComicPreset(pipe.comic_preset);
    setImageBatchPending(pipe.batch_pending_assets);
    setImageSearchFallback(pipe.allow_search_fallback);
    // SD fields
    setSdDetected(img.sd_detected);
    setSdModels(img.sd_models ?? []);
    setSdCurrentModel(img.sd_current_model ?? "");
    setSdError(img.sd_error ?? "");
    setSdBaseUrl(img.sd_base_url ?? "http://127.0.0.1:7860");
    setSdSteps(img.sd_steps ?? 20);
    setSdCfgScale(img.sd_cfg_scale ?? 7.0);
    setSdSampler(img.sd_sampler ?? "Euler a");
    setSdSamplers(img.sd_samplers ?? ["Euler a"]);
    setSdNegativePrompt(img.sd_negative_prompt ?? "");
    // Bailian fields
    setBailianWorkspaceId(img.bailian_workspace_id ?? "");
    setBailianTxt2imgModel(img.bailian_txt2img_model ?? "qwen-image-2.0-pro");
    setBailianImg2imgModel(img.bailian_img2img_model ?? "qwen-image-2.0-pro");

    const vid = config.video;
    setVideoEnabled(vid.enabled);
    setVideoProvider(vid.provider);
    setVideoModel(vid.model);
    setVideoBaseUrl(vid.base_url);
    setVideoMaxDuration(vid.max_duration_sec);
    setVideoResolution(vid.resolution);
    setVideoApiKey("");

    const tts = config.tts;
    setTtsEnabled(tts.enabled);
    setTtsProvider(tts.provider);
    setTtsModel(tts.model);
    setTtsBaseUrl(tts.base_url);
    setTtsLanguage(tts.default_language);
    setTtsVoice(tts.default_voice || "");
    setTtsRate(tts.voice_rate ?? 1);
    setTtsVolume(tts.voice_volume ?? 1);
    setAzureSpeechRegion(tts.azure_speech_region || "");
    setTtsApiKey("");
    setGeminiApiKey("");
    setMimoApiKey("");
    setSiliconflowApiKey("");
    setAzureSpeechKey("");

    const exp = config.export;
    setExportEnabled(exp.enabled);
    setExportFfmpegPath(exp.ffmpeg_path || "");
    setExportFps(exp.fps ?? 30);
    setExportWidth(exp.width ?? 1920);
    setExportHeight(exp.height ?? 1080);
    setExportCrf(exp.crf ?? 23);

    const emb = config.embedding;
    if (emb) {
      setEmbeddingEnabled(emb.enabled ?? true);
      setEmbeddingBaseUrl(emb.base_url || "https://api.openai.com/v1");
      setEmbeddingModel(emb.model || "text-embedding-3-small");
      setEmbeddingApiKey("");
    }
  }, [config]);

  const loadTtsVoices = useCallback(async (locale: string) => {
    try {
      const params = locale ? `?locale=${encodeURIComponent(locale)}` : "";
      const r = await fetch(`/api/ai/tts/voices${params}`);
      if (!r.ok) return;
      const data = await r.json();
      const voices = (data.voices as string[]) ?? [];
      setTtsVoices(voices);
      if (voices.length > 0 && !voices.includes(ttsVoice)) {
        setTtsVoice(voices[0]);
      }
    } catch {
      /* ignore */
    }
  }, [ttsVoice]);

  useEffect(() => {
    if (tab === "tts") {
      void loadTtsVoices(ttsLanguage);
    }
  }, [tab, ttsLanguage, loadTtsVoices]);

  const selectedProvider = config?.llm.available_providers.find((p) => p.id === provider);

  function handleProviderChange(id: string) {
    setProvider(id);
    const p = config?.llm.available_providers.find((x) => x.id === id);
    if (p) setModel(p.default_model);
  }

  function buildPatch(): AiConfigPatch {
    const patch: AiConfigPatch = {
      llm: {
        provider,
        model,
        base_url: baseUrl || undefined,
        use_llm_react: useLlmReact,
        show_react_details: showReactDetails,
        temperature,
        max_tokens: maxTokens,
        context_window_tokens: contextWindowTokens,
        history_keep_messages: historyKeepMessages,
      },
      image: {
        enabled: imageEnabled,
        provider: imageProvider,
        model: imageModel,
        base_url: imageBaseUrl || undefined,
        default_size: imageSize,
        sd_base_url: sdBaseUrl || undefined,
        sd_steps: sdSteps,
        sd_cfg_scale: sdCfgScale,
        sd_sampler: sdSampler || undefined,
        sd_negative_prompt: sdNegativePrompt || undefined,
        bailian_workspace_id: bailianWorkspaceId || undefined,
        bailian_txt2img_model: bailianTxt2imgModel || undefined,
        bailian_img2img_model: bailianImg2imgModel || undefined,
        pipeline: {
          source_mode: imageSourceDefault,
          image_text_preset: imageTextPreset,
          comic_preset: comicPreset,
          batch_pending_assets: imageBatchPending,
          allow_search_fallback: imageSearchFallback,
        },
      },
      video: {
        enabled: videoEnabled,
        provider: videoProvider,
        model: videoModel,
        base_url: videoBaseUrl || undefined,
        max_duration_sec: videoMaxDuration,
        resolution: videoResolution,
      },
      tts: {
        enabled: ttsEnabled,
        provider: ttsProvider,
        model: ttsModel,
        base_url: ttsBaseUrl || undefined,
        default_language: ttsLanguage,
        default_voice: ttsVoice || undefined,
        voice_rate: ttsRate,
        voice_volume: ttsVolume,
        azure_speech_region: azureSpeechRegion || undefined,
      },
      export: {
        enabled: exportEnabled,
        ffmpeg_path: exportFfmpegPath || undefined,
        fps: exportFps,
        width: exportWidth,
        height: exportHeight,
        crf: exportCrf,
      },
      embedding: {
        enabled: embeddingEnabled,
        base_url: embeddingBaseUrl || undefined,
        model: embeddingModel || undefined,
      },
    };
    if (llmApiKey.trim()) patch.llm!.api_key = llmApiKey.trim();
    if (imageApiKey.trim()) patch.image!.api_key = imageApiKey.trim();
    if (videoApiKey.trim()) patch.video!.api_key = videoApiKey.trim();
    if (ttsApiKey.trim()) patch.tts!.api_key = ttsApiKey.trim();
    if (geminiApiKey.trim()) patch.tts!.gemini_api_key = geminiApiKey.trim();
    if (mimoApiKey.trim()) patch.tts!.mimo_api_key = mimoApiKey.trim();
    if (siliconflowApiKey.trim()) patch.tts!.siliconflow_api_key = siliconflowApiKey.trim();
    if (azureSpeechKey.trim()) patch.tts!.azure_speech_key = azureSpeechKey.trim();
    if (embeddingApiKey.trim()) patch.embedding!.api_key = embeddingApiKey.trim();
    return patch;
  }

  async function saveConfig(andBack = false) {
    setSaving(true);
    setSaveMsg(null);
    setSaveError(null);
    try {
      if (useLlmReact && !config?.llm.has_api_key && !llmApiKey.trim()) {
        setSaveError("启用 LLM ReAct 时必须填写 LLM API Key");
        setSaving(false);
        return false;
      }
      const updated = await onSave(buildPatch());
      await syncUiFromTtsLanguage(ttsLanguage);
      setSaveMsg(
        updated.llm.llm_active
          ? "保存成功，AI 已就绪，可以返回对话。"
          : "已保存。请填写 LLM API Key 并启用 ReAct。"
      );
      setLlmApiKey("");
      setImageApiKey("");
      setVideoApiKey("");
      setTtsApiKey("");
      if (andBack && updated.llm.llm_active) {
        onBack();
      }
      return true;
    } catch (err) {
      setSaveError((err as Error).message || "保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await saveConfig(false);
  }

  async function handleSaveAndBack() {
    await saveConfig(true);
  }

  const statusLabel = config?.llm.llm_active ? "LLM 已配置" : "LLM 未配置 Key";

  // SD 检测
  async function detectSd() {
    setSdDetecting(true);
    setSdError("");
    try {
      const r = await fetch("/api/ai/image/detect-sd", { method: "POST" });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: "检测失败" }));
        throw new Error(typeof err.detail === "string" ? err.detail : "检测失败");
      }
      const data = await r.json();
      setSdDetected(data.available);
      setSdCurrentModel(data.current_model ?? "");
      setSdModels(data.models ?? []);
      if (!data.available) {
        setSdError(data.error ?? "未检测到本地 SD");
      }
    } catch (e) {
      setSdDetected(false);
      setSdError((e as Error).message || "检测失败");
    } finally {
      setSdDetecting(false);
    }
  }

  // 测试生图
  async function testImageGen() {
    if (!testPrompt.trim()) return;
    setTestImageLoading(true);
    setTestImageError(null);
    setTestImageUrl(null);
    try {
      const r = await fetch("/api/ai/image/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: testPrompt.trim() }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: "测试生图失败" }));
        throw new Error(typeof err.detail === "string" ? err.detail : "测试生图失败");
      }
      const data = await r.json();
      setTestImageUrl(data.url as string);
    } catch (e) {
      setTestImageError((e as Error).message || "测试生图失败");
    } finally {
      setTestImageLoading(false);
    }
  }

  return (
    <AppShell
      pageClass="settings-page"
      mainClass="settings-main"
      className="settings-top-bar"
      title={t("aiConfig", { ns: "nav" })}
      badge={
        config ? (
          <span
            className={`status-badge ${config.llm.llm_active ? "ai-ready" : "ai-missing"}`}
          >
            {statusLabel}
          </span>
        ) : undefined
      }
      lead={
        <button type="button" className="btn-secondary" onClick={onBack}>
          {t("backToChat", { ns: "nav" })}
        </button>
      }
      trail={
        <>
          <ThemeToggle />
          <LocaleSwitcher />
        </>
      }
    >
        {loading && <p className="muted">{t("actions.loading", { ns: "common" })}</p>}

        {loadError && (
          <div className="settings-alert error">
            <p>{loadError}</p>
            <button type="button" onClick={onRefresh}>{t("actions.retry", { ns: "common" })}</button>
          </div>
        )}

        {!loading && config && (
          <>
            <nav className="settings-tabs" aria-label={t("aiConfig", { ns: "nav" })}>
              {TAB_IDS.map((tabId) => (
                <button
                  key={tabId}
                  type="button"
                  className={`settings-tab ${tab === tabId ? "active" : ""}`}
                  onClick={() => setTab(tabId)}
                >
                  {t(TAB_I18N_KEYS[tabId], { ns: "settings" })}
                  {tabId === "llm" && config.llm.llm_active && (
                    <span className="settings-tab-dot" aria-hidden />
                  )}
                  {tabId === "image" && config.image.active && (
                    <span className="settings-tab-dot" aria-hidden />
                  )}
                </button>
              ))}
            </nav>

            <DesktopUpdateSection />

            <form className="settings-form" onSubmit={handleSubmit}>
              {tab === "llm" && (
                <>
                  <p className="muted settings-intro">
                    ReAct 编排所用大模型。默认 DeepSeek，可切换 Anthropic 等兼容接口。
                  </p>
                  <label className="settings-field">
                    <span>服务商</span>
                    <select
                      value={provider}
                      onChange={(e) => handleProviderChange(e.target.value)}
                    >
                      {config.llm.available_providers.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}（默认 {p.default_model}）
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="settings-field">
                    <span>模型名称</span>
                    <input
                      type="text"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      placeholder={selectedProvider?.default_model ?? "model-id"}
                    />
                  </label>
                  <label className="settings-field">
                    <span>API Key</span>
                    <input
                      type="password"
                      value={llmApiKey}
                      onChange={(e) => setLlmApiKey(e.target.value)}
                      placeholder={
                        config.llm.has_api_key ? "已配置（留空不修改）" : "请输入 API Key"
                      }
                      autoComplete="off"
                    />
                  </label>
                  <label className="settings-field">
                    <span>API Base URL（可选）</span>
                    <input
                      type="text"
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      placeholder={config.llm.base_url}
                    />
                  </label>
                  <label className="settings-field checkbox-row">
                    <input
                      type="checkbox"
                      checked={useLlmReact}
                      onChange={(e) => setUseLlmReact(e.target.checked)}
                    />
                    <span>启用 LLM ReAct（关闭后使用规则回退，无需 Key）</span>
                  </label>
                  <label className="settings-field checkbox-row">
                    <input
                      type="checkbox"
                      checked={showReactDetails}
                      onChange={(e) => setShowReactDetails(e.target.checked)}
                    />
                    <span>展示完整思维过程（关闭后工作台仅显示所调用的工具名称）</span>
                  </label>
                  <div className="settings-row">
                    <label className="settings-field">
                      <span>Temperature</span>
                      <input
                        type="number"
                        min={0}
                        max={2}
                        step={0.1}
                        value={temperature}
                        onChange={(e) => setTemperature(Number(e.target.value))}
                      />
                    </label>
                    <label className="settings-field">
                      <span>输出 Token 上限</span>
                      <input
                        type="number"
                        min={256}
                        max={393216}
                        step={256}
                        value={maxTokens}
                        onChange={(e) => setMaxTokens(Number(e.target.value))}
                      />
                    </label>
                  </div>
                  <div className="settings-row">
                    <label className="settings-field">
                      <span>输入 Token 上限</span>
                      <input
                        type="number"
                        min={4096}
                        max={2_000_000}
                        step={1024}
                        value={contextWindowTokens}
                        onChange={(e) => setContextWindowTokens(Number(e.target.value))}
                      />
                    </label>
                    <label className="settings-field">
                      <span>压缩保留轮次</span>
                      <input
                        type="number"
                        min={1}
                        max={50}
                        step={1}
                        value={historyKeepMessages}
                        onChange={(e) => setHistoryKeepMessages(Number(e.target.value))}
                      />
                    </label>
                  </div>
                  <div className="settings-row">
                    <span className="muted" style={{ fontSize: "0.85rem" }}>
                      输出上限最大 384K；复核分镜等大 JSON tool 调用建议 32K 以上。常用预设：
                    </span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setMaxTokens(8192)}
                    >
                      8K
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setMaxTokens(32_768)}
                    >
                      32K
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setMaxTokens(393_216)}
                    >
                      384K
                    </button>
                  </div>
                  <div className="settings-row">
                    <span className="muted" style={{ fontSize: "0.85rem" }}>
                      输入上限默认 1M；仅当预估输入超过该值时触发历史压缩。常用预设：
                    </span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setContextWindowTokens(131_072)}
                    >
                      128K
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setContextWindowTokens(200_000)}
                    >
                      200K
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setContextWindowTokens(1_048_576)}
                    >
                      1M
                    </button>
                  </div>
                </>
              )}

              {tab === "image" && (
                <>
                  <p className="muted settings-intro">
                    选择生图服务商：Agnes AI、火山 SeedDream、百炼、OpenAI、fal.ai FLUX、Gemini 或本地 SD。
                  </p>
                  <label className="settings-field checkbox-row">
                    <input
                      type="checkbox"
                      checked={imageEnabled}
                      onChange={(e) => setImageEnabled(e.target.checked)}
                    />
                    <span>启用 AI 生图</span>
                  </label>

                  {/* ---- 服务商选择 ---- */}
                  <label className="settings-field">
                    <span>服务商</span>
                    <select
                      value={imageProvider}
                      onChange={(e) => {
                        const next = e.target.value;
                        const defaults = imageDefaultsForProvider(next, {
                          model: imageModel,
                          baseUrl: imageBaseUrl,
                        });
                        setImageProvider(next);
                        setImageModel(defaults.model);
                        setImageBaseUrl(defaults.baseUrl);
                        const mapped = mapSizeForImageProvider(next, imageSize);
                        const presets = imageSizesForProvider(
                          next,
                          config.image.available_sizes,
                        );
                        if (presets.includes(mapped)) {
                          setImageSizeCustom(false);
                          setImageSize(mapped);
                        } else {
                          const wh = parseImageWh(mapped) ?? { w: 2048, h: 2048 };
                          setImageSizeCustom(true);
                          setImageCustomW(wh.w);
                          setImageCustomH(wh.h);
                          setImageSize(formatCustomImageSize(wh.w, wh.h));
                        }
                      }}
                    >
                      {(config.image.available_providers ?? []).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* ---- 本地 SD 状态 + 检测 ---- */}
                  {imageProvider === "local_sd" && (
                    <div className={`sd-status ${sdDetected ? "sd-ready" : "sd-missing"}`}>
                      {sdDetected ? (
                        <p className="sd-status-ok">
                          ✓ 本地 SD 已连接 — 当前模型：{sdCurrentModel || "未知"}
                          {sdModels.length > 0 && (
                            <span className="sd-model-count">（{sdModels.length} 个可用模型）</span>
                          )}
                        </p>
                      ) : (
                        <p className="sd-status-err">
                          {sdError
                            ? `✗ ${sdError}`
                            : "未检测到本地 SD，请确保 Stable Diffusion WebUI 已启动"}
                        </p>
                      )}
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={sdDetecting}
                        onClick={detectSd}
                      >
                        {sdDetecting
                          ? t("ai.detecting", { ns: "settings" })
                          : t("ai.detect", { ns: "settings" })}
                      </button>
                    </div>
                  )}

                  {/* ---- Agnes 专属字段 ---- */}
                  {imageProvider === "agnes" && (
                    <>
                      <label className="settings-field">
                        <span>模型</span>
                        <input
                          type="text"
                          value={imageModel}
                          onChange={(e) => setImageModel(e.target.value)}
                          placeholder="agnes-image-2.0-flash"
                        />
                      </label>
                      <label className="settings-field">
                        <span>API Key</span>
                        <input
                          type="password"
                          value={imageApiKey}
                          onChange={(e) => setImageApiKey(e.target.value)}
                          placeholder={
                            config.image.has_api_key ? "已配置（留空不修改）" : "Agnes API Key"
                          }
                          autoComplete="off"
                        />
                      </label>
                      <label className="settings-field">
                        <span>Base URL</span>
                        <input
                          type="text"
                          value={imageBaseUrl}
                          onChange={(e) => setImageBaseUrl(e.target.value)}
                          placeholder={config.image.base_url}
                        />
                      </label>
                    </>
                  )}

                  {/* ---- SD 专属字段 ---- */}
                  {imageProvider === "local_sd" && (
                    <>
                      <label className="settings-field">
                        <span>SD Base URL</span>
                        <input
                          type="text"
                          value={sdBaseUrl}
                          onChange={(e) => setSdBaseUrl(e.target.value)}
                          placeholder="http://127.0.0.1:7860"
                        />
                      </label>
                      <div className="settings-row">
                        <label className="settings-field">
                          <span>Steps（{sdSteps}）</span>
                          <input
                            type="range"
                            min={1}
                            max={50}
                            value={sdSteps}
                            onChange={(e) => setSdSteps(Number(e.target.value))}
                          />
                        </label>
                        <label className="settings-field">
                          <span>CFG Scale（{sdCfgScale.toFixed(1)}）</span>
                          <input
                            type="range"
                            min={1}
                            max={20}
                            step={0.5}
                            value={sdCfgScale}
                            onChange={(e) => setSdCfgScale(Number(e.target.value))}
                          />
                        </label>
                      </div>
                      <label className="settings-field">
                        <span>采样器</span>
                        <select
                          value={sdSampler}
                          onChange={(e) => setSdSampler(e.target.value)}
                        >
                          {sdSamplers.map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="settings-field">
                        <span>Negative Prompt（可选）</span>
                        <input
                          type="text"
                          value={sdNegativePrompt}
                          onChange={(e) => setSdNegativePrompt(e.target.value)}
                          placeholder="如：low quality, blurry, distorted"
                        />
                      </label>
                    </>
                  )}

                  {/* ---- 百炼专属字段 ---- */}
                  {imageProvider === "bailian" && (
                    <>
                      <label className="settings-field">
                        <span>Workspace ID</span>
                        <input
                          type="text"
                          value={bailianWorkspaceId}
                          onChange={(e) => setBailianWorkspaceId(e.target.value)}
                          placeholder="如：your-workspace-id"
                        />
                        <p className="field-hint" style={{ margin: "4px 0 0", fontSize: "0.75rem" }}>
                          在百炼控制台 → 模型广场 → 模型详情页面 URL 中查看
                        </p>
                      </label>
                      <label className="settings-field">
                        <span>文生图模型 (Txt2img)</span>
                        <input
                          type="text"
                          value={bailianTxt2imgModel}
                          onChange={(e) => setBailianTxt2imgModel(e.target.value)}
                          placeholder="qwen-image-2.0-pro"
                        />
                      </label>
                      <label className="settings-field">
                        <span>图生图/编辑模型 (Img2img)</span>
                        <input
                          type="text"
                          value={bailianImg2imgModel}
                          onChange={(e) => setBailianImg2imgModel(e.target.value)}
                          placeholder="qwen-image-2.0-pro"
                        />
                      </label>
                      <label className="settings-field">
                        <span>API Key</span>
                        <input
                          type="password"
                          value={imageApiKey}
                          onChange={(e) => setImageApiKey(e.target.value)}
                          placeholder={
                            config.image.has_api_key ? "已配置（留空不修改）" : "DashScope API Key"
                          }
                          autoComplete="off"
                        />
                      </label>
                    </>
                  )}

                  {imageProvider === "volcengine" && (
                    <>
                      <label className="settings-field">
                        <span>模型</span>
                        <input
                          type="text"
                          value={imageModel}
                          onChange={(e) => setImageModel(e.target.value)}
                          placeholder="doubao-seedream-5-0-pro"
                        />
                      </label>
                      <label className="settings-field">
                        <span>API Key</span>
                        <input
                          type="password"
                          value={imageApiKey}
                          onChange={(e) => setImageApiKey(e.target.value)}
                          placeholder={
                            config.image.has_api_key ? "已配置（留空不修改）" : "火山方舟 ARK API Key"
                          }
                          autoComplete="off"
                        />
                      </label>
                      <label className="settings-field">
                        <span>Base URL</span>
                        <input
                          type="text"
                          value={imageBaseUrl}
                          onChange={(e) => setImageBaseUrl(e.target.value)}
                          placeholder="https://ark.cn-beijing.volces.com/api/v3"
                        />
                      </label>
                    </>
                  )}

                  <div className="settings-field">
                    <span>默认尺寸</span>
                    <select
                      value={imageSizeCustom ? CUSTOM_SIZE_VALUE : imageSize}
                      onChange={(e) => {
                        const next = e.target.value;
                        if (next === CUSTOM_SIZE_VALUE) {
                          const wh = parseImageWh(imageSize) ?? {
                            w: imageProvider === "volcengine" ? 2048 : 1024,
                            h: imageProvider === "volcengine" ? 2048 : 1024,
                          };
                          setImageSizeCustom(true);
                          setImageCustomW(wh.w);
                          setImageCustomH(wh.h);
                          setImageSize(formatCustomImageSize(wh.w, wh.h));
                          return;
                        }
                        setImageSizeCustom(false);
                        setImageSize(next);
                      }}
                    >
                      <optgroup label="系统预设">
                        {imageSizesForProvider(
                          imageProvider,
                          config.image.available_sizes,
                        ).map((s) => (
                          <option key={s} value={s}>
                            {IMAGE_SIZE_LABELS[s] ?? s}
                          </option>
                        ))}
                      </optgroup>
                      <option value={CUSTOM_SIZE_VALUE}>自定义像素…</option>
                    </select>
                    {imageSizeCustom && (
                      <div
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          gap: 8,
                          alignItems: "center",
                          marginTop: 8,
                        }}
                      >
                        <input
                          type="number"
                          min={64}
                          max={imageProvider === "volcengine" ? 8192 : 4096}
                          step={1}
                          value={imageCustomW}
                          onChange={(e) => {
                            const w = Number(e.target.value) || 0;
                            setImageCustomW(w);
                            setImageSize(formatCustomImageSize(w, imageCustomH));
                          }}
                          aria-label="自定义宽度"
                          style={{ width: 96 }}
                        />
                        <span style={{ opacity: 0.7 }}>×</span>
                        <input
                          type="number"
                          min={64}
                          max={imageProvider === "volcengine" ? 8192 : 4096}
                          step={1}
                          value={imageCustomH}
                          onChange={(e) => {
                            const h = Number(e.target.value) || 0;
                            setImageCustomH(h);
                            setImageSize(formatCustomImageSize(imageCustomW, h));
                          }}
                          aria-label="自定义高度"
                          style={{ width: 96 }}
                        />
                        <span style={{ fontSize: 12, opacity: 0.75 }}>
                          {imageCustomW * imageCustomH >= 3_686_400
                            ? `${imageCustomW}×${imageCustomH} · ${Math.round(
                                (imageCustomW * imageCustomH) / 1_000_000,
                              )}M 像素`
                            : imageProvider === "volcengine"
                              ? `当前 ${imageCustomW * imageCustomH} 像素（火山建议 ≥ 3686400，保存后会自动放大）`
                              : `${imageCustomW}×${imageCustomH}`}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* ---- 测试生图 ---- */}
                  <div className="settings-field test-image-section">
                    <span>测试生图</span>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <input
                        type="text"
                        value={testPrompt}
                        onChange={(e) => setTestPrompt(e.target.value)}
                        placeholder="输入测试 prompt…"
                        style={{ flex: 1, minWidth: 200 }}
                      />
                      <button
                        type="button"
                        disabled={testImageLoading || !testPrompt.trim()}
                        onClick={testImageGen}
                      >
                        {testImageLoading
                          ? t("ai.testImageGenerating", { ns: "settings" })
                          : t("ai.testImage", { ns: "settings" })}
                      </button>
                    </div>
                    {testImageError && (
                      <p className="board-error" style={{ marginTop: 8 }}>{testImageError}</p>
                    )}
                    {testImageUrl && (
                      <div style={{ marginTop: 8 }}>
                        <img
                          src={testImageUrl}
                          alt="测试生成结果"
                          style={{ maxWidth: "100%", maxHeight: 320, borderRadius: 8, border: "1px solid var(--svf-frame)" }}
                        />
                      </div>
                    )}
                  </div>

                  <h2 className="settings-section-title">流水线策略</h2>
                  <label className="settings-field">
                    <span>默认图片来源</span>
                    <select
                      value={imageSourceDefault}
                      onChange={(e) => setImageSourceDefault(e.target.value as ImageSourceMode)}
                    >
                      {(Object.keys(IMAGE_SOURCE_LABELS) as ImageSourceMode[]).map((key) => (
                        <option key={key} value={key}>
                          {IMAGE_SOURCE_LABELS[key]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="settings-row">
                    <label className="settings-field">
                      <span>图文子风格</span>
                      <select
                        value={imageTextPreset}
                        onChange={(e) =>
                          setImageTextPreset(e.target.value as "explainer" | "report" | "lecture")
                        }
                      >
                        <option value="explainer">科普讲解</option>
                        <option value="report">汇报</option>
                        <option value="lecture">课程讲座</option>
                      </select>
                    </label>
                    <label className="settings-field">
                      <span>漫画画风</span>
                      <select
                        value={comicPreset}
                        onChange={(e) =>
                          setComicPreset(e.target.value as "manga" | "webtoon" | "ink")
                        }
                      >
                        <option value="manga">日漫</option>
                        <option value="webtoon">条漫</option>
                        <option value="ink">水墨</option>
                      </select>
                    </label>
                  </div>
                  <label className="settings-field checkbox-row">
                    <input
                      type="checkbox"
                      checked={imageBatchPending}
                      onChange={(e) => setImageBatchPending(e.target.checked)}
                    />
                    <span>批量处理所有缺图文字资产</span>
                  </label>
                  <label className="settings-field checkbox-row">
                    <input
                      type="checkbox"
                      checked={imageSearchFallback}
                      onChange={(e) => setImageSearchFallback(e.target.checked)}
                    />
                    <span>生图失败时允许搜索配图回退</span>
                  </label>
                </>
              )}

              {tab === "video" && (
                <>
                  <p className="muted settings-intro">
                    AI 视频模式所用视频生成 API：Agnes Video 或火山方舟 SeedDance。
                  </p>
                  <label className="settings-field checkbox-row">
                    <input
                      type="checkbox"
                      checked={videoEnabled}
                      onChange={(e) => setVideoEnabled(e.target.checked)}
                    />
                    <span>启用 AI 视频生成</span>
                  </label>
                  <label className="settings-field">
                    <span>服务商</span>
                    <select
                      value={videoProvider}
                      onChange={(e) => {
                        const next = e.target.value;
                        const defaults = videoDefaultsForProvider(next, {
                          model: videoModel,
                          baseUrl: videoBaseUrl,
                        });
                        setVideoProvider(next);
                        setVideoModel(defaults.model);
                        setVideoBaseUrl(defaults.baseUrl);
                      }}
                    >
                      {(config.video.available_providers ?? [{ id: "agnes", label: "Agnes AI" }]).map(
                        (p) => (
                          <option key={p.id} value={p.id}>
                            {p.label}
                          </option>
                        ),
                      )}
                    </select>
                  </label>
                  <label className="settings-field">
                    <span>模型</span>
                    <input
                      type="text"
                      value={videoModel}
                      onChange={(e) => setVideoModel(e.target.value)}
                      placeholder={
                        videoProvider === "volcengine"
                          ? "doubao-seedance-2-0"
                          : "agnes-video-v2.0"
                      }
                    />
                  </label>
                  <label className="settings-field">
                    <span>API Key</span>
                    <input
                      type="password"
                      value={videoApiKey}
                      onChange={(e) => setVideoApiKey(e.target.value)}
                      placeholder={
                        config.video.has_api_key ? "已配置（留空不修改）" : "视频 API Key"
                      }
                      autoComplete="off"
                    />
                  </label>
                  <label className="settings-field">
                    <span>Base URL</span>
                    <input
                      type="text"
                      value={videoBaseUrl}
                      onChange={(e) => setVideoBaseUrl(e.target.value)}
                      placeholder={
                        videoProvider === "volcengine"
                          ? config.video.default_base_url_volcengine ?? ARK_IMAGE_BASE_URL
                          : config.video.base_url
                      }
                    />
                  </label>
                  <div className="settings-row">
                    <label className="settings-field">
                      <span>最大时长（秒）</span>
                      <input
                        type="number"
                        min={1}
                        max={60}
                        value={videoMaxDuration}
                        onChange={(e) => setVideoMaxDuration(Number(e.target.value))}
                      />
                    </label>
                    <label className="settings-field">
                      <span>分辨率</span>
                      <input
                        type="text"
                        value={videoResolution}
                        onChange={(e) => setVideoResolution(e.target.value)}
                      />
                    </label>
                  </div>
                </>
              )}

              {tab === "tts" && (
                <>
                  <p className="muted settings-intro">
                    多引擎配音：Edge TTS（默认免费）、OpenAI、Azure v2、SiliconFlow、Gemini、MiMo。
                  </p>
                  <label className="settings-field checkbox-row">
                    <input
                      type="checkbox"
                      checked={ttsEnabled}
                      onChange={(e) => setTtsEnabled(e.target.checked)}
                    />
                    <span>启用 TTS 合成</span>
                  </label>
                  <label className="settings-field">
                    <span>服务商</span>
                    <select
                      value={ttsProvider}
                      onChange={(e) => setTtsProvider(e.target.value)}
                    >
                      <option value="edge">edge（Edge TTS）</option>
                      <option value="openai">openai</option>
                      <option value="azure_v2">azure_v2</option>
                      <option value="siliconflow">siliconflow</option>
                      <option value="gemini">gemini</option>
                      <option value="mimo">mimo</option>
                    </select>
                  </label>
                  <label className="settings-field">
                    <span>默认语言</span>
                    <input
                      type="text"
                      value={ttsLanguage}
                      onChange={(e) => {
                        const next = e.target.value;
                        setTtsLanguage(next);
                        void syncUiFromTtsLanguage(next);
                      }}
                    />
                  </label>
                  <label className="settings-field">
                    <span>音色</span>
                    <select
                      value={ttsVoice}
                      onChange={(e) => setTtsVoice(e.target.value)}
                    >
                      {ttsVoices.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="settings-field">
                    <span>语速 ({ttsRate.toFixed(2)})</span>
                    <input
                      type="range"
                      min={0.5}
                      max={2}
                      step={0.05}
                      value={ttsRate}
                      onChange={(e) => setTtsRate(Number(e.target.value))}
                    />
                  </label>
                  <label className="settings-field">
                    <span>音量 ({ttsVolume.toFixed(2)})</span>
                    <input
                      type="range"
                      min={0.6}
                      max={1.5}
                      step={0.05}
                      value={ttsVolume}
                      onChange={(e) => setTtsVolume(Number(e.target.value))}
                    />
                  </label>
                  {ttsProvider === "openai" && (
                    <>
                      <label className="settings-field">
                        <span>模型</span>
                        <input
                          type="text"
                          value={ttsModel}
                          onChange={(e) => setTtsModel(e.target.value)}
                          placeholder="tts-1"
                        />
                      </label>
                      <label className="settings-field">
                        <span>OpenAI API Key</span>
                        <input
                          type="password"
                          value={ttsApiKey}
                          onChange={(e) => setTtsApiKey(e.target.value)}
                          placeholder={
                            config.tts.has_api_key ? "已配置（留空不修改）" : "TTS API Key"
                          }
                          autoComplete="off"
                        />
                      </label>
                      <label className="settings-field">
                        <span>Base URL</span>
                        <input
                          type="text"
                          value={ttsBaseUrl}
                          onChange={(e) => setTtsBaseUrl(e.target.value)}
                          placeholder={config.tts.base_url}
                        />
                      </label>
                    </>
                  )}
                  <label className="settings-field">
                    <span>Gemini API Key</span>
                    <input
                      type="password"
                      value={geminiApiKey}
                      onChange={(e) => setGeminiApiKey(e.target.value)}
                      placeholder={
                        config.tts.has_gemini_api_key ? "已配置（留空不修改）" : "可选"
                      }
                      autoComplete="off"
                    />
                  </label>
                  <label className="settings-field">
                    <span>MiMo API Key</span>
                    <input
                      type="password"
                      value={mimoApiKey}
                      onChange={(e) => setMimoApiKey(e.target.value)}
                      placeholder={
                        config.tts.has_mimo_api_key ? "已配置（留空不修改）" : "可选"
                      }
                      autoComplete="off"
                    />
                  </label>
                  <label className="settings-field">
                    <span>SiliconFlow API Key</span>
                    <input
                      type="password"
                      value={siliconflowApiKey}
                      onChange={(e) => setSiliconflowApiKey(e.target.value)}
                      placeholder={
                        config.tts.has_siliconflow_api_key ? "已配置（留空不修改）" : "可选"
                      }
                      autoComplete="off"
                    />
                  </label>
                  <label className="settings-field">
                    <span>Azure Speech Key</span>
                    <input
                      type="password"
                      value={azureSpeechKey}
                      onChange={(e) => setAzureSpeechKey(e.target.value)}
                      placeholder={
                        config.tts.has_azure_speech_key ? "已配置（留空不修改）" : "可选"
                      }
                      autoComplete="off"
                    />
                  </label>
                  <label className="settings-field">
                    <span>Azure Speech Region</span>
                    <input
                      type="text"
                      value={azureSpeechRegion}
                      onChange={(e) => setAzureSpeechRegion(e.target.value)}
                      placeholder={config.tts.azure_speech_region || "eastasia"}
                    />
                  </label>
                  <div className="settings-field">
                    <span>试听</span>
                    <textarea
                      rows={2}
                      value={ttsPreviewText}
                      onChange={(e) => setTtsPreviewText(e.target.value)}
                    />
                    <button
                      type="button"
                      disabled={ttsPreviewLoading || !ttsPreviewText.trim()}
                      onClick={async () => {
                        setTtsPreviewLoading(true);
                        setTtsPreviewUrl(null);
                        try {
                          const r = await fetch("/api/ai/tts/preview", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                              text: ttsPreviewText.slice(0, 100),
                              provider: ttsProvider,
                              default_language: ttsLanguage,
                              voice_name: ttsVoice || undefined,
                              voice_rate: ttsRate,
                              voice_volume: ttsVolume,
                              model: ttsModel || undefined,
                              base_url: ttsBaseUrl || undefined,
                              api_key: ttsApiKey.trim() || undefined,
                              gemini_api_key: geminiApiKey.trim() || undefined,
                              mimo_api_key: mimoApiKey.trim() || undefined,
                              siliconflow_api_key: siliconflowApiKey.trim() || undefined,
                              azure_speech_key: azureSpeechKey.trim() || undefined,
                              azure_speech_region: azureSpeechRegion.trim() || undefined,
                            }),
                          });
                          if (!r.ok) {
                            let detail = "试听失败";
                            try {
                              const err = await r.json();
                              if (typeof err.detail === "string") detail = err.detail;
                              else if (Array.isArray(err.detail)) {
                                detail = err.detail.map((d: { msg?: string }) => d.msg).join("; ");
                              }
                            } catch {
                              /* ignore */
                            }
                            throw new Error(detail);
                          }
                          const data = await r.json();
                          setTtsPreviewUrl(String(data.url ?? ""));
                        } catch (e) {
                          setSaveError((e as Error).message || "试听失败");
                        } finally {
                          setTtsPreviewLoading(false);
                        }
                      }}
                    >
                      {ttsPreviewLoading
                        ? t("ai.testTtsGenerating", { ns: "settings" })
                        : t("ai.testTts", { ns: "settings" })}
                    </button>
                    {ttsPreviewUrl ? (
                      <audio controls src={ttsPreviewUrl} style={{ width: "100%", marginTop: 8 }} />
                    ) : null}
                  </div>
                </>
              )}

              {tab === "export" && (
                <>
                  <p className="field-hint">
                    故事书成片通过 FFmpeg 导出。默认使用 pip 安装的内置 FFmpeg；也可填写自定义路径。
                  </p>
                  <label className="settings-field settings-checkbox">
                    <input
                      type="checkbox"
                      checked={exportEnabled}
                      onChange={(e) => setExportEnabled(e.target.checked)}
                    />
                    <span>启用 FFmpeg 成片导出</span>
                  </label>
                  {config?.export.ffmpeg_available === false && (
                    <p className="board-error">未检测到 FFmpeg，请安装或设置路径。</p>
                  )}
                  <label className="settings-field">
                    <span>FFmpeg 路径（可选）</span>
                    <input
                      type="text"
                      value={exportFfmpegPath}
                      onChange={(e) => setExportFfmpegPath(e.target.value)}
                      placeholder="留空使用内置或 PATH"
                    />
                  </label>
                  <label className="settings-field">
                    <span>帧率 FPS</span>
                    <input
                      type="number"
                      min={24}
                      max={60}
                      value={exportFps}
                      onChange={(e) => setExportFps(Number(e.target.value))}
                    />
                  </label>
                  <label className="settings-field">
                    <span>宽度</span>
                    <input
                      type="number"
                      min={640}
                      value={exportWidth}
                      onChange={(e) => setExportWidth(Number(e.target.value))}
                    />
                  </label>
                  <label className="settings-field">
                    <span>高度</span>
                    <input
                      type="number"
                      min={360}
                      value={exportHeight}
                      onChange={(e) => setExportHeight(Number(e.target.value))}
                    />
                  </label>
                  <label className="settings-field">
                    <span>CRF 质量（18–28，越小越清晰）</span>
                    <input
                      type="number"
                      min={18}
                      max={28}
                      value={exportCrf}
                      onChange={(e) => setExportCrf(Number(e.target.value))}
                    />
                  </label>
                </>
              )}

              {tab === "embedding" && (
                <>
                  <p className="field-hint">
                    用于跨剧本人物/场景/道具的向量检索复用。未配置 API Key 时，系统会按规范化名称精确匹配已有共享资产。
                  </p>
                  <label className="settings-field settings-checkbox">
                    <input
                      type="checkbox"
                      checked={embeddingEnabled}
                      onChange={(e) => setEmbeddingEnabled(e.target.checked)}
                    />
                    <span>启用 Embedding / RAG 复用</span>
                  </label>
                  {config?.embedding && (
                    <p className="field-hint">
                      状态：{config.embedding.active ? "已就绪（向量检索）" : "未配置 Key（将回退名称匹配）"}
                      {config.embedding.has_api_key ? " · 已保存 API Key" : ""}
                    </p>
                  )}
                  <label className="settings-field">
                    <span>Base URL</span>
                    <input
                      type="text"
                      value={embeddingBaseUrl}
                      onChange={(e) => setEmbeddingBaseUrl(e.target.value)}
                      placeholder="https://api.openai.com/v1"
                    />
                  </label>
                  <label className="settings-field">
                    <span>Model</span>
                    <input
                      type="text"
                      value={embeddingModel}
                      onChange={(e) => setEmbeddingModel(e.target.value)}
                      placeholder="text-embedding-3-small"
                    />
                  </label>
                  <label className="settings-field">
                    <span>API Key{config?.embedding?.has_api_key ? "（已配置，留空不修改）" : ""}</span>
                    <input
                      type="password"
                      value={embeddingApiKey}
                      onChange={(e) => setEmbeddingApiKey(e.target.value)}
                      placeholder="sk-…"
                      autoComplete="off"
                    />
                  </label>
                </>
              )}

              <p className="field-hint">
                API Key 仅保存在服务端内存，重启后端后需重新填写或通过环境变量配置。
              </p>

              {saveMsg && <div className="settings-alert success">{saveMsg}</div>}
              {saveError && <div className="settings-alert error">{saveError}</div>}

              <div className="settings-actions">
                <button type="submit" disabled={saving}>
                  {saving
                    ? t("actions.saving", { ns: "common" })
                    : t("ai.saveConfig", { ns: "settings" })}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={saving}
                  onClick={handleSaveAndBack}
                >
                  {saving
                    ? t("actions.saving", { ns: "common" })
                    : t("ai.saveAndBack", { ns: "settings" })}
                </button>
              </div>
            </form>
          </>
        )}
    </AppShell>
  );
}
