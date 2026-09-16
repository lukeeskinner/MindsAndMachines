const AUTH_KEY = "minds-machines-auth";

export type AuthSession = {
  email: string;
  signedInAt: string;
};

export function readAuthSession(): AuthSession | null {
  try {
    const raw = window.sessionStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (!parsed.email || !parsed.signedInAt) return null;
    return { email: parsed.email, signedInAt: parsed.signedInAt };
  } catch {
    return null;
  }
}

export function saveAuthSession(email: string): AuthSession {
  const session = {
    email: email.trim().toLowerCase(),
    signedInAt: new Date().toISOString(),
  };
  window.sessionStorage.setItem(AUTH_KEY, JSON.stringify(session));
  return session;
}

export function clearAuthSession() {
  window.sessionStorage.removeItem(AUTH_KEY);
}

export function cognitoHostedUiUrl(): string | null {
  const domain = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined;
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;
  if (!domain || !clientId) return null;
  const redirectUri =
    (import.meta.env.VITE_COGNITO_REDIRECT_URI as string | undefined) ||
    `${window.location.origin}${window.location.pathname}#/setup`;
  const normalizedDomain = domain.startsWith("http")
    ? domain
    : `https://${domain}`;
  const params = new URLSearchParams({
    client_id: clientId,
    response_type: "code",
    scope: "openid email profile",
    redirect_uri: redirectUri,
  });
  return `${normalizedDomain.replace(/\/$/, "")}/login?${params.toString()}`;
}
