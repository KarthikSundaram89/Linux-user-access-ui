import React, { useEffect, useState } from 'react';
import { adminAPI } from '../services/api';

export default function AdminAuditPage() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadLogs(); }, [page]);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const res = await adminAPI.auditLogs({ page, page_size: 50 });
      setLogs(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Audit Logs</h1>
        <span className="text-sm text-gray-500">Total: {total} entries</span>
      </div>

      <div className="card overflow-hidden p-0">
        {loading ? (
          <div className="flex justify-center py-8"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Timestamp</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Action</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Resource</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {logs.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">{new Date(log.created_at).toLocaleString()}</td>
                    <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{log.user_email || 'System'}</td>
                    <td className="px-4 py-3"><span className="badge-info">{log.action}</span></td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{log.resource_type} {log.resource_id ? `#${log.resource_id}` : ''}</td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 max-w-xs truncate">{log.description || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {total > 50 && (
        <div className="flex justify-center gap-2">
          <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page <= 1} className="btn-secondary text-sm">Previous</button>
          <span className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">Page {page}</span>
          <button onClick={() => setPage(p => p+1)} disabled={logs.length < 50} className="btn-secondary text-sm">Next</button>
        </div>
      )}
    </div>
  );
}
