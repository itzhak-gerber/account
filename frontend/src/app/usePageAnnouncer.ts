import { useEffect, useRef } from "react";
import { useLocation } from "react-router";

/**
 * After navigation: names the browser tab after the page's heading (WCAG 2.4.2) and moves
 * keyboard / screen-reader focus to that heading, so the new page is announced (WCAG 2.4.3).
 * Pages load their data asynchronously, so the heading is awaited briefly.
 */
export function usePageAnnouncer(appName: string, main: React.RefObject<HTMLElement | null>) {
  const { pathname } = useLocation();
  const first = useRef(true);

  useEffect(() => {
    const moveFocus = !first.current;
    first.current = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const apply = () => {
      const heading = main.current?.querySelector<HTMLElement>("h1");
      if (!heading) {
        if (++tries < 40) timer = setTimeout(apply, 50);
        else document.title = appName;
        return;
      }
      const text = heading.textContent?.trim();
      document.title = text && text !== appName ? `${text} · ${appName}` : appName;
      if (moveFocus) {
        heading.tabIndex = -1;
        heading.style.outline = "none";
        heading.focus();
      }
    };
    apply();
    return () => clearTimeout(timer);
  }, [pathname, appName, main]);
}
