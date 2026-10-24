import React, { useState, useEffect } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { ShieldCheck, PlusCircle, LayoutDashboard, Cpu, Server } from 'lucide-react';
import { getModelStatus, getHealth } from '../api.js';

export default function Layout() {
  const [modelStatus, setModelStatus] = useState('checking'); // 'online' | 'training' | 'offline' | 'checking'
  const [modelDetail, setModelDetail] = useState('Checking detector...');
  const location = useLocation();

  useEffect(() => {
    let isMounted = true;

    async function checkStatus() {
      try {
        const [health, models] = await Promise.allSettled([
          getHealth(),
          getModelStatus(),
        ]);

        if (!isMounted) return;

        if (models.status === 'fulfilled' && Array.isArray(models.value)) {
          const detector = models.value.find((m) => m.component === 'detector' || m.component === 'model');
          if (detector?.available) {
            setModelStatus('online');
            setModelDetail(detector.detail || 'Detector ready');
          } else {
            // Note: User mentioned ML model is currently training
            setModelStatus('training');
            setModelDetail(detector?.detail || 'Model training / initialising');
          }
        } else if (health.status === 'fulfilled') {
          setModelStatus('online');
          setModelDetail('Backend active');
        } else {
          setModelStatus('offline');
          setModelDetail('Backend offline');
        }
      } catch {
        if (isMounted) {
          setModelStatus('offline');
          setModelDetail('Detector offline');
        }
      }
    }

    checkStatus();
    const interval = setInterval(checkStatus, 30000); // Check every 30s
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="app-shell">
      {/* Top Industrial Navbar */}
      <header className="topbar">
        <div className="shell">
          <div style={{ display: 'flex', alignItems: 'center', gap: '28px' }}>
            <NavLink to="/" className="brand" aria-label="Eagle Eye Home">
              <span className="brand-icon-box">EE</span>
              <span>EAGLE EYE</span>
            </NavLink>

            <nav className="nav-links" aria-label="Primary Navigation">
              <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <LayoutDashboard size={15} />
                  <span>Dashboard</span>
                </span>
              </NavLink>
              <NavLink to="/inspect" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <PlusCircle size={15} />
                  <span>New Inspection</span>
                </span>
              </NavLink>
              <NavLink to="/cabinets" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <Server size={15} />
                  <span>Cabinets</span>
                </span>
              </NavLink>
            </nav>
          </div>

          <div className="topbar-right">
            {/* Detector status indicator */}
            <div
              className="detector-pill"
              title={`Detector Status: ${modelDetail}`}
              role="status"
              aria-live="polite"
            >
              <span className={`status-dot ${modelStatus}`} />
              <span style={{ color: '#c9d1d9' }}>
                {modelStatus === 'online' && 'Detector Online'}
                {modelStatus === 'training' && 'Model Training'}
                {modelStatus === 'offline' && 'Detector Offline'}
                {modelStatus === 'checking' && 'Connecting…'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="main-content">
        <div className="shell">
          <Outlet />
        </div>
      </main>

      {/* Industrial Footer */}
      <footer className="site-footer">
        <div className="shell">
          <div>
            <strong>EAGLE EYE</strong> — Industrial Electrical Cabinet Quality Assurance
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
            SYSTEM SPEC: V0.3 CONTRACT · DETECTOR & OCR INSPECTION ENGINE
          </div>
        </div>
      </footer>
    </div>
  );
}
