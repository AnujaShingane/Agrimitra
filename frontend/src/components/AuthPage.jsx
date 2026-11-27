import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Sprout } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

export default function AuthPage({ mode }) {
  const isSignup = mode === 'signup';
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [googleSubmitting, setGoogleSubmitting] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(Boolean(googleClientId));
  const [googleUnavailable, setGoogleUnavailable] = useState(!googleClientId);
  const [error, setError] = useState('');
  const googleButtonRef = useRef(null);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const container = googleButtonRef.current;
    if (!container) return undefined;
    if (!googleClientId) return undefined;

    let active = true;

    const initializeGoogle = () => {
      if (!active) return;
      if (!window.google?.accounts?.id) {
        setGoogleLoading(false);
        setGoogleUnavailable(true);
        setError('Google sign-in could not load. Please try again later.');
        return;
      }
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: async ({ credential }) => {
          if (!active || !credential) return;
          setError('');
          setGoogleSubmitting(true);
          try {
            const response = await fetch('/api/auth/google', {
              method: 'POST',
              credentials: 'same-origin',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ credential }),
            });
            let data;
            try {
              data = await response.json();
            } catch {
              data = {};
            }
            if (!response.ok) {
              throw new Error(
                typeof data.detail === 'string'
                  ? data.detail
                  : 'Google sign-in could not be completed. Please try again.',
              );
            }
            navigate(location.state?.from?.pathname || '/app', { replace: true });
          } catch (requestError) {
            setError(requestError.message || 'Could not connect to AgriMitra. Please try again.');
          } finally {
            if (active) setGoogleSubmitting(false);
          }
        },
      });
      window.google.accounts.id.renderButton(container, {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        shape: 'rectangular',
        width: Math.min(372, Math.max(220, Math.floor(container.getBoundingClientRect().width))),
      });
    };

    const existingScript = document.querySelector('#google-identity-services');
    let script = existingScript;
    let handleScriptLoad;
    if (window.google?.accounts?.id) {
      initializeGoogle();
      queueMicrotask(() => {
        if (active) setGoogleLoading(false);
      });
    } else {
      if (!script) {
        script = document.createElement('script');
        script.id = 'google-identity-services';
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
      }
      handleScriptLoad = () => {
        initializeGoogle();
        if (active) setGoogleLoading(false);
      };
      script.addEventListener('load', handleScriptLoad);
      script.addEventListener('error', () => {
        if (active) {
          setGoogleLoading(false);
          setGoogleUnavailable(true);
          setError('Google sign-in could not load. Please try again later.');
        }
      }, { once: true });
    }

    return () => {
      active = false;
      if (handleScriptLoad) script?.removeEventListener('load', handleScriptLoad);
    };
  }, [googleClientId, location.state?.from?.pathname, navigate]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');

    if (isSignup && password !== confirmPassword) {
      setError('Your passwords do not match.');
      return;
    }

    setSubmitting(true);

    try {
      const response = await fetch(`/api/auth/${isSignup ? 'signup' : 'login'}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...(isSignup ? { full_name: fullName.trim() } : {}),
          email: email.trim(),
          password,
        }),
      });

      let data;
      try {
        data = await response.json();
      } catch {
        data = {};
      }

      if (!response.ok) {
        const detail = typeof data.detail === 'string'
          ? data.detail
          : 'We could not complete your request. Please try again.';
        throw new Error(detail);
      }

      navigate(location.state?.from?.pathname || '/app', { replace: true });
    } catch (requestError) {
      setError(requestError.message || 'Could not connect to AgriMitra. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <Link to="/" className="auth-back"><ArrowLeft size={17} /> Back to home</Link>
      <section className="auth-card">
        <div className="landing-brand auth-brand">
          <span className="brand-mark"><Sprout size={23} /></span>
          <span>AgriMitra<span className="brand-ai"> AI</span></span>
        </div>
        <h1>{isSignup ? 'Create your account' : 'Log in to your account'}</h1>
        <p className="auth-intro">
          {isSignup
            ? 'A more helpful farming day starts here.'
            : 'Your farming companion is ready when you are.'}
        </p>

        <div className="google-signin">
          <div
            ref={googleButtonRef}
            className={googleSubmitting ? 'google-signin-button is-disabled' : 'google-signin-button'}
            aria-busy={googleSubmitting}
          />
          {googleLoading && <span className="google-signin-status">Loading Google sign-in…</span>}
          {googleSubmitting && <span className="google-signin-status">Signing in with Google…</span>}
          {googleUnavailable && !googleLoading && (
            <span className="google-signin-status">
              Google sign-in is unavailable. Configure the Google Client ID and reload.
            </span>
          )}
        </div>
        <div className="auth-divider"><span>or continue with email</span></div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {isSignup && (
            <>
              <label htmlFor="auth-full-name">Full name</label>
              <input
                id="auth-full-name"
                type="text"
                autoComplete="name"
                minLength={2}
                maxLength={100}
                required
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Your name"
              />
            </>
          )}
          <label htmlFor="auth-email">Email address</label>
          <input
            id="auth-email"
            type="email"
            autoComplete="email"
            maxLength={254}
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
          />
          <label htmlFor="auth-password">Password</label>
          <input
            id="auth-password"
            type="password"
            autoComplete={isSignup ? 'new-password' : 'current-password'}
            minLength={8}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={isSignup ? 'At least 8 characters' : 'Enter your password'}
          />
          {isSignup && (
            <>
              <label htmlFor="auth-confirm-password">Confirm password</label>
              <input
                id="auth-confirm-password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                required
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="Enter your password again"
              />
            </>
          )}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="button button-primary auth-submit" type="submit" disabled={submitting || googleSubmitting}>
            {submitting ? 'Please wait…' : isSignup ? 'Create account' : 'Log in'}
            {!submitting && <ArrowRight size={17} />}
          </button>
        </form>

        <p className="auth-switch">
          {isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
          <Link to={isSignup ? '/login' : '/signup'}>{isSignup ? 'Log in' : 'Create an account'}</Link>
        </p>
        <p className="auth-note"><Sprout size={15} /> Your account helps keep your AgriMitra experience yours.</p>
      </section>
    </main>
  );
}
