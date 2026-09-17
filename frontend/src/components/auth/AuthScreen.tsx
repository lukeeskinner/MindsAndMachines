import { useMemo, useRef, useState, type FormEvent } from "react";
import { MotionConfig } from "motion/react";
import {
  ArrowRight,
  KeyRound,
  LockKeyhole,
  Mail,
} from "lucide-react";
import cognitoLogo from "../../assets/amazon-cognito.png";
import { cognitoHostedUiAvailable, saveAuthSession, startHostedSignIn, type AuthSession } from "../../auth/cognito";
import { BrandWordmark } from "../brand/Brand";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Scene } from "../ui/primitives";
import { LoginArtwork } from "./LoginArtwork";

type AuthErrors = Partial<Record<"email" | "password", string>>;

function validate(email: string, password: string) {
  const errors: AuthErrors = {};
  if (!email.trim()) errors.email = "Enter your email.";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
    errors.email = "Use a valid email address.";
  if (!password) errors.password = "Enter your password.";
  else if (password.length < 8)
    errors.password = "Use at least 8 characters.";
  return errors;
}

export function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (session: AuthSession) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<AuthErrors>({});
  const emailField = useRef<HTMLInputElement>(null);
  const passwordField = useRef<HTMLInputElement>(null);
  const hostedUiAvailable = useMemo(() => cognitoHostedUiAvailable(), []);

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors = validate(email, password);
    setErrors(nextErrors);
    if (nextErrors.email) {
      emailField.current?.focus();
      return;
    }
    if (nextErrors.password) {
      passwordField.current?.focus();
      return;
    }
    onAuthenticated(saveAuthSession(email));
  }

  return (
    <MotionConfig reducedMotion="user">
      <main className="auth-shell">
        <section className="auth-panel" aria-labelledby="login-title">
          <Scene className="auth-card">
            <div className="auth-header">
              <BrandWordmark className="auth-brand" />
            </div>
            <h1 id="login-title" className="auth-heading">
              Sign in to your study workspace.
            </h1>
            {hostedUiAvailable ? (
              <>
                <p className="auth-intro">
                  Sign in with your real account through Amazon Cognito.
                </p>
                <div className="auth-provider">
                  <img className="auth-cognito-logo" src={cognitoLogo}
                    alt="Amazon Cognito" width={1280} height={720} />
                  <span>Account sign-in<small>Continue to your learning workspace.</small></span>
                </div>
                <Button
                  variant="secondary"
                  className="auth-hosted"
                  onClick={() => void startHostedSignIn()}
                >
                  Continue with Cognito sign-in
                  <ArrowRight size={16} />
                </Button>
              </>
            ) : (
              <>
                <p className="auth-intro">
                  Preview your course setup and study workspace. Live account
                  sign-in is not connected in this demo.
                </p>
                <form className="auth-form" onSubmit={submit} noValidate>
                  <div>
                    <label className="auth-label" htmlFor="email">
                      Email
                    </label>
                    <div className="auth-input-wrap">
                      <Mail size={17} aria-hidden="true" />
                      <Input
                        ref={emailField}
                        className="bg-surface pl-11"
                        id="email"
                        name="email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(event) => {
                          setEmail(event.target.value);
                          if (errors.email)
                            setErrors((previous) => ({
                              ...previous,
                              email: undefined,
                            }));
                        }}
                        aria-invalid={!!errors.email}
                        aria-describedby={errors.email ? "email-error" : undefined}
                        placeholder="you@example.com"
                      />
                    </div>
                    {errors.email && (
                      <p className="auth-error" id="email-error">
                        {errors.email}
                      </p>
                    )}
                  </div>
                  <div>
                    <label className="auth-label" htmlFor="password">
                      Password
                    </label>
                    <div className="auth-input-wrap">
                      <KeyRound size={17} aria-hidden="true" />
                      <Input
                        ref={passwordField}
                        className="bg-surface pl-11"
                        id="password"
                        name="password"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => {
                          setPassword(event.target.value);
                          if (errors.password)
                            setErrors((previous) => ({
                              ...previous,
                              password: undefined,
                            }));
                        }}
                        aria-invalid={!!errors.password}
                        aria-describedby={
                          errors.password ? "password-error" : undefined
                        }
                        placeholder="8+ characters"
                      />
                    </div>
                    {errors.password && (
                      <p className="auth-error" id="password-error">
                        {errors.password}
                      </p>
                    )}
                  </div>
                  <Button type="submit" className="auth-submit">
                    Continue to setup
                    <ArrowRight size={16} />
                  </Button>
                </form>
                <div className="auth-local-note" role="status">
                  <LockKeyhole size={15} />
                  <span>Demo access only. Use a sample email and password.</span>
                </div>
              </>
            )}
          </Scene>
        </section>
        <aside className="auth-context" aria-label="Study workspace preview">
          <div className="auth-context-header">
            <span>A SPACE TO MAKE IT CLICK</span>
            <span className="auth-art-index" aria-hidden="true">M / M</span>
          </div>
          <LoginArtwork />
          <div className="auth-art-caption">
            <span className="auth-art-eyebrow">CURIOSITY, IN MOTION</span>
            <h2>Small steps.<br />Clearer connections.</h2>
            <p>A question, an explanation, a new perspective.<br />Make a little room for learning.</p>
          </div>
        </aside>
      </main>
    </MotionConfig>
  );
}
