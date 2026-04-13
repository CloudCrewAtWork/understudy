import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ReactFlow,
  Background,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ArrowLeft, Play } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import { StepNode } from "../components/StepNode";
import { StepEditor } from "../components/StepEditor";
import type { Recipe, RecipeStep } from "../lib/types";

const NODE_TYPES: NodeTypes = { step: StepNode };

export function RecipeGraph({
  recipeId,
  onBack,
}: {
  recipeId: string;
  onBack: () => void;
}) {
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

  const { data: recipe, isLoading, error } = useQuery<Recipe>({
    queryKey: ["recipe", recipeId],
    queryFn: () => api.getRecipe(recipeId),
  });

  const selected: RecipeStep | null = useMemo(() => {
    if (!recipe || selectedIdx === null) return null;
    return recipe.steps.find((s) => s.idx === selectedIdx) ?? null;
  }, [recipe, selectedIdx]);

  const referencedParamsByStep = useMemo(() => {
    const out = new Map<number, string[]>();
    if (!recipe) return out;
    for (const step of recipe.steps) {
      const refs = extractParamRefs(step);
      out.set(step.idx, refs);
    }
    return out;
  }, [recipe]);

  const highlightedParams = useMemo(() => {
    if (!selected) return new Set<string>();
    return new Set(referencedParamsByStep.get(selected.idx) ?? []);
  }, [selected, referencedParamsByStep]);

  const { nodes, edges } = useMemo(() => {
    if (!recipe) return { nodes: [] as Node[], edges: [] as Edge[] };
    const sortedSteps = [...recipe.steps].sort((a, b) => a.idx - b.idx);
    const ns: Node[] = sortedSteps.map((step, i) => ({
      id: String(step.idx),
      type: "step",
      position: { x: 0, y: i * 140 },
      data: {
        step,
        selected: selectedIdx === step.idx,
        referencedParams: referencedParamsByStep.get(step.idx) ?? [],
        onClick: setSelectedIdx,
      },
      draggable: false,
      selectable: false,
    }));
    const es: Edge[] = [];
    for (let i = 0; i < sortedSteps.length - 1; i++) {
      es.push({
        id: `e-${sortedSteps[i].idx}-${sortedSteps[i + 1].idx}`,
        source: String(sortedSteps[i].idx),
        target: String(sortedSteps[i + 1].idx),
        type: "smoothstep",
      });
    }
    return { nodes: ns, edges: es };
  }, [recipe, selectedIdx, referencedParamsByStep]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-body text-fg-secondary">
        loading recipe…
      </div>
    );
  }
  if (error || !recipe) {
    return (
      <div className="flex h-full items-center justify-center text-body text-danger">
        {(error as Error | undefined)?.message ?? "recipe not found"}
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border-subtle bg-bg-base px-5">
        <div className="flex min-w-0 items-center gap-3">
          <button
            onClick={onBack}
            className="rounded-sm p-1 text-fg-tertiary hover:bg-bg-pressed hover:text-fg-primary"
            aria-label="Back"
          >
            <ArrowLeft size={16} />
          </button>
          <span className="text-body font-medium text-fg-primary">
            {recipe.task_name}
          </span>
          <span className="flex h-5 items-center rounded-xs border border-border bg-bg-raised px-1.5 font-mono text-caption text-fg-tertiary">
            task · {recipe.steps.length} step{recipe.steps.length === 1 ? "" : "s"}
          </span>
        </div>
        <RunButton />
      </header>

      <div className="flex flex-1 overflow-hidden">
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <ParamsBar recipe={recipe} highlighted={highlightedParams} />

          <div className="relative flex-1">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              fitView
              fitViewOptions={{ padding: 0.15, maxZoom: 1, minZoom: 0.6 }}
              proOptions={{ hideAttribution: true }}
              panOnDrag
              panOnScroll
              zoomOnScroll={false}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
            >
              <Background color="#1B1D22" gap={24} size={1} />
            </ReactFlow>
          </div>
        </main>

        {selected && (
          <StepEditor
            recipeId={recipe.id}
            step={selected}
            onClose={() => setSelectedIdx(null)}
          />
        )}
      </div>
    </div>
  );
}

function ParamsBar({
  recipe,
  highlighted,
}: {
  recipe: Recipe;
  highlighted: Set<string>;
}) {
  if (recipe.params.length === 0) return null;
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-border-subtle bg-bg-base px-5 py-2">
      <span className="font-mono text-caption uppercase tracking-wider text-fg-tertiary">
        params
      </span>
      <div className="flex flex-wrap gap-1.5">
        {recipe.params.map((p) => (
          <span
            key={p.name}
            className={clsx(
              "inline-flex h-[22px] items-center rounded-xs border bg-bg-pressed px-2 font-mono text-label",
              paramColor(p.type),
              highlighted.has(p.name)
                ? "ring-1 ring-edit-live"
                : "border-border-subtle",
            )}
          >
            <span className="text-fg-primary">{p.name}</span>
            <span className="ml-1.5 text-fg-tertiary">· {p.type}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function RunButton() {
  return (
    <button
      disabled
      className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-4 font-medium text-bg-base hover:bg-accent-hover disabled:opacity-60"
      title="Run from CLI: understudy replay"
    >
      <Play size={14} strokeWidth={2} />
      Run
      <span className="font-mono text-caption opacity-60">CLI</span>
    </button>
  );
}

function paramColor(type: string): string {
  switch (type) {
    case "number":
      return "text-sky-300";
    case "boolean":
      return "text-violet-300";
    case "email":
      return "text-rose-300";
    case "url":
      return "text-accent";
    case "csv_path":
      return "text-emerald-300";
    default:
      return "text-fg-secondary";
  }
}

function extractParamRefs(step: RecipeStep): string[] {
  const sources = [
    step.intent,
    step.value_template,
    step.success_check,
    step.aria_name,
    step.grounding_hint,
  ];
  const refs = new Set<string>();
  const re = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g;
  for (const src of sources) {
    if (!src) continue;
    for (const m of src.matchAll(re)) refs.add(m[1]);
  }
  return [...refs];
}
