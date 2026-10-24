import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Server,
  Search,
  ArrowUpDown,
  ExternalLink,
  PlusCircle,
  Clock,
  CheckCircle2,
} from 'lucide-react';
import { getCabinets, syntheticData } from '../api.js';
import StatusBadge from '../components/StatusBadge.jsx';
import { SkeletonRow } from '../components/Skeleton.jsx';

export default function CabinetList() {
  const [loading, setLoading] = useState(true);
  const [cabinets, setCabinets] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState('last_inspected');
  const [sortOrder, setSortOrder] = useState('desc');

  useEffect(() => {
    async function loadCabinets() {
      setLoading(true);
      try {
        const res = await getCabinets();
        if (Array.isArray(res) && res.length > 0) {
          setCabinets(res);
        } else {
          setCabinets(syntheticData.cabinets);
        }
      } catch {
        setCabinets(syntheticData.cabinets);
      } finally {
        setLoading(false);
      }
    }
    loadCabinets();
  }, []);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortOrder('asc');
    }
  };

  const filteredAndSortedCabinets = useMemo(() => {
    let result = cabinets.filter((cab) => {
      const q = searchQuery.toLowerCase();
      return (
        (cab.name || '').toLowerCase().includes(q) ||
        (cab.serial || '').toLowerCase().includes(q) ||
        (cab.cabinet_id || '').toLowerCase().includes(q)
      );
    });

    result.sort((a, b) => {
      let aVal = a[sortField] || '';
      let bVal = b[sortField] || '';
      if (typeof aVal === 'string') aVal = aVal.toLowerCase();
      if (typeof bVal === 'string') bVal = bVal.toLowerCase();

      if (aVal < bVal) return sortOrder === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortOrder === 'asc' ? 1 : -1;
      return 0;
    });

    return result;
  }, [cabinets, searchQuery, sortField, sortOrder]);

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="eyebrow">EQUIPMENT REGISTRY</div>
          <h1 className="page-title">Cabinet Fleet Registry</h1>
          <p className="page-desc">
            Enrolled electrical cabinets, current quality status, and historical inspection passports.
          </p>
        </div>

        <div>
          <Link to="/inspect" className="btn btn-accent">
            <PlusCircle size={15} />
            <span>New Inspection</span>
          </Link>
        </div>
      </div>

      {/* Filter and Search Panel */}
      <div className="panel" style={{ padding: '14px 20px', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: '1', maxWidth: '400px' }}>
            <Search size={16} color="var(--color-text-muted)" />
            <input
              type="text"
              className="form-input"
              placeholder="Search by cabinet name, serial, or ID…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search cabinets"
            />
          </div>

          <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
            Showing <strong>{filteredAndSortedCabinets.length}</strong> registered units
          </div>
        </div>
      </div>

      {/* Table Container */}
      <div className="panel" style={{ padding: 0 }}>
        {loading ? (
          <div style={{ padding: '20px' }}>
            <SkeletonRow count={4} height={48} />
          </div>
        ) : (
          <div className="table-container" style={{ border: 'none' }}>
            <table className="table" aria-label="Cabinet Fleet Table">
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('cabinet_id')}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      Cabinet ID <ArrowUpDown size={12} />
                    </span>
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('name')}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      Unit Name <ArrowUpDown size={12} />
                    </span>
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('serial')}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      Serial Number <ArrowUpDown size={12} />
                    </span>
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('status')}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      Quality Status <ArrowUpDown size={12} />
                    </span>
                  </th>
                  <th>Inspections</th>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('last_inspected')}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      Last Inspected <ArrowUpDown size={12} />
                    </span>
                  </th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredAndSortedCabinets.length === 0 ? (
                  <tr>
                    <td colSpan="7" style={{ textAlign: 'center', padding: '36px', color: 'var(--color-text-muted)' }}>
                      No electrical cabinets match your query.
                    </td>
                  </tr>
                ) : (
                  filteredAndSortedCabinets.map((cab) => (
                    <tr key={cab.cabinet_id}>
                      <td className="mono" style={{ fontWeight: 600, color: 'var(--color-navy)' }}>
                        <Link to={`/cabinets/${cab.cabinet_id}`} style={{ color: 'inherit', textDecoration: 'none' }}>
                          {cab.cabinet_id}
                        </Link>
                      </td>
                      <td style={{ fontWeight: 600 }}>{cab.name}</td>
                      <td className="mono">{cab.serial}</td>
                      <td>
                        <StatusBadge status={cab.status || 'review_required'} />
                      </td>
                      <td>
                        <span className="mono">{cab.inspections_count ?? 1} runs</span>
                      </td>
                      <td style={{ fontSize: '12px' }}>
                        {cab.last_inspected ? new Date(cab.last_inspected).toLocaleDateString() : '—'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Link
                          to={`/cabinets/${cab.cabinet_id}`}
                          className="btn btn-secondary btn-sm"
                          title="View Digital Quality Passport"
                        >
                          <span>Passport</span>
                          <ExternalLink size={12} />
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
