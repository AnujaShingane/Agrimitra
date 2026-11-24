import { useEffect, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom';

import LandingPage from './components/LandingPage';
import AuthPage from './components/AuthPage';
import Layout from './components/Layout';
import AgentGrid from './components/AgentGrid';
import Chat from './components/Chat';
import Scanner from './components/Scanner';
import Market from './components/Market';
import Schemes from './components/Schemes';
import Weather from './components/Weather';

import { translations, locales } from './translations';
import './index.css';

function RequireAuth({ children }) {
  const location = useLocation();
  const [status, setStatus] = useState('checking');

  useEffect(() => {
    let active = true;
    fetch('/api/auth/me', { credentials: 'same-origin' })
      .then((response) => {
        if (active) setStatus(response.ok ? 'authenticated' : 'anonymous');
      })
      .catch(() => {
        if (active) setStatus('error');
      });
    return () => {
      active = false;
    };
  }, []);

  if (status === 'checking') {
    return <div className="auth-loading">Checking your session…</div>;
  }
  if (status === 'anonymous') {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  if (status === 'error') {
    return (
      <div className="auth-loading">
        Could not connect to AgriMitra. Please check that the backend is running and refresh.
      </div>
    );
  }
  return children;
}

function LegacyChatRedirect() {
  const { agentId } = useParams();
  return <Navigate to={`/app/chat/${agentId}`} replace />;
}

function App() {
  const [language, setLanguage] = useState('en');

  const t = translations[language];
  const locale = locales[language];

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/signup" element={<AuthPage mode="signup" />} />
      <Route
        path="/app"
        element={(
          <RequireAuth>
            <Layout t={t} language={language} setLanguage={setLanguage} />
          </RequireAuth>
        )}
      >
        <Route index element={<AgentGrid t={t} language={language} />} />
        <Route path="chat/:agentId" element={<Chat t={t} language={language} locale={locale} />} />
        <Route path="chat" element={<Chat t={t} language={language} locale={locale} />} />
        <Route path="scanner" element={<Scanner t={t} language={language} />} />
        <Route path="market" element={<Market t={t} language={language} />} />
        <Route path="weather" element={<Weather t={t} language={language} />} />
        <Route path="schemes" element={<Schemes t={t} language={language} />} />
      </Route>
      <Route path="/chat/:agentId" element={<LegacyChatRedirect />} />
      <Route path="/chat" element={<Navigate to="/app/chat" replace />} />
      <Route path="/scanner" element={<Navigate to="/app/scanner" replace />} />
      <Route path="/market" element={<Navigate to="/app/market" replace />} />
      <Route path="/weather" element={<Navigate to="/app/weather" replace />} />
      <Route path="/schemes" element={<Navigate to="/app/schemes" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
