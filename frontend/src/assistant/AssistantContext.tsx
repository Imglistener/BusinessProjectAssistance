import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, api } from "../api/client";
import type {
  ActionDraft,
  AIProviderInfo,
  ChatReply,
  ConversationDetail,
  Project,
  ProjectPlan,
  StockDraft,
  ToolTraceEntry,
} from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { errorMessage } from "../lib/errors";
import { t } from "../i18n";

/**
 * The assistant lives in a side panel above the routes, so a conversation (and any draft card in it) survives
 * moving around the app. Conversations are saved on the server; this keeps the one on screen.
 */

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  trace?: ToolTraceEntry[];
  proposals?: ProjectPlan[];
  stockProposals?: StockDraft[];
  actionProposals?: ActionDraft[];
  /** Reopened from history: tool sources weren't kept, and drafts are only counted. */
  restored?: boolean;
  drafts?: number;
  provider?: string | null;
  switched?: ChatReply["switched"];
}

interface AssistantState {
  open: boolean;
  wide: boolean;
  view: "chat" | "history";
  conversationId: number | null;
  messages: ChatMessage[];
  /** Loading a saved conversation. */
  loading: boolean;
  busy: boolean;
  error: string | null;
  input: string;
  projectId: string;
  projects: Project[];
  /** The AIs to choose from, the default first. */
  providers: AIProviderInfo[];
  /** The one the next question goes to: the person's choice, or another while that one's limit is reached. */
  provider: AIProviderInfo | null;
  setProvider(id: string): void;
  setOpen(open: boolean): void;
  toggle(): void;
  setWide(wide: boolean): void;
  setView(view: "chat" | "history"): void;
  setInput(text: string): void;
  setProjectId(id: string): void;
  /** Open the panel, optionally about a project and with a question ready to send. */
  openWith(options?: { projectId?: number | string; question?: string }): void;
  send(text: string): Promise<void>;
  newConversation(): void;
  openConversation(id: number): Promise<void>;
  /** After deleting conversations: forget the one on screen if it was among them. */
  forget(ids: number[] | "all"): void;
}

const AssistantContext = createContext<AssistantState | null>(null);

