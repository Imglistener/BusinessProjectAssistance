import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { ChatReply, ProjectPlan, Organization, Project, ToolTraceEntry } from "../api/models";
import { useOrg } from "../auth/OrgContext";
import { AppShell } from "../components/AppShell";
import { ProjectProposal } from "../components/ProjectProposal";
import { FormError } from "../components/AuthLayout";
import { errorMessage } from "../lib/errors";
import { t } from "../i18n";
import { tx } from "../i18n/rich";

const HISTORY_TURNS = 12;

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
  calculate: t("Calculator"),
  vat: t("VAT calculation"),
  budget_what_if: t("Budget what-if"),
  estimate_trip_fuel_cost: t("Trip fuel estimate"),
  estimate_fuel_cost: t("Fuel estimate"),
  propose_project: t("Project draft"),
};

const GENERAL_PROMPTS = [
  t("A customer wants a 3-day team retreat in Ifrane for 25 people next March, about 80000 MAD. Set it up as a project."),
  t("Which projects need attention right now?"),
  t("Are any projects over budget?"),
  t("Which projects have overdue tasks?"),
  t("What would it cost in fuel to drive a van from Casablanca to Marrakech and back?"),
  t("What's the VAT on 12,500 MAD, and the total including VAT?"),
  t("What's running low in stock?"),
];

const PROJECT_PROMPTS = [
  t("How is the budget looking?"),
  t("What are we spending the most on?"),
  t("At the current spend rate, how long will the budget last?"),
  t("Draft a short status update I can share."),
  t("If we spend 5,000 more, how much budget is left?"),
  t("How much fuel will our planned trips cost?"),
];

interface Message {
  role: "user" | "assistant";
  content: string;
  trace?: ToolTraceEntry[];
  proposals?: ProjectPlan[];
}

export default function Assistant() {
  const [params, setParams] = useSearchParams();
  const { orgs, org, error: orgError } = useOrg();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectError, setProjectError] = useState<string | null>(null);
  const loadError = orgError ?? projectError;

  useEffect(() => {
    setProjects([]);
    if (!org) return;
    api<{ projects: Project[] }>(`/organizations/${org.id}/projects`)
      .then((r) => setProjects(r.projects))
      .catch((e) => setProjectError(errorMessage(e, t("Couldn't load your projects."))));
  }, [org]);

  const projectId = params.get("project") ?? "";
  const setProjectId = (id: string) => setParams(id ? { project: id } : {}, { replace: true });

  return (
    <AppShell>
      <header className="main__header">
        <h1>{t("Assistant")}</h1>
        <p className="main__org">
          {t("Ask about your projects, budgets, expenses and deadlines. It reads your data and drafts plans, but never changes anything without you.")}
        </p>
      </header>

      <FormError message={loadError} />
      {orgs === null && !loadError && <p className="muted">{t("Loading…")}</p>}
      {orgs !== null && !org && (
        <p className="muted">
          {tx("Create your organization on the {dashboard} first.", { dashboard: <Link to="/app">{t("dashboard")}</Link> })}
        </p>
      )}
      {org && (
        <Chat
          key={org.id}
          org={org}
          projects={projects}
          projectId={projectId}
          onProjectChange={setProjectId}
          initialQuestion={params.get("q") ?? ""}
        />
      )}
    </AppShell>
  );
}

function Chat({
  org,
  projects,
  projectId,
  onProjectChange,
  initialQuestion,
}: {
  org: Organization;
  projects: Project[];
  projectId: string;
  onProjectChange(id: string): void;
  /** Pre-filled from ?q= (e.g. "Ask the assistant about this" on a trip). */
  initialQuestion: string;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState(initialQuestion.slice(0, 2000));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages, busy]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    const history = messages.slice(-HISTORY_TURNS).map(({ role, content }) => ({ role, content }));
    setMessages((m) => [...m, { role: "user", content: question }]);
    setDraft("");
    setError(null);
    setBusy(true);
    try {
      const r = await api<ChatReply>("/ai/chat", {
        body: {
          organization_id: org.id,
          message: question,
          project_id: projectId ? Number(projectId) : null,
          history,
        },
      });
      setMessages((m) => [
        ...m,
        { role: "assistant", content: r.answer, trace: r.tool_trace, proposals: r.proposals ?? [] },
      ]);
    } catch (e) {
      // Put the question back so it isn't lost.
      setMessages((m) => m.slice(0, -1));
      setDraft(question);
      setError(
        e instanceof ApiError && e.code === "network"
          ? e.message
          : errorMessage(e, t("The assistant couldn't answer. Try again.")),
      );
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(draft);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(draft);
    }
  };

  const prompts = projectId ? PROJECT_PROMPTS : GENERAL_PROMPTS;

  return (
    <section className="chat" aria-label={t("Conversation")}>
      <div className="chat__bar">
        <div className="field chat__project">
          <label htmlFor="chat-project">{t("About")}</label>
          <div className="field__control">
            <select id="chat-project" value={projectId} onChange={(e) => onProjectChange(e.target.value)}>
              <option value="">{t("All projects")}</option>
              {projects.map((p) => (
                <option key={p.id} value={String(p.id)}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        {messages.length > 0 && (
          <button type="button" className="link-btn" onClick={() => setMessages([])} disabled={busy}>
            {t("New conversation")}
          </button>
        )}
      </div>

      <div className="chat__log" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat__empty">
            <p className="muted">{t("Try one of these:")}</p>
            <ul className="chips">
              {prompts.map((p) => (
                <li key={p}>
                  <button type="button" className="chip" onClick={() => send(p)} disabled={busy}>
                    {p}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="bubble bubble--user">
              <span className="visually-hidden">{t("You:")}{" "}</span>
              {m.content}
            </div>
          ) : (
            <AssistantMessage key={i} message={m} org={org} />
          ),
        )}

        {busy && (
          <p className="chat__thinking" role="status">
            {t("Looking at your data…")}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <FormError message={error} />

      <form className="composer" onSubmit={onSubmit}>
        <label htmlFor="chat-input" className="visually-hidden">
          {t("Your question")}
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          rows={2}
          maxLength={2000}
          placeholder={projectId ? t("Ask about this project…") : t("Ask about your projects…")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="btn btn--primary" disabled={busy || !draft.trim()}>
          {t("Ask")}
        </button>
      </form>

      <p className="chat__disclosure">
        {t("Your question and the project figures needed to answer it are sent to an external AI provider. Answers are AI-generated and can be wrong: check important figures on the project page.")}
      </p>
    </section>
  );
}

function AssistantMessage({ message, org }: { message: Message; org: Organization }) {
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
      </p>
      <RichText text={message.content} />
      <footer className="bubble__foot">
        <span>{sources.length > 0 ? t("Based on: {sources}", { sources: sources.join(t(", ")) }) : t("Not based on project data")}</span>
        <button type="button" className="link-btn" onClick={copy}>
          {copied ? t("Copied") : t("Copy")}
        </button>
      </footer>
      {message.proposals?.map((plan, i) => (
        <ProjectProposal key={i} plan={plan} org={org} />
      ))}
    </article>
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
