import {
  AbsoluteFill,
  interpolate,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const FEATURES = [
  { title: "ReAct 主编排", desc: "超级视频大师自动规划与委派" },
  { title: "多 Agent 协作", desc: "剧本 · 分镜 · 配音 · 剪辑" },
  { title: "A2UI 确认", desc: "关键步骤可视化交互确认" },
];

const TitleScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });
  const subtitleOpacity = interpolate(frame, [20, 45], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const glow = interpolate(frame, [0, 60, 90], [0.3, 0.8, 0.5]);

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(circle at 50% 40%, rgba(99,102,241,${glow}) 0%, #0f172a 55%)`,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div style={{ textAlign: "center", transform: `scale(${titleSpring})` }}>
        <div
          style={{
            fontSize: 88,
            fontWeight: 800,
            fontFamily: "system-ui, sans-serif",
            background: "linear-gradient(135deg, #a5b4fc, #6366f1, #818cf8)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            letterSpacing: -2,
          }}
        >
          SuperVideoGenerator
        </div>
        <p
          style={{
            marginTop: 24,
            fontSize: 32,
            color: "#94a3b8",
            fontFamily: "system-ui, sans-serif",
            opacity: subtitleOpacity,
          }}
        >
          AI 多 Agent 视频生成平台
        </p>
      </div>
    </AbsoluteFill>
  );
};

const FeatureCard: React.FC<{
  title: string;
  desc: string;
  index: number;
}> = ({ title, desc, index }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({
    frame: frame - index * 12,
    fps,
    config: { damping: 16, stiffness: 100 },
  });
  const translateY = interpolate(enter, [0, 1], [80, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  return (
    <div
      style={{
        flex: 1,
        padding: "36px 32px",
        borderRadius: 20,
        background: "rgba(255,255,255,0.06)",
        border: "1px solid rgba(148,163,184,0.2)",
        backdropFilter: "blur(8px)",
        transform: `translateY(${translateY}px)`,
        opacity,
      }}
    >
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: 12,
          background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 22,
          fontWeight: 700,
          color: "white",
          fontFamily: "system-ui, sans-serif",
          marginBottom: 20,
        }}
      >
        {index + 1}
      </div>
      <h2
        style={{
          margin: 0,
          fontSize: 28,
          color: "white",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        {title}
      </h2>
      <p
        style={{
          marginTop: 12,
          fontSize: 18,
          color: "#94a3b8",
          lineHeight: 1.5,
          fontFamily: "system-ui, sans-serif",
        }}
      >
        {desc}
      </p>
    </div>
  );
};

const FeaturesScene: React.FC = () => {
  const frame = useCurrentFrame();
  const labelOpacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: "#0f172a",
        padding: 80,
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <p
        style={{
          textAlign: "center",
          color: "#6366f1",
          fontSize: 20,
          fontWeight: 600,
          letterSpacing: 4,
          textTransform: "uppercase",
          fontFamily: "system-ui, sans-serif",
          opacity: labelOpacity,
          marginBottom: 48,
        }}
      >
        核心能力
      </p>
      <div style={{ display: "flex", gap: 32 }}>
        {FEATURES.map((f, i) => (
          <FeatureCard key={f.title} {...f} index={i} />
        ))}
      </div>
    </AbsoluteFill>
  );
};

const OutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 80 },
  });
  const pulse = interpolate(frame, [0, 30, 60], [1, 1.05, 1]);

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(160deg, #1e1b4b 0%, #0f172a 100%)",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          textAlign: "center",
          transform: `scale(${scale * pulse})`,
        }}
      >
        <div
          style={{
            fontSize: 56,
            fontWeight: 700,
            color: "white",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          开始创作你的 AI 视频
        </div>
        <div
          style={{
            marginTop: 20,
            fontSize: 24,
            color: "#64748b",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          Remotion Demo · 2026
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const MyComposition: React.FC = () => {
  return (
    <AbsoluteFill>
      <Sequence from={0} durationInFrames={90}>
        <TitleScene />
      </Sequence>
      <Sequence from={90} durationInFrames={120}>
        <FeaturesScene />
      </Sequence>
      <Sequence from={210} durationInFrames={90}>
        <OutroScene />
      </Sequence>
    </AbsoluteFill>
  );
};
