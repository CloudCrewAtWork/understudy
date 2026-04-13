// Wire-types that mirror the Pydantic models server-side.
// Keep in sync with understudy/types.py and understudy/server/schemas.py.

export type ActionType =
  | "nav"
  | "click"
  | "dblclick"
  | "type"
  | "key"
  | "scroll"
  | "wait"
  | "select"
  | "upload"
  | "note";

export type ParamType =
  | "string"
  | "number"
  | "boolean"
  | "csv_path"
  | "url"
  | "email";

export interface RecipeParam {
  name: string;
  type: ParamType;
  description: string;
  example: string | null;
  required: boolean;
}

export interface RecipeStep {
  idx: number;
  intent: string;
  action: ActionType;
  grounding_hint: string | null;
  aria_role: string | null;
  aria_name: string | null;
  value_template: string | null;
  success_check: string | null;
  requires_confirmation: boolean;
}

export interface Recipe {
  id: string;
  task_name: string;
  target_kind: "browser" | "macos";
  source_trajectory_id: string;
  induced_by: string;
  created_at: string;
  description: string;
  params: RecipeParam[];
  steps: RecipeStep[];
  safety_notes: string | null;
}

export interface RecipeSummary {
  id: string;
  task_name: string;
  description: string;
  created_at: string;
  edited_at: string | null;
  step_count: number;
  param_count: number;
}

export interface ResynthResponse {
  old_step: RecipeStep;
  new_step: RecipeStep;
  reasoning: string | null;
  applied: boolean;
  recipe: Recipe | null;
}
