import { History, Maximize2, Minimize2, Plus, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useLocation } from "react-router";
import { api } from "../api/client";
import type { ConversationSummary, Organization } from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { ActionProposal } from "../components/ActionProposal";
import { FormError } from "../components/AuthLayout";
import { ProjectProposal } from "../components/ProjectProposal";
import { StockProposal } from "../components/StockProposal";
import { getLocale, t } from "../i18n";
import { tx } from "../i18n/rich";
import { errorMessage } from "../lib/errors";
import { ModelPicker } from "./ModelPicker";
import { useAssistant, type ChatMessage } from "./AssistantContext";

/** What each tool's result means to a person reading the answer. */
const TOOL_LABEL: Record<string, string> = {
  list_projects: t("Project list"),
  get_project_summary: t("Project summary"),
  calculate_budget_metrics: t("Budget figures"),
  get_expense_breakdown: t("Expense breakdown"),
  list_overdue_tasks: t("Overdue tasks"),
  estimate_spend_rate: t("Spend-rate estimate"),
  draft_project_update: t("Project facts for the draft"),
  get_inventory_status: t("Inventory"),
  find_inventory_items: t("Stock items"),
  list_warehouses: t("Warehouses"),
  propose_stock_changes: t("Stock changes draft"),
  calculate: t("Calculator"),
  vat: t("VAT calculation"),
  budget_what_if: t("Budget what-if"),
  estimate_trip_fuel_cost: t("Trip fuel estimate"),
  estimate_fuel_cost: t("Fuel estimate"),
  propose_project: t("Project draft"),
  find_tasks: t("Tasks"),
  find_expenses: t("Expenses"),
  list_members: t("Members"),
  propose_actions: t("Changes draft"),
};

const GENERAL_PROMPTS = [
  t("A customer wants a 3-day team retreat in Ifrane for 25 people next March, about 80000 MAD. Set it up as a project."),
  t("Which projects need attention right now?"),
  t("Are any projects over budget?"),
  t("Which projects have overdue tasks?"),
  t("What would it cost in fuel to drive a van from Casablanca to Marrakech and back?"),
  t("What's the VAT on 12,500 MAD, and the total including VAT?"),
  t("What's running low in stock?"),
  t("We received 20 boxes of printer paper."),
];

const PROJECT_PROMPTS = [
  t("How is the budget looking?"),
  t("What are we spending the most on?"),
  t("At the current spend rate, how long will the budget last?"),
  t("Draft a short status update I can share."),
  t("If we spend 5,000 more, how much budget is left?"),
  t("How much fuel will our planned trips cost?"),
];

/** Pages where the side panel is offered: signed-in screens, not the printable report. */
export function panelAllowed(pathname: string): boolean {
  return pathname.startsWith("/app") && !pathname.endsWith("/report");
}

/**
 * The assistant, docked beside every signed-in page. It is mounted once above the routes and only hidden when
 * closed, so a conversation and its draft cards (with what was typed or confirmed in them) survive navigation.
 */
