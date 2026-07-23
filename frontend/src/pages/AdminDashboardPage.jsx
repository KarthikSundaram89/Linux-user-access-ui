import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { adminAPI, reportsAPI } from '../services/api';
import {
  UsersIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  ServerStackIcon,
} from '@heroicons/react/24/outline';

export default function AdminDashboardPage() {
  const [stats, setStats] = useState(null);
  const [trends, setTrends] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [statsRes, trendsRes] = await Promise.all([
        adminAPI.dashboard(),
        reportsAPI.monthlyTrends(),
      ]);
      setStats(statsRes.data);
      setTrends(trendsRes.data.trends || []);
    } catch (err) {
      console.error('Failed to load admin dashboard', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div></div>;

  const statCards = stats ? [
    { name: 'Total Users', value: stats.total_users, icon: UsersIcon, color: 'text-blue-500' },
    { name: 'Pending Requests', value: stats.pending_requests, icon: ClockIcon, color: 'text-yellow-500' },
    { name: 'Approved/Active', value: stats.approved_requests, icon: CheckCircleIcon, color: 'text-green-500' },
    { name: 'Rejected', value: stats.rejected_requests, icon: XCircleIcon, color: 'text-red-500' },
    { name: 'Provisioning Failures', value: stats.provisioning_failures, icon: ExclamationTriangleIcon, color: 'text-orange-500' },
    { name: 'Expiring Sudo', value: stats.expiring_sudo, icon: ClockIcon, color: 'text-purple-500' },
  ] : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Admin Dashboard</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {statCards.map((stat) => (
          <div key={stat.name} className="card flex items-center gap-4">
            <stat.icon className={`h-10 w-10 ${stat.color}`} />
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{stat.value}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">{stat.name}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Monthly Trends */}
      <div className="card">
        <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Monthly Request Trends</h2>
        {trends.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Month</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Requests</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Visual</th>
                </tr>
              </thead>
              <tbody>
                {trends.map((t) => (
                  <tr key={t.month}>
                    <td className="px-4 py-2 text-sm text-gray-900 dark:text-white">{t.month}</td>
                    <td className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300">{t.count}</td>
                    <td className="px-4 py-2">
                      <div className="h-4 rounded bg-primary-100 dark:bg-primary-900/30">
                        <div className="h-4 rounded bg-primary-500" style={{ width: `${Math.min(100, (t.count / Math.max(...trends.map(tr => tr.count))) * 100)}%` }}></div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500 dark:text-gray-400 text-sm">No data yet.</p>
        )}
      </div>

      {/* Quick Links */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link to="/admin/users" className="card hover:border-primary-500 transition-colors text-center">
          <UsersIcon className="h-8 w-8 text-primary-500 mx-auto" />
          <p className="mt-2 font-medium text-gray-900 dark:text-white">Manage Users</p>
        </Link>
        <Link to="/admin/config" className="card hover:border-primary-500 transition-colors text-center">
          <ServerStackIcon className="h-8 w-8 text-primary-500 mx-auto" />
          <p className="mt-2 font-medium text-gray-900 dark:text-white">Configuration</p>
        </Link>
        <Link to="/reports" className="card hover:border-primary-500 transition-colors text-center">
          <CheckCircleIcon className="h-8 w-8 text-primary-500 mx-auto" />
          <p className="mt-2 font-medium text-gray-900 dark:text-white">Reports</p>
        </Link>
      </div>
    </div>
  );
}
