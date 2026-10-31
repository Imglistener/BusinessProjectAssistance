import { Fragment, type ReactNode } from "react";
import { t } from ".";

/**
 * t() for sentences that contain elements (links, bold text): the placeholders are React nodes.
 *
 *   tx("Create your organization on the {link} first.", { link: <Link to="/app">{t("dashboard")}</Link> })
 */
export function tx(key: string, vars: Record<string, ReactNode>): ReactNode {
  const marked: Record<string, string> = {};
  for (const k of Object.keys(vars)) marked[k] = `\u0000${k}\u0000`;
  const parts = t(key, marked).split("\u0000");
  return parts.map((part, i) => <Fragment key={i}>{i % 2 ? vars[part] : part}</Fragment>);
}
