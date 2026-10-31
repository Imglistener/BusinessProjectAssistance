import { useEffect, useState } from "react";

const KEY = "bpa.motion";
const CLASS = "reduce-motion";

/**
 * The app animates by default. People who prefer less movement switch it off in the user menu
 * ("Reduce motion"); the choice is a class on <html> (set before first paint in index.html), so CSS
 * transitions and the Motion library follow the same setting.
 *
 * The operating system's "reduce motion" isn't used on its own: Windows reports it whenever
 * "Animation effects" is off, which many setups do for speed rather than by choice.
 */
export function reduceMotion(): boolean {
  return document.documentElement.classList.contains(CLASS);
}

export function setReduceMotion(on: boolean): void {
  document.documentElement.classList.toggle(CLASS, on);
  try {
    localStorage.setItem(KEY, on ? "reduce" : "full");
  } catch {
    /* storage unavailable: lasts until reload */
  }
}

/** Follows the "Reduce motion" setting as it changes. */
export function useReduceMotion(): boolean {
  const [on, setOn] = useState(reduceMotion);
  useEffect(() => {
    const html = document.documentElement;
    const observer = new MutationObserver(() => setOn(html.classList.contains(CLASS)));
    observer.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return on;
}
