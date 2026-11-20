import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { SaveStatus } from "@/components/ui/SaveIndicator";

/** Autosave indicator for the whole workspace: watches every mutation (pending, succeeded, failed) in the query client. */
export function useSaveStatus(): { status: SaveStatus; savedAt: Date | null } {
  const queryClient = useQueryClient();
  const [state, setState] = useState<{ status: SaveStatus; savedAt: Date | null }>({ status: "idle", savedAt: null });
  useEffect(() => {
    const mutationCache = queryClient.getMutationCache();
    return mutationCache.subscribe(() => {
      const mutations = mutationCache.getAll();
      if (mutations.some((mutation) => mutation.state.status === "pending")) {
        setState((previous) => ({ ...previous, status: "saving" }));
        return;
      }
      const latestMutation = [...mutations].sort((first, second) => second.state.submittedAt - first.state.submittedAt)[0];
      if (!latestMutation) return;
      setState((previous) =>
        latestMutation.state.status === "error"
          ? { ...previous, status: "error" }
          : { status: "saved", savedAt: previous.status === "saved" ? previous.savedAt : new Date() },
      );
    });
  }, [queryClient]);
  return state;
}
