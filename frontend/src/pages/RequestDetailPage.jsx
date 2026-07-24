import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { requestsAPI, approvalsAPI } from '../services/api';
import toast from 'react-hot-toast';

function StatusBadge({ status }) {
  const colors = {
    pending_approval: 'badge-warning',
    approved: 'badge-info',
    provisioned: 'badge-success',
    rejected: 'badge-danger',
    cancelled: 'badge-gray',
    provisioning: 'badge-info',
    provisioning_failed: 'badge-danger',
    pending: 'badge-warning',
  };
  return <span className={colors[status] || 'badge-gray'}>{status.replace(/_/g, ' ')}</span>;
}

export default function RequestDetailPage() {
  const { requestId } = useParams();
  const navigate = useNavigate();
  const [request, setRequest] = useState(null);
  const [approvalHistory, setApprovalHistory] = useState(null);
  const [approvalComments, setApprovalComments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, [requestId]);

  const loadData = async () => {
    try {
      const [reqRes, histRes, commRes] = await Promise.all([
        requestsAPI.get(requestId),
        approvalsAPI.history(requestId).catch(() => null),
        approvalsAPI.comments(requestId).catch(() => null),
      ]);
      setRequest(reqRes.data);
      if (histRes) setApprovalHistory(histRes.data);
      if (commRes) setApprovalComments(commRes.data.comments || []);
    } catch (err) {
      toast.error('Failed to load request details');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!confirm('Are you sure you want to cancel this request?')) return;
    try {
      await requestsAPI.cancel(requestId);
      toast.success('Request cancelled');
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to cancel');
    }
  };

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div></div>;
  if (!request) return <div className="text-center py-12 text-gray-500">Request not found.</div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{request.request_id}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Created {new Date(request.created_at).toLocaleString()}</p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={request.status} />
          {request.status === 'pending_approval' && (
            <button onClick={handleCancel} className="btn-danger text-sm">Cancel Request</button>
          )}
          {(request.status === 'provisioning_failed' || request.status === 'partially_provisioned') && (
            <button onClick={async () => {
              try {
                const res = await requestsAPI.retry(requestId);
                toast.success(`Retried ${res.data.total} server(s): ${res.data.succeeded} succeeded`);
                loadData();
              } catch (err) { toast.error(err.response?.data?.detail || 'Retry failed'); }
            }} className="btn-primary text-sm">Retry Failed Servers</button>
          )}
          {request.status === 'draft' && (
            <button onClick={async () => {
              try {
                await requestsAPI.submitDraft(requestId);
                toast.success('Draft submitted for approval');
                loadData();
              } catch (err) { toast.error(err.response?.data?.detail || 'Submit failed'); }
            }} className="btn-primary text-sm">Submit Draft</button>
          )}
          <button onClick={async () => {
            try {
              const res = await requestsAPI.clone(requestId);
              toast.success(`Cloned as draft: ${res.data.request_id}`);
              navigate(`/requests/${res.data.request_id}`);
            } catch (err) { toast.error('Clone failed'); }
          }} className="btn-secondary text-sm">Request Again</button>
        </div>
      </div>

      {/* Request Details */}
      <div className="card">
        <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Request Details</h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div><dt className="text-sm text-gray-500 dark:text-gray-400">Access Type</dt><dd className="text-sm font-medium text-gray-900 dark:text-white capitalize">{request.access_type.replace(/_/g, ' ')}</dd></div>
          <div><dt className="text-sm text-gray-500 dark:text-gray-400">Environment</dt><dd className="text-sm font-medium text-gray-900 dark:text-white capitalize">{request.environment.replace(/_/g, ' ')}</dd></div>
          <div><dt className="text-sm text-gray-500 dark:text-gray-400">Application</dt><dd className="text-sm font-medium text-gray-900 dark:text-white">{request.application_name || 'N/A'}</dd></div>
          <div><dt className="text-sm text-gray-500 dark:text-gray-400">Project</dt><dd className="text-sm font-medium text-gray-900 dark:text-white">{request.project_name || 'N/A'}</dd></div>
          {request.sudo_expiry_date && (
            <div><dt className="text-sm text-gray-500 dark:text-gray-400">Sudo Expiry</dt><dd className="text-sm font-medium text-gray-900 dark:text-white">{new Date(request.sudo_expiry_date).toLocaleDateString()}</dd></div>
          )}
        </dl>
        <div className="mt-4">
          <dt className="text-sm text-gray-500 dark:text-gray-400">Purpose</dt>
          <dd className="text-sm text-gray-900 dark:text-white mt-1">{request.purpose}</dd>
        </div>
        <div className="mt-4">
          <dt className="text-sm text-gray-500 dark:text-gray-400">Business Justification</dt>
          <dd className="text-sm text-gray-900 dark:text-white mt-1">{request.business_justification}</dd>
        </div>
      </div>

      {/* Servers */}
      <div className="card">
        <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Servers ({request.servers?.length})</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Server</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Details</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Provisioned At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {request.servers?.map((server) => (
                <tr key={server.id} className={server.provisioning_status === 'failed' ? 'bg-red-50 dark:bg-red-900/10' : ''}>
                  <td className="px-4 py-2 text-sm text-gray-900 dark:text-white font-mono">{server.hostname || server.ip_address}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={server.provisioning_status} />
                  </td>
                  <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 max-w-sm">
                    {server.provisioning_message ? (
                      <span className={server.provisioning_status === 'failed' ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}>
                        {server.provisioning_message}
                      </span>
                    ) : '-'}
                  </td>
                  <td className="px-4 py-2 text-sm text-gray-500">{server.provisioned_at ? new Date(server.provisioned_at).toLocaleString() : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {request.servers?.some(s => s.provisioning_status === 'failed') && (
          <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
            <p className="text-sm text-red-700 dark:text-red-300 font-medium">Some servers failed provisioning. Check the error details above or contact your administrator.</p>
          </div>
        )}
      </div>

      {/* Approval Timeline */}
      {approvalHistory && approvalHistory.steps?.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Approval Timeline</h2>
          <div className="space-y-4">
            {approvalHistory.steps.map((step) => (
              <div key={step.id} className="flex items-start gap-3">
                <div className={`mt-1 h-3 w-3 rounded-full ${step.status === 'approved' ? 'bg-green-500' : step.status === 'rejected' ? 'bg-red-500' : step.status === 'pending' ? 'bg-yellow-500' : 'bg-gray-400'}`} />
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{step.step_name}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{step.approver_email} - <StatusBadge status={step.status} /></p>
                  {step.completed_at && <p className="text-xs text-gray-400 mt-0.5">{new Date(step.completed_at).toLocaleString()}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Approval Comments (#7) */}
      {approvalComments.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Approver Comments</h2>
          <div className="space-y-3">
            {approvalComments.map((comment, idx) => (
              <div key={idx} className="border-l-4 border-primary-400 pl-4 py-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium text-gray-900 dark:text-white">{comment.approver_name}</span>
                  <span className="text-gray-400">|</span>
                  <span className="text-gray-500 text-xs">{comment.step_name}</span>
                  <span className="text-gray-400">|</span>
                  <StatusBadge status={comment.action} />
                </div>
                <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{comment.comments}</p>
                <p className="mt-1 text-xs text-gray-400">{comment.created_at ? new Date(comment.created_at).toLocaleString() : ''}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <button onClick={() => navigate('/requests')} className="btn-secondary">Back to Requests</button>
    </div>
  );
}