export function AssistantPanel() {
  const { user } = useAuth();
  const { org } = useOrg();
  const { pathname } = useLocation();
  const a = useAssistant();
  const shown = Boolean(user) && a.open && panelAllowed(pathname);

  // The page leaves room for the panel on wide screens (--assistant-push in index.css).
  useEffect(() => {
    const root = document.documentElement;
    if (shown) root.dataset.assistant = a.wide ? "wide" : "open";
    else delete root.dataset.assistant;
    return () => {
      delete root.dataset.assistant;
    };
  }, [shown, a.wide]);

  if (!user) return null;

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    // Menus and dialogs opened from the panel are portals: their Escape bubbles here but is theirs.
    if (e.key === "Escape" && e.currentTarget.contains(e.target as Node)) a.setOpen(false);
  };

  return (
    <aside
      className="assistant-panel legacy"
      data-wide={a.wide || undefined}
      hidden={!shown}
      aria-label={t("Assistant")}
      onKeyDown={onKeyDown}
    >
      <header className="assistant-panel__head">
        <Sparkles className="assistant-panel__mark" aria-hidden />
        <h2>{a.view === "history" ? t("Conversations") : t("Assistant")}</h2>
        <div className="assistant-panel__tools">
          <IconButton
            label={a.view === "history" ? t("Back to the conversation") : t("Conversation history")}
            pressed={a.view === "history"}
            onClick={() => a.setView(a.view === "history" ? "chat" : "history")}
          >
            <History />
          </IconButton>
          <IconButton label={t("New conversation")} onClick={a.newConversation} disabled={a.busy}>
            <Plus />
          </IconButton>
          <IconButton
            label={a.wide ? t("Narrow the panel") : t("Widen the panel")}
            onClick={() => a.setWide(!a.wide)}
            className="assistant-panel__widen"
          >
            {a.wide ? <Minimize2 /> : <Maximize2 />}
          </IconButton>
          <IconButton label={t("Close the assistant")} onClick={() => a.setOpen(false)}>
            <X />
          </IconButton>
        </div>
      </header>

      {!org ? (
        <p className="muted assistant-panel__body">
          {tx("Create your organization on the {dashboard} first.", {
            dashboard: <Link to="/app">{t("dashboard")}</Link>,
          })}
        </p>
      ) : (
        <>
          {/* Both stay mounted so draft cards keep their state while the history is open. */}
          <div className="assistant-panel__view" hidden={a.view !== "chat"}>
            <Chat org={org} visible={shown && a.view === "chat"} />
          </div>
          {a.view === "history" && <HistoryList org={org} />}
        </>
      )}
    </aside>
  );
}

