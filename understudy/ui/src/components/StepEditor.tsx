import { useEffect, useState } from "react";
import { X, Wand2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { api } from "../lib/api";
import type { RecipeStep, ResynthResponse } from "../lib/types";

interface Props {
  recipeId: string;
  step: RecipeStep;
  onClose: () => void;
}

export function StepEditor({ recipeId, step, onClose }: Props) {
  const [intent, setIntent] = useState(step.intent);
  const [pendingStep, setPendingStep] = useState<RecipeStep | null>(null);
  const [reasoning, setReasoning] = useState<string | null>(null);
  const [resynthing, setResynthing] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    setIntent(step.intent);
    setPendingStep(null);
    setReasoning(null);
  }, [step.idx, step.intent]);

  const resynth = useMutation<ResynthResponse, Error, { intent: string }>({
    mutationFn: async ({ intent }) =>
      api.resynthStep(recipeId, step.idx, intent, false),
    onMutate: () => setResynthing(true),
    onSettled: () => setResynthing(false),
    onSuccess: (data) => {
      setPendingStep(data.new_step);
      setReasoning(data.reasoning);
    },
  });

  const apply = useMutation<ResynthResponse, Error, { intent: string }>({
    mutationFn: async ({ intent }) =>
      api.resynthStep(recipeId, step.idx, intent, true),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recipe", recipeId] });
      setPendingStep(null);
      setReasoning(null);
    },
  });

  const unchanged = intent.trim() === step.intent.trim();

  return (
    <aside
      className={clsx(
        "flex h-full w-[440px] flex-col border-l border-border-subtle bg-bg-base",
        "shadow-[-24px_0_48px_-12px_rgba(0,0,0,0.4)]",
      )}
    >
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border-subtle px-5">
        <div className="flex items-center gap-3">
          <span className="font-mono text-label text-fg-tertiary">
            step {String(step.idx).padStart(2, "0")}
          </span>
          <span className="font-mono text-label text-fg-secondary">
            {step.action}
          </span>
        </div>
        <button
          onClick={onClose}
          className="rounded-sm p-1 text-fg-tertiary hover:bg-bg-pressed hover:text-fg-primary"
        >
          <X size={16} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        <Section title="Intent">
          <textarea
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            rows={4}
            className={clsx(
              "block w-full resize-y rounded-sm border bg-bg-raised px-3 py-2 text-body text-fg-primary",
              "placeholder:text-fg-tertiary focus:outline-none",
              resynthing
                ? "border-edit-live caret-edit-live"
                : "border-border-subtle focus:border-edit-live focus:caret-edit-live",
            )}
            placeholder="Describe what this step should do…"
          />
          <div className="mt-2 flex items-center justify-between">
            <span className="text-caption text-fg-tertiary">
              ⌘↵ resynthesise · ⌘S save
            </span>
            <div className="flex gap-2">
              <button
                disabled={unchanged || resynthing}
                onClick={() => resynth.mutate({ intent })}
                className={clsx(
                  "inline-flex h-8 items-center gap-2 rounded-sm border px-3 font-mono text-label",
                  unchanged || resynthing
                    ? "border-border-subtle text-fg-tertiary"
                    : "border-edit-live/50 text-edit-live hover:bg-edit-live/10",
                )}
              >
                <Wand2 size={12} strokeWidth={1.5} />
                {resynthing ? "synthesising…" : "resynth"}
              </button>
            </div>
          </div>
        </Section>

        {resynth.error && (
          <Section title="Error">
            <div className="text-label text-danger">
              {(resynth.error as Error).message}
            </div>
          </Section>
        )}

        {reasoning && (
          <Section title="Claude's reasoning">
            <div className="rounded-sm border border-border-subtle bg-bg-raised px-3 py-2 text-label text-fg-secondary">
              {reasoning}
            </div>
          </Section>
        )}

        <Section title="Synthesised fields">
          {/* Resynth shimmer: thin cinder sweep while Claude re-synthesises.
              Without this, the 700–1500ms wait reads as dead UI on video. */}
          {resynthing && (
            <div className="relative mb-3 h-[1px] overflow-hidden bg-border-subtle">
              <div className="absolute inset-y-0 left-0 w-1/3 animate-sweep-x bg-accent" />
            </div>
          )}
          <FieldRow
            label="action"
            current={step.action}
            proposed={pendingStep?.action}
          />
          <FieldRow
            label="aria_role"
            current={step.aria_role}
            proposed={pendingStep?.aria_role}
          />
          <FieldRow
            label="aria_name"
            current={step.aria_name}
            proposed={pendingStep?.aria_name}
          />
          <FieldRow
            label="value_template"
            current={step.value_template}
            proposed={pendingStep?.value_template}
          />
          <FieldRow
            label="success_check"
            current={step.success_check}
            proposed={pendingStep?.success_check}
          />
          <FieldRow
            label="grounding_hint"
            current={step.grounding_hint}
            proposed={pendingStep?.grounding_hint}
          />
          <FieldRow
            label="requires_confirmation"
            current={String(step.requires_confirmation)}
            proposed={
              pendingStep ? String(pendingStep.requires_confirmation) : undefined
            }
          />
        </Section>

        {pendingStep && (
          <div className="mt-6 flex gap-2">
            <button
              onClick={() => apply.mutate({ intent })}
              disabled={apply.isPending}
              className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md bg-accent px-4 font-medium text-bg-base hover:bg-accent-hover disabled:opacity-50"
            >
              {apply.isPending ? "saving…" : "accept"}
            </button>
            <button
              onClick={() => {
                setPendingStep(null);
                setReasoning(null);
                setIntent(step.intent);
              }}
              className="inline-flex h-9 items-center justify-center rounded-md border border-border px-4 text-fg-secondary hover:text-fg-primary"
            >
              revert
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-5">
      <h3 className="mb-2 text-head font-medium uppercase text-fg-tertiary">
        {title}
      </h3>
      {children}
    </section>
  );
}

function FieldRow({
  label,
  current,
  proposed,
}: {
  label: string;
  current: string | null | undefined;
  proposed?: string | null;
}) {
  const changed =
    proposed !== undefined && (proposed ?? "") !== (current ?? "");
  return (
    <div
      className={clsx(
        "grid grid-cols-[140px_1fr] gap-3 py-2 font-mono text-label",
        changed ? "animate-flash-live rounded-sm" : "",
      )}
    >
      <div className="text-fg-tertiary">{label}</div>
      <div className="min-w-0">
        {changed ? (
          <div className="flex flex-col gap-1">
            <span className="text-fg-tertiary line-through">
              {current ?? "—"}
            </span>
            <span className="text-edit-live">{proposed ?? "—"}</span>
          </div>
        ) : (
          <span className="truncate text-fg-primary">{current ?? "—"}</span>
        )}
      </div>
    </div>
  );
}
