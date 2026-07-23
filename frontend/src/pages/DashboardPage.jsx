import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { requestsAPI, approvalsAPI } from '../services/api';
import {
  DocumentPlusIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  KeyIcon,
} from '@heroicons/react/24/outline';

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

export default function DashboardPage() {
  const { user } = useAuth();
  const [requests, setRequests] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [reqRes, apprRes] = await Promise.all([
        requestsAPI.list({ page: 1, page_size: 10 }),
        approvalsAPI.pending(),
      ]);
      setRequests(reqRes.data.items || []);
      setPendingApprovals(apprRes.data.count || 0);
    } catch (err) {
      console.error('Failed to load dashboard data', err);
    } finally {
      setLoading(false);
    }
  };

  const stats = [
    { name: 'Pending Requests', value: requests.filter(r => r.status === 'pending_approval').length, icon: ClockIcon, color: 'text-yellow-500' },
    { name: 'Active Access', value: requests.filter(r => r.status === 'provisioned').length, icon: CheckCircleIcon, color: 'text-green-500' },
    { name: 'Pending Approvals', value: pendingApprovals, icon: DocumentPlusIcon, color: 'text-blue-500' },
    { name: 'Rejected', value: requests.filter(r => r.status === 'rejected').length, icon: XCircleIcon, color: 'text-red-500' },
  ];

  if (loading) {
    return <div className="flex items-center justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div></div>;
  }

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Welcome, {user?.display_name}</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">Manage your Linux access requests and approvals</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.name} className="card flex items-center gap-4">
            <stat.icon className={`h-10 w-10 ${stat.color}`} />
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{stat.value}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">{stat.name}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Quick Actions</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <Link to="/requests/new?type=user_access" className="btn-secondary justify-center text-center flex-col gap-1 py-3">
            <KeyIcon className="h-5 w-5 mx-auto" />
            <span className="text-xs">User Access</span>
          </Link>
          <Link to="/requests/new?type=sudo_access" className="btn-secondary justify-center text-center flex-col gap-1 py-3">
            <ShieldIcon className="h-5 w-5 mx-auto" />
            <span className="text-xs">Sudo Access</span>
          </Link>
          <Link to="/requests/new?type=both" className="btn-secondary justify-center text-center flex-col gap-1 py-3">
            <DocumentPlusIcon className="h-5 w-5 mx-auto" />
            <span className="text-xs">Both</span>
          </Link>
          <Link to="/requests/new?type=renew_sudo" className="btn-secondary justify-center text-center flex-col gap-1 py-3">
            <ArrowPathIcon className="h-5 w-5 mx-auto" />
            <span className="text-xs">Renew Sudo</span>
          </Link>
          <Link to="/requests" className="btn-secondary justify-center text-center flex-col gap-1 py-3">
            <ClockIcon className="h-5 w-5 mx-auto" />
            <span className="text-xs">View Status</span>
          </Link>
          <Link to="/approvals" className="btn-secondary justify-center text-center flex-col gap-1 py-3">
            <CheckCircleIcon className="h-5 w-5 mx-auto" />
            <span className="text-xs">Approvals</span>
          </Link>
        </div>
      </div>

      {/* Recent Requests */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Requests</h2>
          <Link to="/requests" className="text-sm text-primary-600 hover:text-primary-700">View all</Link>
        </div>
        {requests.length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400 text-sm">No requests yet. Create your first access request.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Request ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {requests.slice(0, 5).map((req) => (
                  <tr key={req.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3">
                      <Link to={`/requests/${req.request_id}`} className="text-sm font-medium text-primary-600 hover:text-primary-700">{req.request_id}</Link>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{req.access_type.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-3"><StatusBadge status={req.status} /></td>
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{new Date(req.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function ShieldIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
    </svg>
  );
}
