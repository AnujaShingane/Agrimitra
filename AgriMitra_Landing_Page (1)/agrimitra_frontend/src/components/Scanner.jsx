import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import { ScanLine, UploadCloud, AlertCircle, CheckCircle, Leaf } from 'lucide-react';

const PLANTS = [
  'Paddy / Rice',
  'Wheat',
  'Cotton',
  'Maize / Corn',
  'Tomato',
  'Chilli / Pepper',
  'Groundnut / Peanut',
  'Soybean',
  'Potato',
  'Brinjal / Eggplant',
  'Grapevine',
  'Other plant',
];

function Scanner({ t, language }) {
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [error, setError] = useState('');
  const [plant, setPlant] = useState('');
  const [description, setDescription] = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const handleScan = async (file) => {
    if (!file) return;
    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
      setError('Please select a JPEG, PNG, or WebP image.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('The image must be 10MB or smaller.');
      return;
    }
    if (!plant) {
      setError(t?.scannerPlantRequired || 'Select the plant or crop before uploading a leaf.');
      return;
    }
    setScanning(true);
    setResult(null);
    setError('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('plant', plant);
      formData.append('description', description.trim());
      
      const resp = await axios.post(`/api/scan?lang=${language || 'en'}`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      setResult(resp.data.analysis);
    } catch (err) {
      console.error("Scan error:", err);
      setError(err.response?.data?.detail || 'Leaf analysis could not be completed. Please try again later.');
    } finally {
      setScanning(false);
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setError('');
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
      setPreviewUrl(URL.createObjectURL(file));
      handleScan(file);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (scanning) return;
    
    const file = e.dataTransfer.files[0];
    if (file) {
      setError('');
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
      setPreviewUrl(URL.createObjectURL(file));
      handleScan(file);
    }
  };

  const handleClick = () => {
    if (scanning) return;
    if (!plant) {
      setError(t?.scannerPlantRequired || 'Select the plant or crop before uploading a leaf.');
      return;
    }
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleReset = (e) => {
    e.stopPropagation();
    setResult(null);
    setError('');
    setPlant('');
    setDescription('');
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const getSeverityColor = (severity) => {
    const s = (severity || '').toLowerCase();
    if (s === 'high') return '#ef4444'; // Red
    if (s === 'medium') return '#f59e0b'; // Amber
    return '#10b981'; // Emerald
  };

  return (
    <motion.div 
      className="page-container"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
    >
      <div className="page-header">
        <h1 className="page-title"><ScanLine size={32} className="inline-icon" /> {t.scannerPanel || 'Crop Disease Scanner'}</h1>
        <p className="page-subtitle">{t?.scannerSubtitle || 'Upload an image of a leaf to instantly identify diseases and get remedies.'}</p>
      </div>

      <div className="scanner-layout">
        <div className="scanner-upload-section">
          <div className="glass-panel" style={{ padding: '24px', marginBottom: '20px' }} onClick={(event) => event.stopPropagation()}>
            <label htmlFor="scanner-plant" style={{ display: 'block', marginBottom: '8px', fontWeight: 600 }}>
              {t?.scannerPlantLabel || 'What plant is this leaf from?'}
            </label>
            <select
              id="scanner-plant"
              value={plant}
              onChange={(event) => { setPlant(event.target.value); setError(''); }}
              style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--surface-primary)', color: 'var(--text-primary)' }}
            >
              <option value="">{t?.scannerPlantPlaceholder || 'Select a plant or crop...'}</option>
              {PLANTS.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>

            <label htmlFor="scanner-description" style={{ display: 'block', margin: '18px 0 8px', fontWeight: 600 }}>
              {t?.scannerDescriptionLabel || 'Describe what you observe (optional)'}
            </label>
            <textarea
              id="scanner-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={1200}
              rows={4}
              placeholder={t?.scannerDescriptionPlaceholder || 'For example: yellow spots started three days ago after heavy rain...'}
              style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', resize: 'vertical', color: 'var(--text-primary)' }}
            />
          </div>

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept="image/*"
            style={{ display: 'none' }}
          />

          <motion.div
            className={`scanner-dropzone-large glass-panel ${dragging ? 'dragging' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={handleClick}
            aria-disabled={!plant}
            whileHover={{ scale: previewUrl ? 1 : 1.02 }}
            whileTap={{ scale: previewUrl ? 1 : 0.98 }}
          >
            <AnimatePresence mode="wait">
              {previewUrl ? (
                <motion.div 
                  key="preview"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="scanner-preview-container"
                >
                  <img src={previewUrl} alt="Leaf Preview" className="scanner-preview-image" />
                  
                  {scanning && (
                    <motion.div 
                      className="scanner-laser-container"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                    >
                      <motion.div 
                        className="scanner-laser"
                        animate={{ top: ['0%', '100%', '0%'] }}
                        transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                      />
                      <div className="scanner-overlay-text pulsing">
                        <ScanLine className="spin-slow" /> {t?.scannerAnalyzingCrop || 'Analyzing Crop Data...'}
                      </div>
                    </motion.div>
                  )}
                </motion.div>
              ) : (
                <motion.div 
                  key="upload"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="scanner-empty-state"
                >
                  <motion.div 
                    animate={{ y: [0, -10, 0] }} 
                    transition={{ duration: 2, repeat: Infinity }}
                  >
                    <UploadCloud size={64} className="upload-icon" />
                  </motion.div>
                  <h3>{t?.scannerDragDrop || 'Drag & Drop Leaf Image'}</h3>
                  <p>{t?.scannerBrowse || 'or click to browse from your device'}</p>
                  <span className="file-hint">{t?.scannerFileHint || 'Supports JPG, PNG (Max 10MB)'}</span>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          {previewUrl && !scanning && (
            <motion.button 
              className="btn-danger mt-4" 
              onClick={handleReset}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              {t?.scannerScanAnother || 'Scan Another Leaf'}
            </motion.button>
          )}
          {error && <p className="error-state" role="alert" style={{ marginTop: '1rem' }}>{error}</p>}
        </div>

        <div className="scanner-results-section">
          <AnimatePresence mode="wait">
            {scanning ? (
              <motion.div 
                key="loading"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="glass-panel results-placeholder loading"
              >
                <div className="skeleton-line title"></div>
                <div className="skeleton-line"></div>
                <div className="skeleton-line"></div>
                <div className="skeleton-line short"></div>
              </motion.div>
            ) : result ? (
              <motion.div 
                key="result"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                className="glass-panel results-card"
                style={{ borderTop: `4px solid ${getSeverityColor(result.severity)}` }}
              >
                <div className="results-header">
                  <h2>{result.disease}</h2>
                  <span 
                    className="severity-badge"
                    style={{ backgroundColor: `${getSeverityColor(result.severity)}20`, color: getSeverityColor(result.severity) }}
                  >
                    {result.severity === 'High' ? <AlertCircle size={16} /> : <CheckCircle size={16} />}
                    {result.severity} {t?.scannerSeverity || 'Severity'}
                  </span>
                </div>

                <p style={{ color: 'var(--text-muted)', margin: '0 0 18px' }}>
                  {t?.scannerAnalyzedPlant || 'Analysis context'}: {plant}
                </p>

                {result.pathogen && (
                  <div className="results-detail-block">
                    <strong>Pathogen</strong>
                    <p>{result.pathogen}</p>
                  </div>
                )}

                {result.diagnostic_note && (
                  <div className="results-detail-block">
                    <strong>Why this fits</strong>
                    <p>{result.diagnostic_note}</p>
                  </div>
                )}
                
                <div className="results-metrics">
                  <div className="metric-box">
                    <span className="metric-label">{t?.scannerConfidence || 'Confidence'}</span>
                    <span className="metric-value">{result.confidence}%</span>
                  </div>
                  <div className="metric-box">
                    <span className="metric-label">{t?.scannerAffectedArea || 'Affected Area'}</span>
                    <span className="metric-value">{result.affected_area || 'Unknown'}</span>
                  </div>
                </div>

                {result.visible_signs?.length > 0 && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> Visible signs</h3>
                    <ul>
                      {result.visible_signs.map((item, index) => (
                        <li key={`sign-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="results-recommendations">
                  <h3><Leaf size={18} /> {t?.scannerRecommendedActions || 'Recommended Actions'}</h3>
                  <ul>
                    {(result.recommendations || []).map((rec, i) => (
                      <motion.li 
                        key={i}
                        initial={{ opacity: 0, x: 10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.1 }}
                      >
                        {rec}
                      </motion.li>
                    ))}
                  </ul>
                </div>

                <div className="results-recommendations" style={{ marginTop: '18px' }}>
                  <h3><Leaf size={18} /> Treatment / Fungicide Advisory</h3>
                  {result.treatment_options?.length > 0 && (
                    <ul>
                      {result.treatment_options.map((item, index) => (
                        <li key={`treatment-option-${index}`}>{item}</li>
                      ))}
                    </ul>
                  )}
                  {result.treatment_advisory && (
                    <p className="results-caution">{result.treatment_advisory}</p>
                  )}
                </div>

                {result.non_chemical_actions?.length > 0 && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> Non-chemical actions</h3>
                    <ul>
                      {result.non_chemical_actions.map((item, index) => (
                        <li key={`non-chemical-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.symptoms && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> Symptoms</h3>
                    <ul>
                      {(result.symptoms || []).map((item, index) => (
                        <li key={`symptom-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.treatment && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> Treatment</h3>
                    <ul>
                      {(result.treatment || []).map((item, index) => (
                        <li key={`treatment-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.preventive_measures && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> Prevention</h3>
                    <ul>
                      {(result.preventive_measures || []).map((item, index) => (
                        <li key={`preventive-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.confidence_note && (
                  <div className="results-detail-block results-caution" style={{ marginTop: '18px' }}>
                    <strong>Image confidence note</strong>
                    <p>{result.confidence_note}</p>
                  </div>
                )}

                {result.source_guidance?.length > 0 && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> Source guidance</h3>
                    <ul>
                      {result.source_guidance.map((item, index) => (
                        <li key={`source-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </motion.div>
            ) : (
              <motion.div 
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="glass-panel results-placeholder empty"
              >
                <Leaf size={48} className="empty-icon" />
                <p>{t?.scannerEmptyState || 'Upload a leaf image to see detailed AI analysis and targeted remedies.'}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}

export default Scanner;
