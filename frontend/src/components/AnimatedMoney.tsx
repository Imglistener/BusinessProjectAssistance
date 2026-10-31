import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";
import { formatMoney } from "../lib/format";

/** A money figure that counts up from zero once, quickly. The final text is always the exact formatted amount. */
export function AnimatedMoney({ amount, currency, className }: { amount: string; currency: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduce = useReducedMotion();
  const final = formatMoney(amount, currency);

  useEffect(() => {
    const el = ref.current;
    const target = Number(amount);
    if (!el || reduce || !Number.isFinite(target) || target === 0) return;
    const controls = animate(0, target, {
      duration: 0.9,
      ease: [0.2, 0.7, 0.2, 1],
      onUpdate: (v) => {
        el.textContent = formatMoney(v.toFixed(2), currency);
      },
      onComplete: () => {
        el.textContent = final;
      },
    });
    return () => controls.stop();
  }, [amount, currency, final, reduce]);

  return (
    <span ref={ref} className={className}>
      {final}
    </span>
  );
}
