import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { BookOpen, ExternalLink, IndianRupee, RefreshCcw } from 'lucide-react';

export default function Schemes({ t, language }) {
  const [data, setData] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchSchemes = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/schemes?lang=${language || 'en'}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || 'Schemes request failed');
      }
      const payload = await res.json();
      setData(Array.isArray(payload) ? payload : []);
    } catch (requestError) {
      setData([]);
      setError(requestError.message || 'Unable to load schemes.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchemes();
  }, [language]);

  const containerVariants = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };

  const itemVariants = {
    hidden: { opacity: 0, scale: 0.95 },
    show: { opacity: 1, scale: 1 }
  };

  return (
    <motion.div 
      className="page-container"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
    >
      <div className="page-header">
        <h1 className="page-title"><BookOpen className="inline-icon" /> {t.schemesPanel || 'Govt Schemes'}</h1>
        <p className="page-subtitle">{t?.schemesSubtitle || 'Discover subsidies, financial support, and welfare programs for farmers.'}</p>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '20px' }}>
        <button className="btn-secondary" onClick={fetchSchemes} disabled={loading}>
          <RefreshCcw size={16} style={{ marginRight: '8px' }} /> {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {loading ? (
        <div className="agent-grid-full">
          {[1, 2, 3].map((i) => (
            <div key={i} className="glass-panel" style={{ padding: '30px', height: '250px' }}>
              <div className="skeleton-line" style={{ width: '80%', height: '24px', marginBottom: '20px' }}></div>
              <div className="skeleton-line" style={{ width: '100%', marginBottom: '10px' }}></div>
              <div className="skeleton-line" style={{ width: '100%', marginBottom: '10px' }}></div>
              <div className="skeleton-line" style={{ width: '60%' }}></div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="error-state glass-panel" style={{ padding: '40px', textAlign: 'center' }}>
          <div className="error-emoji" style={{ fontSize: '3rem' }}>🏛️</div>
          <p>{error}</p>
        </div>
      ) : data.length === 0 ? (
        <div className="glass-panel" style={{ padding: '40px', textAlign: 'center' }}>
          <p>No scheme data is available right now.</p>
        </div>
      ) : (
        <motion.div 
          className="agent-grid-full"
          variants={containerVariants}
          initial="hidden"
          animate="show"
        >
          {data.map((scheme, i) => (
            <motion.div key={`${scheme.name || scheme.title || 'scheme'}-${i}`} variants={itemVariants} className="glass-panel" style={{ padding: '30px', display: 'flex', flexDirection: 'column' }}>
              <h3 style={{ fontSize: '1.4rem', marginBottom: '15px', color: 'var(--accent-primary)', display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                <IndianRupee size={24} style={{ marginTop: '3px', flexShrink: 0 }} />
                {scheme.name || scheme.title || 'Scheme'}
              </h3>
              
              <p style={{ color: 'var(--text-secondary)', lineHeight: '1.6', marginBottom: '20px', flex: 1 }}>
                {scheme.description}
              </p>

              <div style={{ background: 'rgba(255,255,255,0.05)', padding: '15px', borderRadius: '12px', marginBottom: '20px' }}>
                <strong style={{ display: 'block', marginBottom: '8px', color: 'var(--text-muted)' }}>{t?.schemesEligibility || 'Eligibility:'}</strong>
                <span style={{ color: 'var(--text-main)' }}>{scheme.eligibility || 'Eligibility details not available.'}</span>
              </div>

              {scheme.link && scheme.link.startsWith('http') ? (
                <a 
                  href={scheme.link} 
                  target="_blank" 
                  rel="noreferrer" 
                  style={{ 
                    display: 'inline-flex', 
                    alignItems: 'center', 
                    gap: '8px', 
                    color: 'var(--accent-secondary)', 
                    textDecoration: 'none',
                    fontWeight: '600',
                    padding: '10px 0'
                  }}
                >
                  {t?.schemesApply || 'Apply / Learn More'} <ExternalLink size={16} />
                </a>
              ) : (
                <div style={{ color: 'var(--text-muted)', padding: '10px 0' }}>Official application link unavailable.</div>
              )}
            </motion.div>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}
