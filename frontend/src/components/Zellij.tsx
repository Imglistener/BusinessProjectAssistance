import { useId } from "react";

/** Repeating eight-point star tile (zellij-style) used as the product's one decorative motif. */
export function ZellijField({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg className={className} aria-hidden="true" focusable="false" width="100%" height="100%">
      <defs>
        <pattern id={id} width="80" height="80" patternUnits="userSpaceOnUse">
          <rect x="18" y="18" width="44" height="44" fill="none" stroke="currentColor" strokeWidth="1" />
          <rect
            x="18"
            y="18"
            width="44"
            height="44"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            transform="rotate(45 40 40)"
          />
          <rect x="36" y="36" width="8" height="8" className="zellij-dot" transform="rotate(45 40 40)" />
          <circle cx="0" cy="0" r="2.5" className="zellij-dot" />
          <circle cx="80" cy="0" r="2.5" className="zellij-dot" />
          <circle cx="0" cy="80" r="2.5" className="zellij-dot" />
          <circle cx="80" cy="80" r="2.5" className="zellij-dot" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  );
}

/** The star as a single mark; `draw` animates the outline once (splash only). */
export function StarMark({ size = 28, draw = false }: { size?: number; draw?: boolean }) {
  return (
    <svg
      className={draw ? "star-mark star-mark--draw" : "star-mark"}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      aria-hidden="true"
      focusable="false"
    >
      <rect pathLength={1} x="22" y="22" width="56" height="56" />
      <rect pathLength={1} x="22" y="22" width="56" height="56" transform="rotate(45 50 50)" />
      <rect className="star-mark__dot" x="44" y="44" width="12" height="12" transform="rotate(45 50 50)" />
    </svg>
  );
}

export function Wordmark({ light = false }: { light?: boolean }) {
  return (
    <span className={light ? "wordmark wordmark--light" : "wordmark"}>
      <StarMark size={30} />
      <span className="wordmark__text">
        Business Project
        <br />
        Assistance
      </span>
    </span>
  );
}
