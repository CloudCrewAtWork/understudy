import { Handle, Position } from "@xyflow/react";
import clsx from "clsx";
import {
  MousePointerClick,
  TextCursorInput,
  Navigation,
  Clock,
  CheckCheck,
  Keyboard,
  ArrowDownUp,
  FileUp,
  StickyNote,
} from "lucide-react";
import type { RecipeStep } from "../lib/types";

const ACTION_ICON: Record<string, typeof MousePointerClick> = {
  click: MousePointerClick,
  dblclick: MousePointerClick,
  type: TextCursorInput,
  nav: Navigation,
  wait: Clock,
  select: CheckCheck,
  key: Keyboard,
  scroll: ArrowDownUp,
  upload: FileUp,
  note: StickyNote,
};

export interface StepNodeData {
  step: RecipeStep;
  selected: boolean;
  referencedParams: string[];
  onClick: (idx: number) => void;
  executing?: boolean;
  justFailed?: boolean;
}

export function StepNode({ data }: { data: StepNodeData }) {
  const { step, selected, referencedParams, onClick, executing, justFailed } =
    data;
  const Icon = ACTION_ICON[step.action] ?? StickyNote;

  return (
    <button
      onClick={() => onClick(step.idx)}
      style={{ width: 320 }}
      className={clsx(
        "relative block rounded-md border bg-bg-raised text-left transition-colors",
        selected
          ? "border-border-emph"
          : "border-border-subtle hover:border-border",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ opacity: 0, pointerEvents: "none" }}
      />

      {/* Left accent bar */}
      <span
        aria-hidden
        className={clsx(
          "absolute left-0 top-0 h-full w-[2px] rounded-l-md transition-colors",
          executing
            ? "bg-edit-live"
            : justFailed
              ? "bg-danger"
              : step.requires_confirmation
                ? "bg-warn"
                : selected
                  ? "bg-accent"
                  : "bg-transparent",
        )}
      />

      {/* Selected ring (subtle orange inner) */}
      {selected && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-md ring-1 ring-accent/40"
        />
      )}

      {/* Executing sweep */}
      {executing && (
        <span className="pointer-events-none absolute inset-x-0 top-0 h-[1px] overflow-hidden">
          <span className="block h-full w-1/2 animate-sweep-x bg-edit-live" />
        </span>
      )}

      {/* Header: action id + idx */}
      <div className="flex items-center justify-between px-5 pt-3 pb-1">
        <div className="flex items-center gap-2 font-mono text-label text-fg-secondary">
          <Icon size={14} className="text-fg-tertiary" strokeWidth={1.5} />
          <span>{step.action}</span>
        </div>
        <span className="font-mono text-caption text-fg-tertiary">
          {String(step.idx).padStart(2, "0")}
        </span>
      </div>

      {/* Intent */}
      <div className="px-5 pb-4 pt-1">
        <div className="text-body text-fg-primary">
          <span className="line-clamp-2">{step.intent}</span>
        </div>

        {/* Target hint when present */}
        {(step.aria_role || step.aria_name) && (
          <div className="mt-2 font-mono text-caption text-fg-tertiary">
            {step.aria_role ?? "—"}
            {step.aria_name ? ` · "${step.aria_name}"` : ""}
          </div>
        )}

        {/* Param chips */}
        {referencedParams.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {referencedParams.map((p) => (
              <span
                key={p}
                className="inline-flex h-[22px] items-center rounded-xs border border-border bg-bg-pressed px-2 font-mono text-label text-fg-secondary"
              >
                {p}
              </span>
            ))}
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ opacity: 0, pointerEvents: "none" }}
      />
    </button>
  );
}
