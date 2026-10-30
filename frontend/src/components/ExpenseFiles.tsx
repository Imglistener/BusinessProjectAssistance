import { useEffect, useRef, useState } from "react";
import { api, download, openFile, uploadFile } from "../api/client";
import type { Attachment } from "../api/models";
import { errorMessage } from "../lib/errors";

const ACCEPT = "application/pdf,image/jpeg,image/png,image/webp";

const size = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

/** Receipts on one expense: list, view, download, upload and remove. */
export function ExpenseFiles({
  expenseId,
  canChange,
  onCountChange,
}: {
  expenseId: number;
  canChange: boolean;
  onCountChange(count: number): void;
}) {
  const [files, setFiles] = useState<Attachment[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<{ attachments: Attachment[] }>(`/expenses/${expenseId}/attachments`)
      .then((r) => setFiles(r.attachments))
      .catch((e) => setError(errorMessage(e, "Couldn't load files.")));
  }, [expenseId]);

  const update = (next: Attachment[]) => {
    setFiles(next);
    onCountChange(next.length);
  };

  const onPick = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const r = await uploadFile<{ attachment: Attachment }>(`/expenses/${expenseId}/attachments`, file);
      update([...(files ?? []), r.attachment]);
    } catch (e) {
      setError(errorMessage(e, "The upload failed. Try again."));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  const remove = async (a: Attachment) => {
    setError(null);
    try {
      await api(`/attachments/${a.id}`, { method: "DELETE" });
      update((files ?? []).filter((f) => f.id !== a.id));
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const run = (fn: () => Promise<void>) => fn().catch((e) => setError(errorMessage(e)));

  return (
    <div className="files">
      {error && (
        <p className="field__message field__message--error" role="alert">
          {error}
        </p>
      )}
      {files === null && !error && <p className="muted">Loading…</p>}
      {files && files.length === 0 && <p className="muted">No receipts attached.</p>}
      {files && files.length > 0 && (
        <ul className="files__list">
          {files.map((a) => (
            <li key={a.id}>
              <span className="files__name">{a.filename}</span>
              <span className="muted"> — {size(a.size)}</span>
              <span className="row__confirm files__actions">
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => run(() => openFile(`/attachments/${a.id}/file`))}
                >
                  View
                </button>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => run(() => download(`/attachments/${a.id}/file`, a.filename))}
                >
                  Download
                </button>
                {canChange && (
                  <button type="button" className="link-btn" onClick={() => remove(a)}>
                    Remove
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {canChange && (
        <label className="files__upload">
          <input
            ref={input}
            type="file"
            accept={ACCEPT}
            disabled={busy}
            onChange={(e) => onPick(e.target.files?.[0])}
            aria-label="Attach a receipt"
          />
          <span className="muted">{busy ? "Uploading…" : "PDF, JPEG, PNG or WebP, up to 10 MB."}</span>
        </label>
      )}
    </div>
  );
}
