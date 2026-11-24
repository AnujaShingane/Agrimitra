import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowRight, MessageCircle, ScanLine, TrendingUp, CloudSun, Landmark, Sprout, ShieldCheck, Languages } from 'lucide-react';
import farmerHero from './assets/farmer-hero.png';

const tools = [
  { title: 'AI Crop Advisor', text: 'Get practical answers for crop care, pests, diseases and cultivation.', icon: Sprout, to: '/chat', tag: 'Ask an expert' },
  { title: 'Plant Health Scanner', text: 'Upload a leaf photo to explore possible plant health issues.', icon: ScanLine, to: '/scanner', tag: 'Scan a leaf' },
  { title: 'Mandi Market Prices', text: 'Explore market prices and make more informed selling decisions.', icon: TrendingUp, to: '/market', tag: 'View prices' },
  { title: 'Weather Advisory', text: 'Check weather information to plan your farm activities.', icon: CloudSun, to: '/weather', tag: 'Check weather' },
  { title: 'Government Schemes', text: 'Discover useful schemes, subsidies and farmer support information.', icon: Landmark, to: '/schemes', tag: 'Explore schemes' },
];

export default function Home() {
  return (
    <div className="landing-page">
      <section className="landing-hero11" style={{ backgroundImage: `linear-gradient(90deg, rgba(12,39,24,.90) 0%, rgba(12,39,24,.78) 39%, rgba(12,39,24,.12) 76%), url(${farmerHero})` }}>
        <div className="landing-hero11-content">
          <div className="hero-eyebrow"><span className="eyebrow-dot" /> SMARTER FARMING STARTS HERE</div>
          <h1>Grow better.<br /><span>Farm smarter.</span></h1>
          <p className="landing-lead">Your farming companion, powered by AI. Get crop guidance, understand plant health, follow market prices and make confident decisions — all in one place.</p>
          <div className="landing-actions">
            <Link className="landing-btn landing-btn-primary" to="/chat">Ask AgriMitra <ArrowRight size={18} /></Link>
            <a className="landing-btn landing-btn-outline" href="#explore">Explore features</a>
          </div>
          <div className="hero-trust"><ShieldCheck size={17} /> Helpful agricultural insights, in your language</div>
        </div>
        <div className="hero-image-caption"><span className="caption-mark">✳</span><span>Technology for every field</span></div>
      </section>

      <section className="landing-intro" id="explore">
        <div>
          <span className="section-kicker">ONE PLATFORM, MANY POSSIBILITIES</span>
          <h2>Everything your farm needs,<br /><em>within reach.</em></h2>
        </div>
        <p>From the first question to your next farming decision, AgriMitra brings useful tools together in one simple experience.</p>
      </section>

      <section className="landing-tools">
        {tools.map((tool, index) => {
          const Icon = tool.icon;
          return (
            <motion.div className="landing-tool-card" key={tool.title} initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: index * .07 }}>
              <div className="tool-icon"><Icon size={23} strokeWidth={1.8} /></div>
              <span className="tool-tag">{tool.tag}</span>
              <h3>{tool.title}</h3>
              <p>{tool.text}</p>
              <Link to={tool.to} className="tool-link">Get started <ArrowRight size={16} /></Link>
            </motion.div>
          );
        })}
      </section>

      <section className="landing-bottom-cta">
        <div className="cta-icon"><MessageCircle size={25} /></div>
        <div><span className="section-kicker">YOUR FARMING JOURNEY, SUPPORTED</span><h2>Have a question about your crops?</h2><p>Talk to AgriMitra and take your next step with more clarity.</p></div>
        <Link to="/chat" className="landing-btn landing-btn-dark">Chat with AgriMitra <ArrowRight size={18} /></Link>
      </section>
      <footer className="landing-footer"><div className="footer-brand"><span>🌾</span> AgriMitra AI</div><span>Empowering farmers with accessible agricultural intelligence.</span><span className="footer-language"><Languages size={15} /> Multilingual support</span></footer>
    </div>
  );
}
