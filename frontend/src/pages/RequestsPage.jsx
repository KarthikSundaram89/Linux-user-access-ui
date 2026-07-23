import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { requestsAPI } from '../services/api';

function StatusBadge({ status }) {
  const colors = {
    pending_approval: 'badge-warning',
    approved: 'badge-info',
    provisioned: 'badge-success',
    rejected: 'badge-danger',
    cancelled: 'badge-gray',
    provisioning: 'badge-info',
    provisioning_failed: 'badge-danger',
    expired: 'badge-gray',
    revoked: 'badge-gray',
  };
  return <span className={colors[status] || 'badge-gray'}>{status.replace(/_/g, ' ')}</span>;
}

export default function RequestsPage() {
  const [requests, setRequests] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadRequests(); }, [page, statusFilter]);

  const loadRequests = async () => {
    setLoading(true);
    try {
      const params = { page, page_size: 20 };
      if (statusFilter) params.status = statusFilter;
      const res = await requestsAPI.list(params);
      setRequests(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch (err) {
      console.error('Failed to load requests', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Requests</h1>
        <Link to="/requests/new" className="btn-primary">New Request</Link>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="flex items-center gap-4">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Filter:</label>
          <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="input-field w-48">
            <option value="">All Statuses</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="approved">Approved</option>
            <option value="provisioned">Provisioned</option>
            <option value="rejected">Rejected</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <span className="text-sm text-gray-500 dark:text-gray-400">Total: {total}</span>
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden p-0">
        {loading ? (
          <div className="flex justify-center py-8"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div></div>
        ) : requests.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500 dark:text-gray-400">No requests found.</p>
            <Link to="/requests/new" className="btn-primary mt-4 inline-flex">Create Request</Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Request ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Environment</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Servers</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {requests.map((req) => (
                  <tr key={req.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3">
                      <Link to={`/requests/${req.request_id}`} className="text-sm font-medium text-primary-600 hover:text-primary-700">{req.request_id}</Link>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 capitalize">{req.access_type.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 capitalize">{req.environment.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-3"><StatusBadge status={req.status} /></td>
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{req.servers?.length || 0} server(s)</td>
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{new Date(req.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > 20 && (
        <div className="flex justify-center gap-2">
          <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page <= 1} className="btn-secondary text-sm">Previous</button>
          <span className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">Page {page}</span>
          <button onClick={() => setPage(p => p+1)} disabled={requests.length < 20} className="btn-secondary text-sm">Next</button>
        </div>
      )}
    </div>
  );
}
