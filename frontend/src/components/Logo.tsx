import { cn } from "@/lib/utils";

/** The eight-point star (two squares) with its saffron centre: the product's mark. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false" className={cn("size-7 shrink-0", className)}>
      <g fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinejoin="round">
        <rect x="11" y="11" width="26" height="26" rx="2" />
        <rect x="11" y="11" width="26" height="26" rx="2" transform="rotate(45 24 24)" />
      </g>
      <rect x="20.5" y="20.5" width="7" height="7" rx="1" transform="rotate(45 24 24)" className="fill-highlight" />
    </svg>
  );
}

/** Mark and name. `compact` puts the name on one line (headers); otherwise two lines (sidebar). */
export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5 font-semibold tracking-tight", className)} dir="ltr">
      <LogoMark className="text-primary" />
      {compact ? (
        <span className="text-[15px]">Business Project Assistance</span>
      ) : (
        <span className="text-[13px] leading-tight">
          Business Project
          <br />
          Assistance
        </span>
      )}
    </span>
  );
}
