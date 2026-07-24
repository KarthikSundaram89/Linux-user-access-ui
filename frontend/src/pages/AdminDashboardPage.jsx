import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { adminAPI } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import {
  UsersIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  ServerStackIcon,
} from '@heroicons/react/24/outline';

const COLORS = ['#3b82f6', '#22c55e', '#ef4444', '#f59e0b', '#8b5cf6', '#06b6d4'];

export default function AdminDashboardPage() {
  const [stats, setStats] = useState(null);
  const [monthlyData, setMonthlyData] = useState([]);
  const [topServers, setTopServers] = useState([]);
  const [approvalSLA, setApprovalSLA] = useState([]);
  const [rotationStatus, setRotationStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [statsRes, monthlyRes, serversRes, slaRes, rotRes] = await Promise.all([
        adminAPI.dashboard(),
        adminAPI.chartMonthly().catch(() => ({ data: [] })),
        adminAPI.chartTopServers().catch(() => ({ data: [] })),
        adminAPI.chartApprovalSLA().catch(() => ({ data: [] })),
        adminAPI.rotationStatus().catch(() => ({ data: null })),
      ]);
      setStats(statsRes.data);
      setMonthlyData(monthlyRes.data || []);
      setTopServers(serversRes.data || []);
      setApprovalSLA(slaRes.data || []);
      setRotationStatus(rotRes.data);
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

      {/* Rotation Warnings (#10) */}
      {rotationStatus && rotationStatus.warnings?.length > 0 && (
        <div className="card border-yellow-300 dark:border-yellow-600">
          <h2 className="text-lg font-medium text-yellow-700 dark:text-yellow-400 mb-3">Credential Rotation Warnings</h2>
          <div className="space-y-2">
            {rotationStatus.warnings.map((w, i) => (
              <div key={i} className="flex items-center gap-3 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded">
                <ExclamationTriangleIcon className="h-5 w-5 text-yellow-500 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{w.name}</p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">{w.message}</p>
                </div>
                <span className={`ml-auto badge ${w.status === 'overdue' ? 'badge-danger' : 'badge-warning'}`}>{w.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Monthly Requests Chart */}
        <div className="card">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Monthly Requests</h2>
          {monthlyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={monthlyData}>
                <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="total" fill="#3b82f6" name="Total" radius={[4, 4, 0, 0]} />
                <Bar dataKey="approved" fill="#22c55e" name="Approved" radius={[4, 4, 0, 0]} />
                <Bar dataKey="rejected" fill="#ef4444" name="Rejected" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-500 text-sm">No data yet.</p>
          )}
        </div>

        {/* Top Servers Chart */}
        <div className="card">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Top Requested Servers</h2>
          {topServers.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={topServers.slice(0, 8)} layout="vertical">
                <XAxis type="number" tick={{ fontSize: 12 }} />
                <YAxis dataKey="ip_address" type="category" tick={{ fontSize: 11 }} width={120} />
                <Tooltip />
                <Bar dataKey="request_count" fill="#8b5cf6" name="Requests" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-500 text-sm">No data yet.</p>
          )}
        </div>

        {/* Approval SLA Chart */}
        <div className="card">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Approval SLA (Avg Hours)</h2>
          {approvalSLA.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={approvalSLA}>
                <XAxis dataKey="step_name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="avg_hours" fill="#f59e0b" name="Avg Hours" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-500 text-sm">No data yet.</p>
          )}
        </div>
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
