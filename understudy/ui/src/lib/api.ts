import { CSRF_TOKEN } from "./csrf";
import type { Recipe, RecipeSummary, ResynthResponse } from "./types";

const BASE = "/api";

async function send<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const method = (init?.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    headers["X-Understudy-CSRF"] = CSRF_TOKEN;
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listRecipes: () => send<RecipeSummary[]>("/recipes"),
  getRecipe: (id: string) => send<Recipe>(`/recipes/${id}`),
  patchStep: (id: string, idx: number, body: Partial<import("./types").RecipeStep>) =>
    send<Recipe>(`/recipes/${id}/steps/${idx}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  resynthStep: (
    id: string,
    idx: number,
    new_intent: string,
    apply: boolean,
  ) =>
    send<ResynthResponse>(
      `/recipes/${id}/steps/${idx}/resynthesize`,
      {
        method: "POST",
        body: JSON.stringify({ new_intent, apply }),
      },
    ),
};
