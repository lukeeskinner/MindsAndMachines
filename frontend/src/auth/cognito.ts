// Cognito Hosted UI sign-in (Authorization Code + PKCE), no SDK dependency.
// AuthScreen's local email/password form is an explicit demo-only
// placeholder ("Live account sign-in is not connected in this demo") and
// never produces an idToken, so the backend treats it as anonymous. The
// "Open Cognito hosted sign-in" path below is the real one: it completes
// the redirect, exchanges the code for tokens and reaches the backend as a
// verified Cognito user.

const AUTH_KEY = "minds-machines-auth";
const VERIFIER_KEY = "minds-machines-pkce-verifier";

export type AuthSession = {
  email: string;
  signedInAt: string;
  idToken?: string;
};

function config(): { domain: string; clientId: string } | null {
  const domain = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined;
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;
  if (!domain || !clientId) return null;
  return { domain: (domain.startsWith("http") ? domain : `https://${domain}`).replace(/\/$/, ""), clientId };
}

function redirectUri(): string {
  // Must exactly match a callback URL registered on the Cognito app client
  // (no hash fragment: Cognito compares the literal redirect_uri string).
  return (
    (import.meta.env.VITE_COGNITO_REDIRECT_URI as string | undefined) ||
    `${window.location.origin}${window.location.pathname}`
  );
}

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function pkcePair(): Promise<{ verifier: string; challenge: string }> {
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return { verifier, challenge: base64url(new Uint8Array(digest)) };
}

export function readAuthSession(): AuthSession | null {
  try {
    const raw = window.sessionStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (!parsed.email || !parsed.signedInAt) return null;
    return { email: parsed.email, signedInAt: parsed.signedInAt, idToken: parsed.idToken };
  } catch {
    return null;
  }
}

function writeAuthSession(session: AuthSession): AuthSession {
  window.sessionStorage.setItem(AUTH_KEY, JSON.stringify(session));
  return session;
}

// Demo-only local sign-in: no real credential check. Never sets an
// idToken, so getIdToken() stays null and sessions remain anonymous.
export function saveAuthSession(email: string): AuthSession {
  return writeAuthSession({ email: email.trim().toLowerCase(), signedInAt: new Date().toISOString() });
}

export function clearAuthSession() {
  window.sessionStorage.removeItem(AUTH_KEY);
  window.sessionStorage.removeItem(VERIFIER_KEY);
}

export function getIdToken(): string | null {
  return readAuthSession()?.idToken ?? null;
}

export function cognitoHostedUiAvailable(): boolean {
  return config() !== null;
}

// Redirects to the real Cognito Hosted UI. Only call when cognitoHostedUiAvailable().
export async function startHostedSignIn(): Promise<void> {
  const cfg = config();
  if (!cfg) return;
  const { verifier, challenge } = await pkcePair();
  window.sessionStorage.setItem(VERIFIER_KEY, verifier);
  const params = new URLSearchParams({
    client_id: cfg.clientId, response_type: "code", scope: "openid email",
    redirect_uri: redirectUri(), code_challenge: challenge, code_challenge_method: "S256",
  });
  window.location.assign(`${cfg.domain}/login?${params}`);
}

// Call once on app load: exchanges ?code=... from the Hosted UI redirect for
// a real, verified session. Returns null (no-op) on any other load, so it's
// safe to always call.
export async function completeHostedSignIn(): Promise<AuthSession | null> {
  const cfg = config();
  const url = new URL(window.location.href);
  const code = url.searchParams.get("code");
  const verifier = window.sessionStorage.getItem(VERIFIER_KEY);
  if (!code || !verifier || !cfg) return null;
  window.sessionStorage.removeItem(VERIFIER_KEY);
  const body = new URLSearchParams({
    grant_type: "authorization_code", client_id: cfg.clientId, code,
    redirect_uri: redirectUri(), code_verifier: verifier,
  });
  const response = await fetch(`${cfg.domain}/oauth2/token`, {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body,
  });
  url.searchParams.delete("code");
  url.searchParams.delete("state");
  window.history.replaceState({}, "", url);
  if (!response.ok) return null;
  const tokens = await response.json();
  const claims = JSON.parse(atob(tokens.id_token.split(".")[1])) as { email?: string; sub: string };
  return writeAuthSession({
    email: claims.email ?? claims.sub,
    signedInAt: new Date().toISOString(),
    idToken: tokens.id_token,
  });
}
