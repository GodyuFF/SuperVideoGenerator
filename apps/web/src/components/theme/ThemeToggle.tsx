/**

 * 主应用明暗主题切换按钮。

 */



import { useEffect, useState } from "react";

import { useTheme } from "next-themes";

import { useTranslation } from "react-i18next";



/** 在顶栏切换 light / dark / system 主题。 */

export function ThemeToggle() {

  const { t } = useTranslation("common");

  const { theme, setTheme, resolvedTheme } = useTheme();

  const [mounted, setMounted] = useState(false);



  useEffect(() => {

    setMounted(true);

  }, []);



  if (!mounted) {

    return (

      <button type="button" className="btn-secondary btn-sm svf-theme-toggle" aria-hidden>

        ···

      </button>

    );

  }



  const isDark = resolvedTheme === "dark";



  /** 在 dark → light → system 间循环。 */

  const handleToggle = () => {

    if (theme === "dark") setTheme("light");

    else if (theme === "light") setTheme("system");

    else setTheme("dark");

  };



  const label =

    theme === "system"

      ? t("theme.followSystem")

      : isDark

        ? t("theme.switchToLight")

        : t("theme.switchToDark");



  const shortLabel =

    theme === "system" ? t("theme.system") : isDark ? t("theme.dark") : t("theme.light");



  return (

    <button

      type="button"

      className="btn-secondary btn-sm svf-theme-toggle"

      onClick={handleToggle}

      title={label}

      aria-label={label}

    >

      <span className="svf-theme-toggle-icon" aria-hidden>

        {theme === "system" ? "◐" : isDark ? "☀" : "☾"}

      </span>

      <span className="svf-theme-toggle-label">{shortLabel}</span>

    </button>

  );

}

