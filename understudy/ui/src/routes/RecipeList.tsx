import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { ChevronRight } from "lucide-react";

export function RecipeList({ onOpen }: { onOpen: (id: string) => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["recipes"],
    queryFn: () => api.listRecipes(),
  });

  return (
    <div className="flex h-full w-full flex-col">
      <header className="flex h-12 shrink-0 items-center border-b border-border-subtle bg-bg-base px-5">
        <div className="flex items-center gap-3">
          <div className="font-sans text-[16px] font-semibold tracking-tight">
            U
          </div>
          <div className="text-title font-medium">Understudy</div>
        </div>
      </header>

      <main className="flex-1 overflow-auto">
        <div className="mx-auto max-w-3xl px-8 py-10">
          <div className="mb-6">
            <div className="text-head font-medium uppercase text-fg-tertiary">
              Recipes
            </div>
          </div>

          {isLoading && (
            <div className="text-body text-fg-secondary">loading…</div>
          )}
          {error && (
            <div className="text-body text-danger">
              {(error as Error).message}
            </div>
          )}

          {data && data.length === 0 && <EmptyState />}

          {data && data.length > 0 && (
            <ul className="flex flex-col gap-2">
              {data.map((r) => (
                <li key={r.id}>
                  <button
                    onClick={() => onOpen(r.id)}
                    className="group flex w-full items-center justify-between rounded-md border border-border-subtle bg-bg-raised px-5 py-4 text-left transition-colors hover:border-border"
                  >
                    <div className="flex min-w-0 flex-col gap-1">
                      <div className="flex items-baseline gap-3">
                        <span className="text-body font-medium text-fg-primary">
                          {r.task_name}
                        </span>
                        <span className="font-mono text-caption text-fg-tertiary">
                          {r.id.slice(0, 8)}
                        </span>
                      </div>
                      <span className="truncate text-label text-fg-secondary">
                        {r.description}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-label text-fg-tertiary">
                      <span>
                        {r.step_count} step{r.step_count === 1 ? "" : "s"}
                      </span>
                      <span>
                        {r.param_count} param{r.param_count === 1 ? "" : "s"}
                      </span>
                      <ChevronRight
                        className="text-fg-tertiary group-hover:text-fg-primary"
                        size={16}
                      />
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-6 py-16 text-center">
      <div className="max-w-md">
        <div className="text-title font-medium">No recipe yet.</div>
        <p className="mt-3 text-body text-fg-secondary">
          Record a workflow with{" "}
          <code className="rounded-xs border border-border-subtle bg-bg-raised px-1.5 py-0.5 font-mono text-label">
            understudy record
          </code>{" "}
          then induce a recipe with{" "}
          <code className="rounded-xs border border-border-subtle bg-bg-raised px-1.5 py-0.5 font-mono text-label">
            understudy induce
          </code>
          .
        </p>
      </div>
      <div className="w-80 rounded-md border border-dashed border-border px-6 py-6 text-center font-mono text-label text-fg-tertiary">
        first step appears here
      </div>
    </div>
  );
}
