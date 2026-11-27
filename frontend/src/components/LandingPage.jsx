import { useState } from 'react';
import {
  ArrowRight,
  BookOpen,
  Check,
  CloudSun,
  Landmark,
  Leaf,
  Menu,
  MessageCircle,
  ScanLine,
  ShieldCheck,
  Sprout,
  TrendingUp,
  Users,
  X,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import './landing.css';

const features = [
  {
    title: 'AI Farming Assistant',
    description: 'Ask about crop care, fertilizers, irrigation, pests and more.',
    icon: MessageCircle,
    path: '/app/chat',
    label: 'Ask AgriMitra',
  },
  {
    title: 'Leaf Disease Scanner',
    description: 'Explore possible plant diseases from a leaf photo, with careful guidance.',
    icon: ScanLine,
    path: '/app/scanner',
    label: 'Scan a leaf',
  },
  {
    title: 'Live Market Prices',
    description: 'Compare crop-wise mandi prices and relevant market information.',
    icon: TrendingUp,
    path: '/app/market',
    label: 'Check prices',
  },
  {
    title: 'Weather Updates',
    description: 'Check local weather information to better plan farm activities.',
    icon: CloudSun,
    path: '/app/weather',
    label: 'View weather',
  },
  {
    title: 'Government Schemes',
    description: 'Explore farmer schemes, benefits and application information.',
    icon: Landmark,
    path: '/app/schemes',
    label: 'Explore schemes',
  },
];

const navigationItems = [
  ['About', '/about'],
  ['Features', '/features'],
  ['How It Works', '/how-it-works'],
  ['Contact', '/contact'],
];

function Brand({ footer = false }) {
  return (
    <Link
      className={`public-brand${footer ? ' public-brand-footer' : ''}`}
      to="/"
      aria-label="AgriMitra home"
    >
      <span className="public-brand-icon"><Sprout size={22} strokeWidth={2.2} /></span>
      <span>AgriMitra</span>
    </Link>
  );
}

function Navigation() {
  const [menuOpen, setMenuOpen] = useState(false);

  function closeMenu() {
    setMenuOpen(false);
  }

  return (
    <header className="public-header">
      <div className="public-nav">
        <Brand />
        <button
          className="public-menu-toggle"
          type="button"
          aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={menuOpen}
          aria-controls="public-navigation"
          onClick={() => setMenuOpen((isOpen) => !isOpen)}
        >
          {menuOpen ? <X size={23} /> : <Menu size={23} />}
        </button>
        <nav
          id="public-navigation"
          className={`public-nav-links${menuOpen ? ' public-nav-links-open' : ''}`}
          aria-label="Main navigation"
        >
          <Link to="/" onClick={closeMenu}>Home</Link>
          {navigationItems.map(([label, path]) => (
            <Link key={path} to={path} onClick={closeMenu}>{label}</Link>
          ))}
          <div className="public-nav-mobile-actions">
            <Link to="/login" onClick={closeMenu}>Log In</Link>
            <Link className="public-button public-button-small" to="/signup" onClick={closeMenu}>
              Sign Up <ArrowRight size={15} />
            </Link>
          </div>
        </nav>
        <div className="public-nav-actions">
          <Link className="public-login-link" to="/login">Log In</Link>
          <Link className="public-button public-button-small" to="/signup">
            Sign Up <ArrowRight size={15} />
          </Link>
        </div>
      </div>
    </header>
  );
}

function AnimatedHeroWord({ word, startIndex }) {
  return (
    <span className="public-hero-word" aria-hidden="true">
      {Array.from(word).map((letter, index) => {
        const delay = (startIndex + index) * 65;
        return (
          <span
            className="public-hero-letter"
            key={`${letter}-${index}`}
            style={{
              '--letter-delay': `${delay}ms`,
              '--glitter-delay': `${delay + 500}ms`,
            }}
          >
            {letter}
          </span>
        );
      })}
    </span>
  );
}

function Hero({ onGetStarted, checkingSession, sessionError }) {
  return (
    <main className="public-hero" id="home" aria-labelledby="public-hero-title">
      <div className="public-hero-shade" aria-hidden="true" />
      <div className="public-hero-content">
        <h1 id="public-hero-title" aria-label="Growing Smarter, Farming Better.">
          <span className="public-hero-line">
            <AnimatedHeroWord word="Growing" startIndex={0} />{' '}
            <AnimatedHeroWord word="Smarter," startIndex={8} />
          </span>
          <br />
          <span className="public-hero-line public-hero-line-accent">
            <AnimatedHeroWord word="Farming" startIndex={17} />{' '}
            <AnimatedHeroWord word="Better." startIndex={24} />
          </span>
        </h1>
        <div className="public-hero-actions">
          <button
            className="public-button public-button-hero"
            type="button"
            onClick={onGetStarted}
            disabled={checkingSession}
          >
            {checkingSession ? 'Checking your account…' : 'Get Started'}
            {!checkingSession && <ArrowRight size={18} />}
          </button>
        </div>
        {sessionError && <p className="public-hero-error" role="alert">{sessionError}</p>}
      </div>
    </main>
  );
}

function About() {
  return (
    <section className="public-section public-about">
      <div className="public-about-copy">
        <p className="public-eyebrow public-eyebrow-green">ABOUT AGRIMITRA</p>
        <h2>Knowledge that helps<br /><em>your farm grow.</em></h2>
        <p>
          AgriMitra brings agricultural guidance and practical digital tools together
          in one place. Ask questions in a conversational way, explore crop and plant
          health information, and stay informed with market and weather updates.
        </p>
        <p>
          We aim to make useful information easier to find, so farmers can consider
          their options and make decisions with greater confidence.
        </p>
        <Link className="public-text-link" to="/features">Discover what you can do <ArrowRight size={17} /></Link>
      </div>
      <div className="public-about-visual">
        <div className="public-about-image" role="img" aria-label="Farmer using a phone in a green field" />
        <div className="public-about-callout">
          <span className="public-callout-icon"><Sprout size={23} /></span>
          <div><strong>Made for the people who grow our food</strong><span>Practical tools, all in one place</span></div>
        </div>
      </div>
    </section>
  );
}

function Features() {
  return (
    <section className="public-section public-features">
      <div className="public-section-heading">
        <p className="public-eyebrow public-eyebrow-green">TOOLS FOR YOUR FARM</p>
        <h2>Helpful insights.<br /><em>Right when you need them.</em></h2>
        <p>Explore five practical tools designed to support everyday farming decisions.</p>
      </div>
      <div className="public-feature-grid">
        {features.map(({ title, description, icon: Icon, path, label }, index) => (
          <Link
            className={`public-feature-card${index === 0 ? ' public-feature-card-featured' : ''}`}
            to={path}
            key={title}
          >
            <span className="public-feature-icon"><Icon size={23} strokeWidth={1.9} /></span>
            <span className="public-feature-number">0{index + 1}</span>
            <h3>{title}</h3>
            <p>{description}</p>
            <span className="public-feature-link">{label} <ArrowRight size={16} /></span>
          </Link>
        ))}
      </div>
      <p className="public-features-note">
        <ShieldCheck size={16} /> Plant health information is a starting point, not a substitute for local expert advice.
      </p>
    </section>
  );
}

function HowItWorks({ onGetStarted }) {
  const steps = [
    { number: '01', title: 'Create your account', description: 'Sign up to make your AgriMitra tools available in one place.', icon: Users },
    { number: '02', title: 'Explore your tools', description: 'Ask questions and explore helpful agricultural information.', icon: BookOpen },
    { number: '03', title: 'Decide with confidence', description: 'Use relevant information to plan your next farming steps.', icon: Check },
  ];

  return (
    <section className="public-section public-how">
      <div className="public-section-heading">
        <p className="public-eyebrow public-eyebrow-green">HOW IT WORKS</p>
        <h2>Three simple steps<br /><em>to get started.</em></h2>
      </div>
      <div className="public-steps">
        {steps.map(({ number, title, description, icon: Icon }) => (
          <article className="public-step" key={number}>
            <div className="public-step-top"><span>{number}</span><Icon size={22} /></div>
            <h3>{title}</h3>
            <p>{description}</p>
          </article>
        ))}
      </div>
      <button className="public-button public-button-green" type="button" onClick={onGetStarted}>
        Get Started <ArrowRight size={17} />
      </button>
    </section>
  );
}

function WhyChooseUs() {
  const benefits = [
    'AI-powered farming assistance',
    'Easy-to-use tools in one place',
    'Agricultural information, made accessible',
    'Real-time information where available',
    'Designed with Indian farmers in mind',
  ];

  return (
    <section className="public-why">
      <div className="public-why-inner">
        <div className="public-why-copy">
          <p className="public-eyebrow">A SUPPORTIVE FARMING COMPANION</p>
          <h2>Built around the<br />way you farm.</h2>
          <p>Useful information should be approachable, relevant and easy to find.</p>
        </div>
        <ul className="public-benefits">
          {benefits.map((benefit) => (
            <li key={benefit}><span><Check size={15} /></span>{benefit}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Contact() {
  const [message, setMessage] = useState('');

  function handleSubmit(event) {
    event.preventDefault();
    setMessage(
      'Your message has not been sent. AgriMitra does not have a contact-submission endpoint configured yet.',
    );
  }

  return (
    <section className="public-section public-contact">
      <div className="public-contact-copy">
        <p className="public-eyebrow public-eyebrow-green">GET IN TOUCH</p>
        <h2>We’d love to<br /><em>hear from you.</em></h2>
        <p>Have a question or feedback about AgriMitra? Leave a message and we’ll be ready to connect once contact submissions are available.</p>
        <div className="public-contact-promise"><MessageCircle size={19} /> Your feedback helps us grow with farmers.</div>
      </div>
      <form className="public-contact-form" onSubmit={handleSubmit}>
        <div className="public-form-row">
          <label>Name<input name="name" autoComplete="name" required maxLength={100} /></label>
          <label>Email<input name="email" type="email" autoComplete="email" required maxLength={254} /></label>
        </div>
        <label>Subject<input name="subject" required maxLength={120} /></label>
        <label>Message<textarea name="message" rows="4" required maxLength={2000} /></label>
        <button className="public-button public-button-green" type="submit">
          Send Message <ArrowRight size={17} />
        </button>
        {message && <p className="public-contact-status" role="status">{message}</p>}
      </form>
    </section>
  );
}

function Footer() {
  return (
    <footer className="public-footer">
      <div className="public-footer-main">
        <div className="public-footer-about">
          <Brand footer />
          <p>Bringing useful agricultural information and digital tools closer to farmers.</p>
        </div>
        <div className="public-footer-links">
          <h3>Explore</h3>
          {navigationItems.map(([label, path]) => <Link key={path} to={path}>{label}</Link>)}
        </div>
        <div className="public-footer-links">
          <h3>Farmer tools</h3>
          {features.map((feature) => (
            <Link key={feature.title} to={feature.path}>{feature.title}</Link>
          ))}
        </div>
      </div>
      <div className="public-footer-bottom">
        <span>© {new Date().getFullYear()} AgriMitra. All rights reserved.</span>
        <span><Leaf size={15} /> Growing a more informed future</span>
      </div>
    </footer>
  );
}

export default function LandingPage({ page = 'home' }) {
  const navigate = useNavigate();
  const [sessionError, setSessionError] = useState('');
  const [checkingSession, setCheckingSession] = useState(false);

  async function handleGetStarted() {
    setCheckingSession(true);
    setSessionError('');

    try {
      const response = await fetch('/api/auth/me', { credentials: 'same-origin' });
      if (response.ok) {
        navigate('/app');
      } else if (response.status === 401) {
        navigate('/signup');
      } else {
        throw new Error('We could not verify your account. Please try again.');
      }
    } catch (error) {
      setSessionError(error.message || 'Could not connect to AgriMitra. Please try again.');
    } finally {
      setCheckingSession(false);
    }
  }

  const pages = {
    about: <><About /><WhyChooseUs /></>,
    features: <Features />,
    'how-it-works': <HowItWorks onGetStarted={handleGetStarted} />,
    contact: <Contact />,
  };

  return (
    <div className="public-site">
      <Navigation />
      {page === 'home' ? (
        <Hero
          onGetStarted={handleGetStarted}
          checkingSession={checkingSession}
          sessionError={sessionError}
        />
      ) : (
        <main className="public-info-page">{pages[page]}</main>
      )}
      <Footer />
    </div>
  );
}
