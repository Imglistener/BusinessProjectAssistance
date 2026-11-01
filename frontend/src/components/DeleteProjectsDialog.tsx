import { Loader2, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { errorMessage } from "../lib/errors";
import { FormAlert } from "./form";
import { t } from "../i18n";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

interface Preview {
  projects: { id: number; name: string; status: string }[];
  expenses: number;
  receipts: number;
  tasks: number;
  milestones: number;
  trips: number;
  stock_movements: number;
}

const SHOWN = 6;

/**
 * Confirms deleting one or more projects for good. Shows what will be removed (from the server, so the
 * numbers are exact) and asks the person to type a word, since there's no undo.
 */
export function DeleteProjectsDialog({
  orgId,
  projectIds,
  open,
  onOpenChange,
  onDeleted,
}: {
  orgId: number;
  projectIds: number[];
  open: boolean;
  onOpenChange(open: boolean): void;
  onDeleted(count: number): void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const word = t("delete");
  const ids = projectIds.join(",");

  useEffect(() => {
    if (!open) return;
    setPreview(null);
    setError(null);
    setTyped("");
    api<Preview>(`/organizations/${orgId}/projects/delete-preview`, { body: { project_ids: projectIds } })
      .then(setPreview)
      .catch((e) => setError(errorMessage(e)));
    // `ids` stands in for projectIds: a new array with the same IDs shouldn't reload the preview.
  }, [open, orgId, ids]);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ deleted: number }>(`/organizations/${orgId}/projects/delete`, {
        body: { project_ids: projectIds },
      });
      onDeleted(r.deleted);
      onOpenChange(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const count = projectIds.length;
  const matches = typed.trim().toLowerCase() === word.toLowerCase();
  const removed = preview
    ? [
        [preview.expenses, t("{count} expenses", { count: preview.expenses })],
        [preview.receipts, t("{count} receipts", { count: preview.receipts })],
        [preview.tasks, t("{count} tasks", { count: preview.tasks })],
        [preview.milestones, t("{count} milestones", { count: preview.milestones })],
        [preview.trips, t("{count} trips", { count: preview.trips })],
      ].filter(([n]) => (n as number) > 0)
    : [];

  return (
    <AlertDialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <AlertDialogContent className="sm:max-w-md">
        <AlertDialogHeader>
          <span className="mb-1 flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <Trash2 className="size-5" />
          </span>
          <AlertDialogTitle>{t("Delete {count} projects?", { count })}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("This can't be undone. To keep a project's records but put it away, archive it instead.")}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="grid gap-4 text-sm">
          {!preview && !error && (
            <div className="grid gap-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          )}
          {preview && (
            <>
              <ul className="grid gap-1 rounded-lg border bg-muted/40 p-3">
                {preview.projects.slice(0, SHOWN).map((p) => (
                  <li key={p.id} className="truncate font-medium">
                    {p.name}
                  </li>
                ))}
                {preview.projects.length > SHOWN && (
                  <li className="text-muted-foreground">
                    {t("and {count} more.", { count: preview.projects.length - SHOWN })}
                  </li>
                )}
              </ul>
              <p className="text-muted-foreground">
                {removed.length > 0
                  ? t("Also deleted: {items}.", { items: removed.map(([, label]) => label).join(t(", ")) })
                  : t("These projects have no expenses, tasks or trips.")}
                {preview.stock_movements > 0 && ` ${t("Stock history is kept.")}`}
              </p>
              <div className="grid gap-2">
                <Label htmlFor="delete-confirm" className="font-normal">
                  {t("Type {word} to confirm.", { word })}
                </Label>
                <Input
                  id="delete-confirm"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  autoComplete="off"
                  autoFocus
                  disabled={busy}
                  onKeyDown={(e) => e.key === "Enter" && matches && !busy && confirm()}
                />
              </div>
            </>
          )}
          <FormAlert message={error} />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{t("Cancel")}</AlertDialogCancel>
          <Button variant="destructive" onClick={confirm} disabled={!preview || !matches || busy}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            {t("Delete {count} projects", { count })}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
