import React, { useEffect, useState } from 'react';
import { approvalsAPI } from '../services/api';
import toast from 'react-hot-toast';

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionModal, setActionModal] = useState(null);
  const [comments, setComments] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => { loadApprovals(); }, []);

  const loadApprovals = async () => {
    try {
      const res = await approvalsAPI.pending();
      setApprovals(res.data.pending_approvals || []);
    } catch (err) {
      console.error('Failed to load approvals', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (action) => {
    if (!actionModal) return;
    setActionLoading(true);
    try {
      await approvalsAPI.action(actionModal.step.id, { action, comments: comments || null });
      toast.success(`Request ${action}`);
      setActionModal(null);
      setComments('');
      loadApprovals();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Action failed');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div></div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Pending Approvals</h1>

      {approvals.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-gray-500 dark:text-gray-400">No pending approvals. You're all caught up!</p>
        </div>
      ) : (
        <div className="space-y-4">
          {approvals.map(({ step, request_id }) => (
            <div key={step.id} className="card">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-primary-600">{request_id}</p>
                  <p className="text-lg font-semibold text-gray-900 dark:text-white mt-1">{step.step_name}</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Step {step.step_order} - {step.approval_type}</p>
                  <p className="text-xs text-gray-400 mt-1">Assigned to: {step.approver_email}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setActionModal({ step, request_id })} className="btn-success text-sm">Approve</button>
                  <button onClick={() => setActionModal({ step, request_id, reject: true })} className="btn-danger text-sm">Reject</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Action Modal */}
      {actionModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              {actionModal.reject ? 'Reject' : 'Approve'} Request: {actionModal.request_id}
            </h3>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Comments</label>
              <textarea value={comments} onChange={(e) => setComments(e.target.value)} className="input-field" rows="3" placeholder="Add your comments..." />
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => { setActionModal(null); setComments(''); }} className="btn-secondary">Cancel</button>
              {!actionModal.reject && (
                <button onClick={() => handleAction('approved')} disabled={actionLoading} className="btn-success">
                  {actionLoading ? 'Processing...' : 'Approve'}
                </button>
              )}
              {actionModal.reject && (
                <button onClick={() => handleAction('rejected')} disabled={actionLoading} className="btn-danger">
                  {actionLoading ? 'Processing...' : 'Reject'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
