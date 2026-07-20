/** SuperVideoGenerator 展示站中英字典与切换。 */
(function () {
  const STORAGE_KEY = "svg-site-lang";

  const STRINGS = {
    zh: {
      brand: "SuperVideoGenerator",
      navPipeline: "流水线",
      navFilm: "成片",
      navGet: "下载",
      navContact: "联系",
      langZh: "中",
      langEn: "EN",
      heroTitle: "SuperVideoGenerator",
      heroClaim: "从剧本到成片，一条对话流水线",
      ctaWatch: "观看演示",
      ctaDownload: "下载安装包",
      ctaGithub: "GitHub",
      pipelineEyebrow: "PIPELINE",
      stepDialogue: "对话",
      stepBoard: "分镜与资产",
      stepEdit: "剪辑",
      stepFinal: "成片",
      stepDialogueBody: "用自然语言描述创意，主 Agent 编排剧本与计划。",
      stepBoardBody: "分镜、人物与场景资产在看板中可见可改。",
      stepEditBody: "Edit Studio 多轨时间轴精修字幕、画面与旁白。",
      stepFinalBody: "导出故事书成片——本页演示：女娲补天。",
      placeholderChat: "对话录屏即将补上",
      placeholderBoard: "看板 / 分镜截图即将补上",
      placeholderAssets: "资产详情截图即将补上",
      capsEyebrow: "CAPABILITIES",
      capChatTitle: "对话 + 看板",
      capChatBody: "Plan 可见可审，再执行；不是黑盒一键生成。",
      capAssetsTitle: "资产复用",
      capAssetsBody: "人物、道具、场景跨剧本共享，系列创作少重复劳动。",
      capEditTitle: "Edit Studio",
      capEditBody: "镜内多轨剪辑，可写回分镜，成片前仍可改。",
      getEyebrow: "GET STARTED",
      getDownload: "从 GitHub Releases 下载桌面安装包",
      getClone: "克隆仓库本地运行",
      getDocs: "阅读快速开始",
      getCloneCmd: "git clone https://github.com/GodyuFF/SuperVideoGenerator.git",
      contactEyebrow: "CONTACT",
      contactTitle: "加入交流",
      contactLead: "问题反馈、体验交流，欢迎进群或发邮件。",
      contactQqLabel: "QQ 群",
      contactQqHint: "群号可直接搜索加入",
      contactEmailLabel: "邮箱",
      contactWechatLabel: "微信群",
      contactWechatCaption: "微信扫码加入交流群（二维码会过期，失效请用 QQ / 邮箱联系）",
      contactWechatAlt: "SuperVideoGenerator 微信交流群二维码",
      footerLicense: "MIT License",
      footerNotices: "第三方声明",
      editAlt: "女娲补天项目的多轨剪辑时间轴",
      videoTitle: "女娲补天 · 故事书成片演示",
    },
    en: {
      brand: "SuperVideoGenerator",
      navPipeline: "Pipeline",
      navFilm: "Film",
      navGet: "Download",
      navContact: "Contact",
      langZh: "中",
      langEn: "EN",
      heroTitle: "SuperVideoGenerator",
      heroClaim: "From script to finished film — one conversation pipeline",
      ctaWatch: "Watch demo",
      ctaDownload: "Download",
      ctaGithub: "GitHub",
      pipelineEyebrow: "PIPELINE",
      stepDialogue: "Dialogue",
      stepBoard: "Board & assets",
      stepEdit: "Edit Studio",
      stepFinal: "Final cut",
      stepDialogueBody: "Describe the idea in natural language; the master agent plans the script.",
      stepBoardBody: "Shots, characters, and scenes stay visible and editable on the board.",
      stepEditBody: "Refine subtitles, picture, and narration on a multi-track timeline.",
      stepFinalBody: "Export the storybook film — demo: Nüwa Repairs the Heavens.",
      placeholderChat: "Conversation recording coming soon",
      placeholderBoard: "Board / storyboard stills coming soon",
      placeholderAssets: "Asset detail stills coming soon",
      capsEyebrow: "CAPABILITIES",
      capChatTitle: "Chat + board",
      capChatBody: "Review the plan before it runs — not a black-box one-click.",
      capAssetsTitle: "Reusable assets",
      capAssetsBody: "Share characters, props, and scenes across scripts.",
      capEditTitle: "Edit Studio",
      capEditBody: "Multi-track polish that can write back to shots before export.",
      getEyebrow: "GET STARTED",
      getDownload: "Download the desktop installer from GitHub Releases",
      getClone: "Clone the repo to run locally",
      getDocs: "Read Getting Started",
      getCloneCmd: "git clone https://github.com/GodyuFF/SuperVideoGenerator.git",
      contactEyebrow: "CONTACT",
      contactTitle: "Get in touch",
      contactLead: "Feedback and discussion — join the group or email us.",
      contactQqLabel: "QQ group",
      contactQqHint: "Search the group ID in QQ to join",
      contactEmailLabel: "Email",
      contactWechatLabel: "WeChat group",
      contactWechatCaption: "Scan to join (QR codes expire — use QQ or email if it fails)",
      contactWechatAlt: "SuperVideoGenerator WeChat group QR code",
      footerLicense: "MIT License",
      footerNotices: "Third-party notices",
      editAlt: "Multi-track edit timeline for the Nüwa storybook project",
      videoTitle: "Nüwa Repairs the Heavens — storybook demo",
    },
  };

  function getLang() {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "en" || v === "zh" ? v : "zh";
  }

  function applyLang(lang) {
    const pack = STRINGS[lang] || STRINGS.zh;
    document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
    localStorage.setItem(STORAGE_KEY, lang);
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (key && pack[key] != null) el.textContent = pack[key];
    });
    document.querySelectorAll("[data-i18n-attr]").forEach((el) => {
      const spec = el.getAttribute("data-i18n-attr");
      if (!spec) return;
      const [attr, key] = spec.split(":");
      if (attr && key && pack[key] != null) el.setAttribute(attr, pack[key]);
    });
    document.querySelectorAll("[data-lang-set]").forEach((btn) => {
      const active = btn.getAttribute("data-lang-set") === lang;
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  window.SvgSiteI18n = { STRINGS, getLang, applyLang };

  document.addEventListener("DOMContentLoaded", () => {
    applyLang(getLang());
    document.querySelectorAll("[data-lang-set]").forEach((btn) => {
      btn.addEventListener("click", () => applyLang(btn.getAttribute("data-lang-set")));
    });
  });
})();
