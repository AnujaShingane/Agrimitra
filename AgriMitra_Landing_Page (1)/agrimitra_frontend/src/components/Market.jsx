import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { BarChart2, TrendingUp, TrendingDown, Minus, RefreshCcw } from 'lucide-react';

export default function Market({ t, language }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchMarket = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/market?lang=${language || 'en'}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || 'Market data request failed');
      }
      const payload = await res.json();
      setData(Array.isArray(payload) ? payload : []);
    } catch (requestError) {
      setData([]);
      setError(requestError.message || 'Unable to load live market data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMarket();
  }, [language]);

  const containerVariants = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
  };

  return (
    <motion.div 
      className="page-container"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
    >
      <div className="page-header">
        <h1 className="page-title"><BarChart2 className="inline-icon" /> {t.marketPanel || 'Market Prices'}</h1>
        <p className="page-subtitle">{t?.marketSubtitle || 'Real-time mandi prices, MSP, and demand trends for your crops.'}</p>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '20px' }}>
        <button className="btn-secondary" onClick={fetchMarket} disabled={loading}>
          <RefreshCcw size={16} style={{ marginRight: '8px' }} /> {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {loading ? (
        <div className="agent-grid-full">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="glass-panel" style={{ padding: '30px', height: '220px' }}>
              <div className="skeleton-line" style={{ width: '60%', height: '24px', marginBottom: '20px' }}></div>
              <div className="skeleton-line" style={{ width: '80%' }}></div>
              <div className="skeleton-line" style={{ width: '40%' }}></div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="error-state glass-panel" style={{ padding: '40px', textAlign: 'center' }}>
          <div className="error-emoji" style={{ fontSize: '3rem' }}>📡</div>
          <p>{error}</p>
        </div>
      ) : data.length === 0 ? (
        <div className="glass-panel" style={{ padding: '40px', textAlign: 'center' }}>
          <p>No live market data is available for the current request.</p>
        </div>
      ) : (
        <motion.div 
          className="agent-grid-full"
          variants={containerVariants}
          initial="hidden"
          animate="show"
        >
          {data.map((info, idx) => (
            <motion.div key={`${info.crop}-${info.market}-${idx}`} variants={itemVariants} className="glass-panel" style={{ padding: '30px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                <h3 style={{ fontSize: '1.5rem', margin: 0 }}>{info.crop || 'Crop'}</h3>
                <span style={{ padding: '6px 12px', borderRadius: '20px', fontSize: '0.85rem', fontWeight: 'bold', background: 'rgba(16,185,129,0.1)', color: '#10b981' }}>
                  {info.state || 'State'}
                </span>
              </div>

              <div style={{ color: 'var(--text-muted)', marginBottom: '12px' }}>
                {info.market || 'Market'} • {info.district || 'District'}
              </div>

              <div style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '10px', color: 'var(--accent-primary)' }}>
                ₹{Number(info.modalPrice ?? info.minPrice ?? 0).toLocaleString()} / {info.unit || 'quintal'}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', color: 'var(--text-secondary)' }}>
                <div><strong>Min:</strong> ₹{Number(info.minPrice ?? 0).toLocaleString()}</div>
                <div><strong>Max:</strong> ₹{Number(info.maxPrice ?? 0).toLocaleString()}</div>
                <div><strong>Modal:</strong> ₹{Number(info.modalPrice ?? 0).toLocaleString()}</div>
                <div><strong>Variety:</strong> {info.variety || 'Unknown'}</div>
              </div>

              <div style={{ marginTop: '16px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                {info.arrivalDate ? `Arrival date: ${info.arrivalDate}` : 'Date unavailable'}
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}
