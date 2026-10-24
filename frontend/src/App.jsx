import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import Dashboard from './pages/Dashboard.jsx';
import NewInspection from './pages/NewInspection.jsx';
import Results from './pages/Results.jsx';
import CabinetHistory from './pages/CabinetHistory.jsx';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/inspect" element={<NewInspection />} />
          <Route path="/inspections/:inspectionId" element={<Results />} />
          <Route path="/cabinets/:cabinetId" element={<CabinetHistory />} />
          <Route path="*" element={<p className="panel">Page not found.</p>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
