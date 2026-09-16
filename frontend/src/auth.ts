// Cognito Hosted UI sign-in (Authorization Code + PKCE). No SDK dependency:
// plain redirects plus the browser's Web Crypto API. Inert until
// VITE_COGNITO_DOMAIN and VITE_COGNITO_CLIENT_ID are configured, so the
// anonymous demo session (main.tsx) keeps working unchanged either way.

const domain = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined;
const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;
const ID_TOKEN_KEY = 'mm_id_token';
const VERIFIER_KEY = 'mm_pkce_verifier';

export const authConfigured = Boolean(domain && clientId);

function redirectUri(): string {
  return window.location.origin + '/';
}

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function pkcePair(): Promise<{ verifier: string; challenge: string }> {
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return { verifier, challenge: base64url(new Uint8Array(digest)) };
}

export async function signIn(): Promise<void> {
  if (!domain || !clientId) return;
  const { verifier, challenge } = await pkcePair();
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  const params = new URLSearchParams({
    client_id: clientId, response_type: 'code', scope: 'openid email',
    redirect_uri: redirectUri(), code_challenge: challenge, code_challenge_method: 'S256',
  });
  window.location.assign(`https://${domain}/login?${params}`);
}

export function signOut(): void {
  sessionStorage.removeItem(ID_TOKEN_KEY);
  if (!domain || !clientId) return;
  const params = new URLSearchParams({ client_id: clientId, logout_uri: redirectUri() });
  window.location.assign(`https://${domain}/logout?${params}`);
}

export function getIdToken(): string | null {
  return sessionStorage.getItem(ID_TOKEN_KEY);
}

// Call once on app load: exchanges ?code=... from the Hosted UI redirect for
// tokens, stores the ID token, and cleans the URL. No-op on any other load.
export async function completeSignInRedirect(): Promise<void> {
  const url = new URL(window.location.href);
  const code = url.searchParams.get('code');
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  if (!code || !verifier || !domain || !clientId) return;
  sessionStorage.removeItem(VERIFIER_KEY);
  const body = new URLSearchParams({
    grant_type: 'authorization_code', client_id: clientId, code,
    redirect_uri: redirectUri(), code_verifier: verifier,
  });
  const response = await fetch(`https://${domain}/oauth2/token`, {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body,
  });
  if (response.ok) {
    const tokens = await response.json();
    sessionStorage.setItem(ID_TOKEN_KEY, tokens.id_token);
  }
  url.searchParams.delete('code');
  url.searchParams.delete('state');
  window.history.replaceState({}, '', url);
}
