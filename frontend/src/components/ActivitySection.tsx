import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Project } from "../api/models";
import { type ActivityEntry, describe, formatWhen } from "../lib/activity";
import { errorMessage } from "../lib/errors";
import { FormError } from "./AuthLayout";
import { t } from "../i18n";

const PAGE = 10;

interface ActivityPage {
  entries: ActivityEntry[];
  people: Record<string, string>;
  total: number;
}

/** Audit trail of the project. `refreshKey` changes whenever something on the page was saved. */
export function ActivitySection({ project, refreshKey }: { project: Project; refreshKey: number }) {
  const [entries, setEntries] = useState<ActivityEntry[] | null>(null);
  const [people, setPeople] = useState<Record<string, string>>({});
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    (offset = 0) =>
      api<ActivityPage>(`/projects/${project.id}/activity?limit=${PAGE}&offset=${offset}`)
        .then((r) => {
          setError(null);
          setEntries((prev) => (offset === 0 || !prev ? r.entries : [...prev, ...r.entries]));
          setPeople((prev) => ({ ...prev, ...r.people }));
          setTotal(r.total);
        })
        .catch((e) => setError(errorMessage(e, t("Couldn't load the activity.")))),
    [project.id],
  );

  useEffect(() => {
    load(0);
  }, [load, refreshKey]);

  return (
    <section className="projects-section" aria-labelledby="activity-heading">
      <div className="section-head">
        <h2 id="activity-heading">{t("Activity")}</h2>
      </div>
      <FormError message={error} />
      {entries === null && !error && <p className="muted">{t("Loading…")}</p>}
      {entries && entries.length === 0 && <p className="muted">{t("No changes recorded yet.")}</p>}
      {entries && entries.length > 0 && (
        <ol className="activity">
          {entries.map((e) => (
            <li key={e.id}>
              <time dateTime={e.at}>{formatWhen(e.at)}</time>
              <p>
                <strong>{e.actor ?? t("Someone")}</strong> {describe(e, people, project.currency)}.
              </p>
            </li>
          ))}
        </ol>
      )}
      {entries && entries.length < total && (
        <button type="button" className="btn btn--quiet" onClick={() => load(entries.length)}>
          {t("Show older")}
        </button>
      )}
    </section>
  );
}