function IconButton({
  label,
  onClick,
  children,
  disabled,
  pressed,
  className,
}: {
  label: string;
  onClick(): void;
  children: React.ReactNode;
  disabled?: boolean;
  pressed?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={`assistant-panel__icon ${className ?? ""}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={pressed}
      title={label}
    >
      {children}
    </button>
  );
}

function Chat({ org, visible }: { org: Organization; visible: boolean }) {
  const a = useAssistant();
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const log = logRef.current;
    if (log && visible) log.scrollTop = a.messages.length > 0 ? log.scrollHeight : 0; // suggestions start at the top
  }, [a.messages, a.busy, visible]);

  useEffect(() => {
    if (visible) inputRef.current?.focus();
  }, [visible]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void a.send(a.input);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void a.send(a.input);
    }
  };

  const prompts = a.projectId ? PROJECT_PROMPTS : GENERAL_PROMPTS;
  // The conversation's project may be archived or gone from the list; keep it selectable while it's selected.
  const knownProject = !a.projectId || a.projects.some((p) => String(p.id) === a.projectId);

  return (
    <section className="chat" aria-label={t("Conversation")}>
      <div className="field chat__project">
        <label htmlFor="chat-project">{t("About")}</label>
        <div className="field__control">
          <select
            id="chat-project"
            value={a.projectId}
            onChange={(e) => a.setProjectId(e.target.value)}
            disabled={a.busy}
          >
            <option value="">{t("All projects")}</option>
            {!knownProject && <option value={a.projectId}>{t("Project #{id}", { id: a.projectId })}</option>}
            {a.projects.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="chat__log" ref={logRef} aria-live="polite">
        {a.loading && <p className="muted">{t("Loading…")}</p>}
        {!a.loading && a.messages.length === 0 && (
          <div className="chat__empty">
            <p className="muted">{t("Try one of these:")}</p>
            <ul className="chips">
              {prompts.map((p) => (
                <li key={p}>
                  <button type="button" className="chip" onClick={() => void a.send(p)} disabled={a.busy}>
                    {p}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {a.messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="bubble bubble--user">
              <span className="visually-hidden">{t("You:")} </span>
              {m.content}
            </div>
          ) : (
            <AssistantMessage key={i} message={m} org={org} />
          ),
        )}

        {a.busy && (
          <p className="chat__thinking" role="status">
            {t("Looking at your data…")}
          </p>
        )}
      </div>

      <FormError message={a.error} />

      <form className="composer" onSubmit={onSubmit}>
        <label htmlFor="chat-input" className="visually-hidden">
          {t("Your question")}
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          rows={2}
          maxLength={2000}
          placeholder={a.projectId ? t("Ask about this project…") : t("Ask about your projects…")}
          value={a.input}
          onChange={(e) => a.setInput(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="composer__bar">
          <ModelPicker />
          <button type="submit" className="btn btn--primary" disabled={a.busy || a.loading || !a.input.trim()}>
            {t("Ask")}
          </button>
        </div>
      </form>

      <p className="chat__disclosure">
        {a.providers.length > 0
          ? t("Your question and the project figures needed to answer it are sent to an external AI provider ({providers}). Answers are AI-generated and can be wrong: check important figures on the project page.", {
              providers: a.providers.map((p) => p.label).join(t(", ")),
            })
          : t("Your question and the project figures needed to answer it are sent to an external AI provider. Answers are AI-generated and can be wrong: check important figures on the project page.")}
      </p>
    </section>
  );
}

function AssistantMessage({ message, org }: { message: ChatMessage; org: Organization }) {
  const { providers } = useAssistant();
  const label = (id: string) => providers.find((p) => p.id === id)?.label ?? id;
  const [copied, setCopied] = useState(false);
  const sources = [...new Set((message.trace ?? []).filter((x) => x.ok).map((x) => TOOL_LABEL[x.tool] ?? x.tool))];

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  };

  return (
    <article className="bubble bubble--ai">
      <p className="bubble__label">
        <span className="tag">{t("AI-generated")}</span>
        {message.provider && <span className="bubble__provider">{label(message.provider)}</span>}
      </p>
      {message.switched && message.provider && (
        <p className="chat__draft-note" role="status">
          {t(
            message.switched.reason === "limit"
              ? "{from} has reached its usage limit, so {used} answered."
              : "{from} couldn't answer, so {used} did.",
            { from: label(message.switched.from), used: label(message.provider) },
          )}
        </p>
      )}
      <RichText text={message.content} />
      {message.restored && (message.drafts ?? 0) > 0 && (
        <p className="chat__draft-note">
          {t("A draft was shown here. Drafts aren't kept: ask again if you still need it.")}
        </p>
      )}
      <footer className="bubble__foot">
        <span>
          {message.restored
            ? ""
            : sources.length > 0
              ? t("Based on: {sources}", { sources: sources.join(t(", ")) })
              : t("Not based on project data")}
        </span>
        <button type="button" className="link-btn" onClick={copy}>
          {copied ? t("Copied") : t("Copy")}
        </button>
      </footer>
      {message.proposals?.map((plan, i) => <ProjectProposal key={i} plan={plan} org={org} />)}
      {message.stockProposals?.map((draft, i) => <StockProposal key={i} draft={draft} org={org} />)}
      {message.actionProposals?.map((draft, i) => <ActionProposal key={i} draft={draft} />)}
    </article>
  );
}

const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
const timeFmt = new Intl.DateTimeFormat(getLocale(), { hour: "2-digit", minute: "2-digit" });
const dayFmt = new Intl.DateTimeFormat(getLocale(), { day: "numeric", month: "short" });
const yearFmt = new Intl.DateTimeFormat(getLocale(), { day: "numeric", month: "short", year: "numeric" });

function when(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  if (sameDay(d, now)) return timeFmt.format(d);
  return d.getFullYear() === now.getFullYear() ? dayFmt.format(d) : yearFmt.format(d);
}

function HistoryList({ org }: { org: Organization }) {
  const a = useAssistant();
  const [items, setItems] = useState<ConversationSummary[] | null>(null);
  const [retention, setRetention] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<number | "all" | null>(null);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    let alive = true;
    api<{ conversations: ConversationSummary[]; retention_days: number }>(`/ai/conversations?organization_id=${org.id}`)
      .then((r) => {
        if (!alive) return;
        setItems(r.conversations);
        setRetention(r.retention_days);
      })
      .catch((e) => alive && setError(errorMessage(e, t("Couldn't load your conversations."))));
    return () => {
      alive = false;
    };
  }, [org.id]);

  const remove = async (target: number | "all") => {
    setWorking(true);
    setError(null);
    try {
      if (target === "all") await api(`/ai/conversations?organization_id=${org.id}`, { method: "DELETE" });
      else await api(`/ai/conversations/${target}?organization_id=${org.id}`, { method: "DELETE" });
      setItems((list) => (target === "all" ? [] : (list ?? []).filter((c) => c.id !== target)));
      a.forget(target === "all" ? "all" : [target]);
    } catch (e) {
      setError(errorMessage(e, t("Couldn't delete the conversation.")));
    } finally {
      setWorking(false);
      setConfirming(null);
    }
  };

  const projectName = (id: number | null) => (id ? a.projects.find((p) => p.id === id)?.name : undefined);

  return (
    <div className="assistant-panel__body assistant-history">
      {retention !== null && (
        <p className="muted assistant-history__note">
          {t("Only you can see your conversations. Each one is deleted {days} days after its last message.", {
            days: retention,
          })}
        </p>
      )}
      <FormError message={error} />
      {items === null && !error && <p className="muted">{t("Loading…")}</p>}
      {items?.length === 0 && <p className="muted">{t("No saved conversations yet.")}</p>}
      {items && items.length > 0 && (
        <ul className="assistant-history__list">
          {items.map((c) => (
            <li key={c.id} className="assistant-history__item" data-current={c.id === a.conversationId || undefined}>
              <button
                type="button"
                className="assistant-history__open"
                onClick={() => void a.openConversation(c.id)}
                disabled={a.busy}
              >
                <span className="assistant-history__title">{c.title}</span>
                <span className="assistant-history__meta">
                  {[projectName(c.project_id), when(c.updated_at)].filter(Boolean).join(" · ")}
                </span>
              </button>
              {confirming === c.id ? (
                <span className="assistant-history__confirm">
                  <button type="button" className="link-btn link-btn--danger" onClick={() => void remove(c.id)} disabled={working}>
                    {t("Delete")}
                  </button>
                  <button type="button" className="link-btn" onClick={() => setConfirming(null)} disabled={working}>
                    {t("Cancel")}
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  className="assistant-panel__icon"
                  onClick={() => setConfirming(c.id)}
                  aria-label={t("Delete “{title}”", { title: c.title })}
                  title={t("Delete")}
                  disabled={a.busy && c.id === a.conversationId}
                >
                  <Trash2 />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {items && items.length > 0 && (
        <div className="assistant-history__all">
          {confirming === "all" ? (
            <>
              <span>{t("Delete all your conversations in this organization?")}</span>
              <button type="button" className="link-btn link-btn--danger" onClick={() => void remove("all")} disabled={working}>
                {t("Delete all")}
              </button>
              <button type="button" className="link-btn" onClick={() => setConfirming(null)} disabled={working}>
                {t("Cancel")}
              </button>
            </>
          ) : (
            <button type="button" className="link-btn link-btn--danger" onClick={() => setConfirming("all")} disabled={a.busy}>
              {t("Delete all conversations")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Model output is untrusted: render it as plain text only (React escapes it), with paragraphs
 * and "- " bullet lists recognised. Never use dangerouslySetInnerHTML here.
 */
function RichText({ text }: { text: string }) {
  const blocks = text.replace(/\r\n/g, "\n").split(/\n\s*\n/);
  return (
    <div className="rich">
      {blocks.map((block, i) => {
        const lines = block.split("\n").filter((l) => l.trim());
        const bullet = /^\s*(?:[-*•]|\d+[.)])\s+/;
        if (lines.length > 0 && lines.every((l) => bullet.test(l))) {
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j}>{strip(l.replace(bullet, ""))}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {strip(l)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

/** Drop markdown emphasis markers the model sometimes adds despite the prompt. */
const strip = (line: string) => line.replace(/\*\*(.+?)\*\*/g, "$1").replace(/^#+\s+/, "");
