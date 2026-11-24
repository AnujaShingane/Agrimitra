import { useState } from 'react';
import { ArrowLeft, ArrowRight, Sprout } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

export default function AuthPage({ mode }) {
  const isSignup = mode === 'signup';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const location = useLocation();
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const response = await fetch(`/api/auth/${isSignup ? 'signup' : 'login'}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'We could not complete your request. Please try again.');
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
        <Link className="landing-brand auth-brand" to="/">
          <span className="brand-mark"><Sprout size={23} /></span>
          <span>AgriMitra<span className="brand-ai"> AI</span></span>
        </Link>
        <span className="section-kicker">{isSignup ? 'WELCOME TO AGRIMITRA' : 'WELCOME BACK'}</span>
        <h1>{isSignup ? 'Create your account' : 'Log in to your account'}</h1>
        <p className="auth-intro">
          {isSignup
            ? 'A more helpful farming day starts here.'
            : 'Your farming companion is ready when you are.'}
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
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
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="button button-primary auth-submit" type="submit" disabled={submitting}>
            {submitting ? 'Please wait…' : isSignup ? 'Create account' : 'Log in'}
            {!submitting && <ArrowRight size={17} />}
          </button>
        </form>

        <p className="auth-switch">
          {isSignup ? 'Already have an account?' : 'New to AgriMitra?'}{' '}
          <Link to={isSignup ? '/login' : '/signup'}>{isSignup ? 'Log in' : 'Create an account'}</Link>
        </p>
        <p className="auth-note"><Sprout size={15} /> Your account helps keep your AgriMitra experience yours.</p>
      </section>
    </main>
  );
}