const OPEN_KEY = "bpa.assistant.open";
const WIDE_KEY = "bpa.assistant.wide";
const PROVIDER_KEY = "bpa.assistant.provider";
// Longest delay setTimeout takes (about 24 days); limits reset long before.
const MAX_TIMER_MS = 2 ** 31 - 1;
const convKey = (orgId: number) => `bpa.assistant.conversation.${orgId}`;

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the choice lasts until reload */
  }
}

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { org } = useOrg();
  const orgId = user ? (org?.id ?? null) : null;

  const [open, setOpenState] = useState(() => read(OPEN_KEY) === "1");
  const [wide, setWideState] = useState(() => read(WIDE_KEY) === "1");
  const [view, setView] = useState<"chat" | "history">("chat");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [projectId, setProjectId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [providers, setProviders] = useState<AIProviderInfo[]>([]);
  const [choice, setChoice] = useState<string | null>(() => read(PROVIDER_KEY));
  const provider = useMemo(() => {
    const chosen = providers.find((p) => p.id === choice) ?? providers[0] ?? null;
    return chosen?.available ? chosen : (providers.find((p) => p.available) ?? chosen);
  }, [providers, choice]);
  const setProvider = useCallback((id: string) => {
    setChoice(id);
    write(PROVIDER_KEY, id);
  }, []);
  // Replies or loads that arrive after the user moved on (another conversation or organization) are dropped.
  const generation = useRef(0);
  // openWith() before the organization is known (a link opened on a fresh page load): applied once it is.
  const pending = useRef<{ projectId?: string; question?: string } | null>(null);

  const setOpen = useCallback((value: boolean) => {
    setOpenState(value);
    write(OPEN_KEY, value ? "1" : "0");
  }, []);
  const setWide = useCallback((value: boolean) => {
    setWideState(value);
    write(WIDE_KEY, value ? "1" : "0");
  }, []);

  const remember = useCallback(
    (id: number | null) => {
      setConversationId(id);
      if (orgId !== null) write(convKey(orgId), id === null ? null : String(id));
    },
    [orgId],
  );

  const reset = useCallback(() => {
    generation.current += 1;
    setConversationId(null);
    setMessages([]);
    setBusy(false);
    setLoading(false);
    setError(null);
    setInput("");
    setProjectId("");
  }, []);

  const load = useCallback(
    async (id: number) => {
      if (orgId === null) return;
      const gen = ++generation.current;
      setLoading(true);
      setError(null);
      try {
        const r = await api<{ conversation: ConversationDetail }>(`/ai/conversations/${id}?organization_id=${orgId}`);
        if (gen !== generation.current) return;
        const c = r.conversation;
        setMessages(c.messages.map((m) => ({ role: m.role, content: m.content, restored: true, drafts: m.drafts, provider: m.provider })));
        setProjectId(c.project_id ? String(c.project_id) : "");
        remember(c.id);
      } catch (e) {
        if (gen !== generation.current) return;
        if (e instanceof ApiError && e.code === "conversation_not_found") {
          // Deleted or past the retention period: start fresh without a message.
          remember(null);
          setMessages([]);
        } else {
          setError(errorMessage(e, t("Couldn't load the conversation.")));
        }
      } finally {
        if (gen === generation.current) setLoading(false);
      }
    },
    [orgId, remember],
  );

  // Signing out or switching organization clears the panel; the last conversation of the new one comes back.
  useEffect(() => {
    reset();
    setProjects([]);
    if (orgId === null) return;
    const request = pending.current;
    pending.current = null;
    if (request) {
      // A link asked for this project or question: start there rather than in the last conversation.
      remember(null);
      if (request.projectId !== undefined) setProjectId(request.projectId);
      if (request.question) setInput(request.question);
      return;
    }
    const saved = Number(read(convKey(orgId)));
    if (saved) void load(saved);
  }, [orgId, reset, load, remember]);

  // The project list for "About", refreshed each time the panel opens (a draft may have created one).
  useEffect(() => {
    if (!open || orgId === null) return;
    let alive = true;
    api<{ projects: Project[] }>(`/organizations/${orgId}/projects`)
      .then((r) => alive && setProjects(r.projects))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [open, orgId]);

  const loadProviders = useCallback(
    () =>
      api<{ providers: AIProviderInfo[] }>("/ai/providers")
        .then((r) => setProviders(r.providers))
        .catch(() => undefined), // the picker keeps what it had
    [],
  );
  useEffect(() => {
    if (open && orgId !== null) void loadProviders();
  }, [open, orgId, loadProviders]);
  // Offer an exhausted one again as soon as its limit resets.
  useEffect(() => {
    const resets = providers.filter((p) => p.available_at).map((p) => Date.parse(p.available_at!));
    if (!open || resets.length === 0) return;
    const delay = Math.min(Math.max(Math.min(...resets) - Date.now() + 1000, 1000), MAX_TIMER_MS);
    const timer = window.setTimeout(() => void loadProviders(), delay);
    return () => window.clearTimeout(timer);
  }, [open, providers, loadProviders]);

  const newConversation = useCallback(() => {
    reset();
    remember(null);
    setView("chat");
  }, [reset, remember]);

  const openConversation = useCallback(
    async (id: number) => {
      setView("chat");
      if (id === conversationId) return;
      reset();
      await load(id);
    },
    [conversationId, reset, load],
  );

  const openWith = useCallback(
    (options: { projectId?: number | string; question?: string } = {}) => {
      setOpen(true);
      setView("chat");
      const pid = options.projectId === undefined ? undefined : String(options.projectId);
      const question = options.question?.slice(0, 2000);
      if (orgId === null) {
        pending.current = { projectId: pid, question };
        return;
      }
      // A different project, or a question from elsewhere in the app, starts a new conversation
      // (also when a saved one is still loading, so it can't overwrite the request).
      const switching = (pid !== undefined && pid !== projectId) || Boolean(question);
      if (!busy && switching && (messages.length > 0 || loading)) {
        reset();
        remember(null);
      }
      if (pid !== undefined) setProjectId(pid);
      if (question) setInput(question);
    },
    [orgId, busy, loading, messages.length, projectId, reset, remember, setOpen],
  );

  const send = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || busy || loading || orgId === null) return;
      const gen = generation.current;
      setMessages((m) => [...m, { role: "user", content: question }]);
      setInput("");
      setError(null);
      setBusy(true);
      try {
        const r = await api<ChatReply>("/ai/chat", {
          body: {
            organization_id: orgId,
            message: question,
            project_id: projectId ? Number(projectId) : null,
            conversation_id: conversationId,
            provider: provider?.id ?? null,
          },
        });
        setProviders(r.providers);
        if (gen !== generation.current) return; // saved; it shows up in history
        remember(r.conversation.id);
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: r.answer,
            trace: r.tool_trace,
            proposals: r.proposals ?? [],
            stockProposals: r.stock_proposals ?? [],
            actionProposals: r.action_proposals ?? [],
            provider: r.provider,
            switched: r.switched,
          },
        ]);
      } catch (e) {
        if (e instanceof ApiError && Array.isArray(e.details?.providers)) setProviders(e.details.providers as AIProviderInfo[]);
        if (gen !== generation.current) return;
        // Put the question back so it isn't lost.
        setMessages((m) => m.slice(0, -1));
        setInput(question);
        if (e instanceof ApiError && e.code === "conversation_not_found") {
          // The conversation was deleted (or expired) meanwhile: the next try starts a new one.
          remember(null);
          setMessages([]);
          setError(t("That conversation no longer exists. Send your question again to start a new one."));
        } else {
          setError(
            e instanceof ApiError && e.code === "network"
              ? e.message
              : errorMessage(e, t("The assistant couldn't answer. Try again.")),
          );
        }
      } finally {
        if (gen === generation.current) setBusy(false);
      }
    },
    [busy, loading, orgId, projectId, conversationId, provider, remember],
  );

  const forget = useCallback(
    (ids: number[] | "all") => {
      if (ids === "all" || (conversationId !== null && ids.includes(conversationId))) {
        reset();
        remember(null);
      }
    },
    [conversationId, reset, remember],
  );

  const value = useMemo<AssistantState>(
    () => ({
      open,
      wide,
      view,
      conversationId,
      messages,
      loading,
      busy,
      error,
      input,
      projectId,
      projects,
      providers,
      provider,
      setProvider,
      setOpen,
      toggle: () => setOpen(!open),
      setWide,
      setView,
      setInput,
      setProjectId,
      openWith,
      send,
      newConversation,
      openConversation,
      forget,
    }),
    [open, wide, view, conversationId, messages, loading, busy, error, input, projectId, projects, providers, provider,
      setProvider, setOpen, setWide,
      openWith, send, newConversation, openConversation, forget],
  );

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantState {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error("useAssistant must be used inside AssistantProvider");
  return ctx;
}

