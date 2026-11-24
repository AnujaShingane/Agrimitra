import { ArrowRight, Sprout } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function LandingPage() {
  return (
    <main className="landing-page">
      <div className="landing-photo" aria-hidden="true" />
      <div className="landing-wash" aria-hidden="true" />
      <header className="landing-nav">
        <Link className="landing-brand" to="/" aria-label="AgriMitra home">
          <span className="brand-mark"><Sprout size={24} /></span>
          <span>AgriMitra<span className="brand-ai"> AI</span></span>
        </Link>
        <nav className="landing-actions" aria-label="Account navigation">
          <Link className="landing-login" to="/login">Log in</Link>
          <Link className="button button-primary nav-signup" to="/signup">
            Sign up <ArrowRight size={16} />
          </Link>
        </nav>
      </header>

      <section className="landing-hero">
        <div className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-dot" /> YOUR FARM. YOUR FUTURE.</div>
          <h1>Grow smarter.<br /><span>Thrive together.</span></h1>
          <p className="hero-description">
            Farming is full of big decisions. Get trusted guidance on your crops,
            weather, markets, and more — right when you need it.
          </p>
          <div className="hero-buttons">
            <Link className="button button-primary button-large" to="/signup">
              Get started <ArrowRight size={18} />
            </Link>
            <Link className="button button-quiet button-large" to="/login">I already have an account</Link>
          </div>
          <div className="hero-trust"><Sprout size={17} /> A helpful companion for every growing season</div>
        </div>
      </section>

      <div className="landing-caption">Tools and knowledge for the people who grow our food.</div>
    </main>
  );
}
