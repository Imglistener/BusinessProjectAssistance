import { useEffect } from "react";
import { Navigate, useSearchParams } from "react-router";
import { useAssistant } from "../assistant/AssistantContext";

/**
 * Old links and bookmarks (/app/assistant?project=3&q=...) open the side panel over the matching page:
 * the project's page when one is given, otherwise the dashboard.
 */
export default function Assistant() {
  const [params] = useSearchParams();
  const { openWith } = useAssistant();
  const raw = params.get("project");
  const project = raw && /^\d+$/.test(raw) ? raw : undefined;
  const question = params.get("q") ?? undefined;

  useEffect(() => {
    openWith({ projectId: project, question });
    // Once, on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <Navigate to={project ? `/app/projects/${project}` : "/app"} replace />;
}
