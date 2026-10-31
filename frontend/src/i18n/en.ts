// English singular forms for keys that take a {count}; the key itself is the plural.
import type { Dictionary } from ".";

const en: Dictionary = {
  "Stock updated: {count} changes saved.": { one: "Stock updated: {count} change saved.", other: "Stock updated: {count} changes saved." },
  "Confirm {count} changes": { one: "Confirm {count} change", other: "Confirm {count} changes" },
  "{count} days late": { one: "{count} day late", other: "{count} days late" },
  "Leaves in {count} days": { one: "Leaves in {count} day", other: "Leaves in {count} days" },
  "In {count} days": { one: "In {count} day", other: "In {count} days" },
  "{count} expenses match. Valid total: {amount}.": { one: "{count} expense matches. Valid total: {amount}.", other: "{count} expenses match. Valid total: {amount}." },
  "{done} of {count} tasks done ({pct})": { one: "{done} of {count} task done ({pct})", other: "{done} of {count} tasks done ({pct})" },
  "{count} overdue tasks": { one: "{count} overdue task", other: "{count} overdue tasks" },
  "deleted a milestone ({count} tasks kept, without a milestone)": { one: "deleted a milestone ({count} task kept, without a milestone)", other: "deleted a milestone ({count} tasks kept, without a milestone)" },
  "{count} active projects": { one: "{count} active project", other: "{count} active projects" },
  "{count} projects are over budget": { one: "{count} project is over budget", other: "{count} projects are over budget" },
  "{count} overdue tasks, listed in the agenda": { one: "{count} overdue task, listed in the agenda", other: "{count} overdue tasks, listed in the agenda" },
  "{count} items have no unit cost, so they aren't in the stock value.": { one: "{count} item has no unit cost, so it isn't in the stock value.", other: "{count} items have no unit cost, so they aren't in the stock value." },
  "{count} items counted, no differences.": { one: "{count} item counted, no differences.", other: "{count} items counted, no differences." },
  "{count} items counted, {changed} different from the records.": { one: "{count} item counted, {changed} different from the records.", other: "{count} items counted, {changed} different from the records." },
  "Based on {count} valid expenses; {excluded} voided or refunded not counted.": { one: "Based on {count} valid expense; {excluded} voided or refunded not counted.", other: "Based on {count} valid expenses; {excluded} voided or refunded not counted." },
  "Based on {count} valid expenses.": { one: "Based on {count} valid expense.", other: "Based on {count} valid expenses." },
  "{count} tasks, {pct} complete.": { one: "{count} task, {pct} complete.", other: "{count} tasks, {pct} complete." },
  "{count} nights": { one: "{count} night", other: "{count} nights" },
};

export default en;
