import { useEffect, useState } from "react";
import { App } from "./App";
import { Onboarding } from "./components/onboarding/Onboarding";
import { initialDraft } from "./components/onboarding/model";

// Setup data and selected File handles stay in this tab; learning state remains API-owned.
export function RootApp() {
  const [draft, setDraft] = useState(initialDraft);
  const [route, setRoute] = useState(() =>
    window.location.hash === "#/study" ? "study" : "setup",
  );
  const [visitedStudy, setVisitedStudy] = useState(route === "study");
  useEffect(() => {
    const update = () => {
      // In-page accessibility anchors must not change the active screen.
      if (!["", "#/study", "#/setup"].includes(window.location.hash)) return;
      const next = window.location.hash === "#/study" ? "study" : "setup";
      if (next === "study") setVisitedStudy(true);
      setRoute(next);
      window.scrollTo({ top: 0, behavior: "instant" });
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  function navigate(next: "study" | "setup") {
    if (next === "study") setVisitedStudy(true);
    setRoute(next);
    window.location.hash = `/${next}`;
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  return (
    <>
      {route === "setup" && (
        <Onboarding
          draft={draft}
          onChange={setDraft}
          onContinue={() => navigate("study")}
        />
      )}
      {visitedStudy && (
        <div hidden={route !== "study"}>
          <App onEditSetup={() => navigate("setup")} />
        </div>
      )}
    </>
  );
}
