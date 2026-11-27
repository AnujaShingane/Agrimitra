import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import { ScanLine, UploadCloud, AlertCircle, CheckCircle, Leaf } from 'lucide-react';

const SYMPTOM_OPTIONS = [
  'Black or brown spots',
  'Yellow leaves',
  'Holes or damaged leaves',
  'White powder or patches',
  'Leaves drying or falling',
  'Curling or twisted leaves',
  'Something else',
  "I don't know",
];

function Scanner({ t, language }) {
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [error, setError] = useState('');
  const [plant, setPlant] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [symptoms, setSymptoms] = useState([]);
  const [additionalSymptoms, setAdditionalSymptoms] = useState('');
  const [noticedWhen, setNoticedWhen] = useState('');
  const [spreading, setSpreading] = useState('');
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
    if (!plant.trim()) {
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
      symptoms.forEach((symptom) => formData.append('observations', symptom));
      formData.append('additional_symptoms', additionalSymptoms.trim());
      formData.append('noticed_when', noticedWhen);
      formData.append('spreading', spreading);
      formData.append('description', description.trim());

      const resp = await axios.post(`/api/scan?lang=${language || 'en'}`, formData, {
        timeout: 60000,
      });
      setResult(resp.data.analysis);
    } catch (err) {
      console.error("Scan error:", err);
      setError(err.response?.data?.detail || 'Leaf analysis could not be completed. Please try again later.');
    } finally {
      setScanning(false);
    }
  };

  const selectFile = (file) => {
    if (!file) return;
    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
      setSelectedFile(null);
      setPreviewUrl(null);
      setError('Please select a JPEG, PNG, or WebP image.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setSelectedFile(null);
      setPreviewUrl(null);
      setError('The image must be 10MB or smaller.');
      return;
    }
    setError('');
    setResult(null);
    setSelectedFile(file);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(file));
  };

  const handleFileChange = (e) => {
    selectFile(e.target.files?.[0]);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (scanning) return;
    
    selectFile(e.dataTransfer.files?.[0]);
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
    setSelectedFile(null);
    setSymptoms([]);
    setAdditionalSymptoms('');
    setNoticedWhen('');
    setSpreading('');
    setDescription('');
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const toggleSymptom = (symptom) => {
    setSymptoms((current) => {
      if (symptom === "I don't know") {
        return current.includes(symptom) ? [] : [symptom];
      }
      const withoutUnknown = current.filter((item) => item !== "I don't know");
      return withoutUnknown.includes(symptom)
        ? withoutUnknown.filter((item) => item !== symptom)
        : [...withoutUnknown, symptom];
    });
    setError('');
  };

  const getSeverityColor = (severity) => {
    const s = (severity || '').toLowerCase();
    if (s === 'severe') return '#ef4444';
    if (s === 'moderate') return '#f59e0b';
    if (s === 'mild') return '#10b981';
    return '#6b7280';
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
              Plant name <span aria-hidden="true">*</span>
            </label>
            <input
              id="scanner-plant"
              type="text"
              value={plant}
              onChange={(event) => { setPlant(event.target.value); setError(''); }}
              maxLength={100}
              required
              placeholder="For example, Mango, Tomato, or Wheat"
              style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--surface-primary)', color: 'var(--text-primary)' }}
            />

            <fieldset style={{ border: 0, padding: 0, margin: '20px 0 0' }}>
              <legend style={{ marginBottom: '10px', fontWeight: 600 }}>
                What have you noticed? (optional)
              </legend>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '8px' }}>
                {SYMPTOM_OPTIONS.map((symptom) => (
                  <label key={symptom} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <input
                      type="checkbox"
                      checked={symptoms.includes(symptom)}
                      onChange={() => toggleSymptom(symptom)}
                    />
                    {symptom}
                  </label>
                ))}
              </div>
            </fieldset>

            {symptoms.includes('Something else') && (
              <>
                <label htmlFor="scanner-additional-symptoms" style={{ display: 'block', margin: '16px 0 8px', fontWeight: 600 }}>
                  Tell us what else you noticed (optional)
                </label>
                <input
                  id="scanner-additional-symptoms"
                  type="text"
                  value={additionalSymptoms}
                  onChange={(event) => setAdditionalSymptoms(event.target.value)}
                  maxLength={300}
                  placeholder="Describe what you see"
                  style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--surface-primary)', color: 'var(--text-primary)' }}
                />
              </>
            )}

            <label htmlFor="scanner-noticed-when" style={{ display: 'block', margin: '18px 0 8px', fontWeight: 600 }}>
              When did you first notice it? (optional)
            </label>
            <select
              id="scanner-noticed-when"
              value={noticedWhen}
              onChange={(event) => setNoticedWhen(event.target.value)}
              style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--surface-primary)', color: 'var(--text-primary)' }}
            >
              <option value="">Choose an option...</option>
              {['Today', 'A few days ago', 'About a week ago', 'More than two weeks ago', 'Not sure'].map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>

            <label htmlFor="scanner-spreading" style={{ display: 'block', margin: '18px 0 8px', fontWeight: 600 }}>
              Is the problem spreading? (optional)
            </label>
            <select
              id="scanner-spreading"
              value={spreading}
              onChange={(event) => setSpreading(event.target.value)}
              style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--surface-primary)', color: 'var(--text-primary)' }}
            >
              <option value="">Choose an option...</option>
              {['Yes', 'No', 'Not sure'].map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>

            <label htmlFor="scanner-description" style={{ display: 'block', margin: '18px 0 8px', fontWeight: 600 }}>
              Anything else you would like to tell us? (optional)
            </label>
            <textarea
              id="scanner-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={1200}
              rows={4}
              placeholder="For example, the weather or recent changes in watering"
              style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', resize: 'vertical', color: 'var(--text-primary)' }}
            />
          </div>

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept="image/jpeg,image/png,image/webp"
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

          {selectedFile && !scanning && (
            <button
              type="button"
              className="button button-primary mt-4"
              onClick={() => handleScan(selectedFile)}
              disabled={!plant.trim()}
            >
              Analyze leaf
            </button>
          )}

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
                  <div>
                    <h2>{result.possible_disease}</h2>
                    <span className="severity-badge">
                      {result.diagnosis_status === 'possible'
                        ? <CheckCircle size={16} />
                        : <AlertCircle size={16} />}
                      {result.diagnosis_status.replaceAll('_', ' ')}
                    </span>
                  </div>
                  <span
                    className="severity-badge"
                    style={{ backgroundColor: `${getSeverityColor(result.severity)}20`, color: getSeverityColor(result.severity) }}
                  >
                    {result.severity} severity
                  </span>
                </div>

                <p style={{ color: 'var(--text-muted)', margin: '0 0 18px' }}>
                  Plant: {result.plant_name || plant}
                </p>

                {result.plant_identification_note && (
                  <div className="results-detail-block">
                    <strong>Plant identification</strong>
                    <p>{result.plant_identification_note}</p>
                  </div>
                )}

                {result.observed_symptoms?.length > 0 && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> What we can see</h3>
                    <ul>
                      {result.observed_symptoms.map((item, index) => (
                        <li key={`sign-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.explanation && (
                  <div className="results-detail-block">
                    <strong>What may be happening</strong>
                    <p>{result.explanation}</p>
                  </div>
                )}

                {result.alternative_causes?.length > 0 && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> Other possible causes</h3>
                    <ul>
                      {result.alternative_causes.map((item, index) => (
                        <li key={`cause-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.treatment?.length > 0 && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> What you can do</h3>
                    <ul>
                      {result.treatment.map((item, index) => (
                        <li key={`treatment-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.prevention?.length > 0 && (
                  <div className="results-recommendations" style={{ marginTop: '18px' }}>
                    <h3><Leaf size={18} /> Prevention</h3>
                    <ul>
                      {result.prevention.map((item, index) => (
                        <li key={`prevention-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.confidence_note && (
                  <div className="results-detail-block results-caution" style={{ marginTop: '18px' }}>
                    <strong>About this result</strong>
                    <p>{result.confidence_note}</p>
                  </div>
                )}

                {result.when_to_consult_an_expert && (
                  <div className="results-detail-block" style={{ marginTop: '18px' }}>
                    <strong>When to ask an expert</strong>
                    <p>{result.when_to_consult_an_expert}</p>
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
