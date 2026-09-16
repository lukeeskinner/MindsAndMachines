import { useEffect, useState } from "react";
import { App } from "./App";
import {
  clearAuthSession,
  readAuthSession,
  type AuthSession,
} from "./auth/cognito";
import { AuthScreen } from "./components/auth/AuthScreen";
import { Onboarding } from "./components/onboarding/Onboarding";
import { initialDraft } from "./components/onboarding/model";

type Route = "login" | "setup" | "study";

function routeFromHash(authenticated: boolean): Route {
  if (window.location.hash === "#/study")
    return authenticated ? "study" : "login";
  if (window.location.hash === "#/setup")
    return authenticated ? "setup" : "login";
  return authenticated ? "setup" : "login";
}

// Setup data and selected File handles stay in this tab; learning state remains API-owned.
export function RootApp() {
  const [draft, setDraft] = useState(initialDraft);
  const [auth, setAuth] = useState<AuthSession | null>(() => readAuthSession());
  const [route, setRoute] = useState<Route>(() => routeFromHash(!!auth));
  const [visitedStudy, setVisitedStudy] = useState(route === "study");
  useEffect(() => {
    const update = () => {
      // In-page accessibility anchors must not change the active screen.
      if (!["", "#/login", "#/study", "#/setup"].includes(window.location.hash))
        return;
      const next = routeFromHash(!!auth);
      if (next === "study") setVisitedStudy(true);
      setRoute(next);
      window.scrollTo({ top: 0, behavior: "instant" });
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, [auth]);
  function navigate(next: Route) {
    if (!auth && next !== "login") next = "login";
    if (next === "study") setVisitedStudy(true);
    setRoute(next);
    window.location.hash = `/${next}`;
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  function handleAuthenticated(session: AuthSession) {
    setAuth(session);
    setRoute("setup");
    window.location.hash = "/setup";
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  function handleSignOut() {
    clearAuthSession();
    setAuth(null);
    setDraft(initialDraft());
    setVisitedStudy(false);
    navigate("login");
  }
  return (
    <>
      {route === "login" && (
        <AuthScreen onAuthenticated={handleAuthenticated} />
      )}
      {auth && route === "setup" && (
        <Onboarding
          draft={draft}
          onChange={setDraft}
          onContinue={() => navigate("study")}
          onSignOut={handleSignOut}
          signedInEmail={auth.email}
        />
      )}
      {auth && visitedStudy && (
        <div hidden={route !== "study"}>
          <App
            onEditSetup={() => navigate("setup")}
            course={{ draft, onChange: setDraft }}
          />
        </div>
      )}
    </>
  );
}
