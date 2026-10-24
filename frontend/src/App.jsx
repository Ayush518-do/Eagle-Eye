import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import Dashboard from './pages/Dashboard.jsx';
import NewInspection from './pages/NewInspection.jsx';
import Results from './pages/Results.jsx';
import CabinetList from './pages/CabinetList.jsx';
import CabinetHistory from './pages/CabinetHistory.jsx';
import Analytics from './pages/Analytics.jsx';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/inspect" element={<NewInspection />} />
          <Route path="/inspections/:inspectionId" element={<Results />} />
          <Route path="/cabinets" element={<CabinetList />} />
          <Route path="/cabinets/:cabinetId" element={<CabinetHistory />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route
            path="*"
            element={
              <div className="panel" style={{ textAlign: 'center', padding: '48px 24px' }}>
                <h2 style={{ marginBottom: '8px' }}>Page Not Found</h2>
                <p className="page-desc" style={{ marginBottom: '20px' }}>
                  The requested industrial inspection page or route does not exist.
                </p>
                <Link to="/" className="btn btn-primary">
                  Return to Dashboard
                </Link>
              </div>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
