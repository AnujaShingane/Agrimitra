import { useState } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Home, MessageSquare, Cloud, BarChart2, BookOpen, Scan, LogOut } from 'lucide-react';

export default function Layout({ t, language, setLanguage }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [logoutError, setLogoutError] = useState('');

  const navItems = [
    { path: '/app', icon: <Home size={24} />, label: t.agentsAll || 'Home' },
    { path: '/app/chat', icon: <MessageSquare size={24} />, label: t.chatPanel || 'Chat' },
    { path: '/app/scanner', icon: <Scan size={24} />, label: t.scannerPanel || 'Scanner' },
    { path: '/app/market', icon: <BarChart2 size={24} />, label: t.marketPanel || 'Market' },
    { path: '/app/weather', icon: <Cloud size={24} />, label: t.weatherPanel || 'Weather' },
    { path: '/app/schemes', icon: <BookOpen size={24} />, label: t.schemesPanel || 'Schemes' },
  ];

  async function handleLogout() {
    setLogoutError('');
    try {
      const response = await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error('Could not log out. Please try again.');
      navigate('/', { replace: true });
    } catch (error) {
      setLogoutError(error.message);
    }
  }

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <aside className="app-sidebar glass">
        <div className="sidebar-brand">
          <div className="sidebar-logo">🌾</div>
        </div>
        <nav className="sidebar-nav">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path || (item.path !== '/app' && location.pathname.startsWith(item.path));
            return (
              <Link to={item.path} key={item.path} className={`nav-item ${isActive ? 'active' : ''}`}>
                <div className="nav-icon-container">
                  {item.icon}
                  {isActive && (
                    <motion.div
                      layoutId="nav-indicator"
                      className="nav-indicator"
                      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                    />
                  )}
                </div>
                <span className="nav-label">{item.label}</span>
              </Link>
            );
          })}
            <Link to="/" className="nav-item nav-home-link">
              <div className="nav-icon-container"><span aria-hidden="true">🌿</span></div>
              <span className="nav-label">Landing page</span>
            </Link>
        </nav>
      </aside>

      {/* Main Content Area */}
      <div className="main-wrapper">
        <header className="app-header glass">
          <div>
            <div className="header-title">{t.appTitle}</div>
            <div className="header-subtitle">{t.appSubtitle}</div>
          </div>
          <div className="header-status">
            <span className="status-dot"></span>
            <span>{t.systemOnline}</span>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="lang-select"
            >
              <option value="en">English</option>
              <option value="hi">हिंदी</option>
              <option value="te">తెలుగు</option>
              <option value="mr">मराठी</option>
              <option value="bn">বাংলা</option>
              <option value="gu">ગુજરાતી</option>
              <option value="kn">ಕನ್ನಡ</option>
              <option value="ml">മലയാളം</option>
              <option value="or">ଓଡ଼ିଆ</option>
              <option value="pa">ਪੰਜਾਬੀ</option>
              <option value="ta">தமிழ்</option>
            </select>
            <button type="button" className="logout-button" onClick={handleLogout} aria-label="Log out">
              <LogOut size={17} /> <span>Log out</span>
            </button>
          </div>
        </header>
        {logoutError && <p className="logout-error" role="alert">{logoutError}</p>}
        
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
