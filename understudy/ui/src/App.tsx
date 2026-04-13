import { useState } from "react";
import { RecipeList } from "./routes/RecipeList";
import { RecipeGraph } from "./routes/RecipeGraph";

export default function App() {
  // Minimal "router": we just track the selected recipe id.
  // Reloads reset via URL query param.
  const [recipeId, setRecipeId] = useState<string | null>(() => {
    return new URLSearchParams(window.location.search).get("r");
  });

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      {recipeId ? (
        <RecipeGraph
          recipeId={recipeId}
          onBack={() => {
            setRecipeId(null);
            const url = new URL(window.location.href);
            url.searchParams.delete("r");
            window.history.replaceState({}, "", url.toString());
          }}
        />
      ) : (
        <RecipeList
          onOpen={(id) => {
            setRecipeId(id);
            const url = new URL(window.location.href);
            url.searchParams.set("r", id);
            window.history.replaceState({}, "", url.toString());
          }}
        />
      )}
    </div>
  );
}
