import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { requestsAPI } from '../services/api';
import toast from 'react-hot-toast';

const accessTypes = [
  { value: 'user_access', label: 'Linux User Access', desc: 'Creates a user account on the server' },
  { value: 'sudo_access', label: 'Sudo Access', desc: 'Provides sudo privileges (90 days)' },
  { value: 'both', label: 'Both (User + Sudo)', desc: 'Creates user account and grants sudo' },
  { value: 'renew_sudo', label: 'Renew Existing Sudo', desc: 'Extend sudo by another 90 days' },
];

const environments = [
  { value: 'production', label: 'Production' },
  { value: 'non_production', label: 'Non-Production' },
  { value: 'development', label: 'Development' },
  { value: 'dr', label: 'DR (Disaster Recovery)' },
  { value: 'uat', label: 'UAT' },
];

export default function NewRequestPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    access_type: searchParams.get('type') || 'user_access',
    environment: 'production',
    purpose: '',
    business_justification: '',
    application_name: '',
    project_name: '',
    serverInput: '',
  });
  const [servers, setServers] = useState([]);

  const addServers = () => {
    const lines = form.serverInput.split('\n').map(l => l.trim()).filter(Boolean);
    const newServers = [];
    const duplicates = [];

    lines.forEach(line => {
      const isIP = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(line);
      const existing = servers.find(s => (isIP ? s.ip_address : s.hostname) === line);
      if (existing) {
        duplicates.push(line);
      } else {
        newServers.push(isIP ? { ip_address: line } : { hostname: line });
      }
    });

    if (duplicates.length) toast.error(`Duplicate servers: ${duplicates.join(', ')}`);
    if (newServers.length) {
      setServers([...servers, ...newServers]);
      setForm({ ...form, serverInput: '' });
    }
  };

  const removeServer = (index) => {
    setServers(servers.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (servers.length === 0) {
      toast.error('Add at least one server');
      return;
    }
    setLoading(true);
    try {
      const payload = {
        access_type: form.access_type,
        environment: form.environment,
        purpose: form.purpose,
        business_justification: form.business_justification,
        application_name: form.application_name || null,
        project_name: form.project_name || null,
        servers,
        is_renewal: form.access_type === 'renew_sudo',
      };
      const res = await requestsAPI.create(payload);
      toast.success(`Request ${res.data.request_id} submitted!`);
      navigate(`/requests/${res.data.request_id}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit request');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">New Access Request</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Access Type */}
        <div className="card">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Access Type</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {accessTypes.map(type => (
              <label key={type.value} className={`relative flex cursor-pointer rounded-lg border p-4 ${form.access_type === type.value ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' : 'border-gray-300 dark:border-gray-600'}`}>
                <input type="radio" name="access_type" value={type.value} checked={form.access_type === type.value} onChange={(e) => setForm({...form, access_type: e.target.value})} className="sr-only" />
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{type.label}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{type.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Environment & Details */}
        <div className="card space-y-4">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white">Request Details</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Environment *</label>
            <select value={form.environment} onChange={(e) => setForm({...form, environment: e.target.value})} className="input-field">
              {environments.map(env => <option key={env.value} value={env.value}>{env.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Purpose *</label>
            <textarea value={form.purpose} onChange={(e) => setForm({...form, purpose: e.target.value})} className="input-field" rows="2" required minLength={10} placeholder="Brief description of why access is needed" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Business Justification *</label>
            <textarea value={form.business_justification} onChange={(e) => setForm({...form, business_justification: e.target.value})} className="input-field" rows="3" required minLength={10} placeholder="Detailed business justification for this access" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Application Name</label>
              <input type="text" value={form.application_name} onChange={(e) => setForm({...form, application_name: e.target.value})} className="input-field" placeholder="Optional" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Project Name</label>
              <input type="text" value={form.project_name} onChange={(e) => setForm({...form, project_name: e.target.value})} className="input-field" placeholder="Optional" />
            </div>
          </div>
        </div>

        {/* Servers */}
        <div className="card space-y-4">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white">Server Details</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Enter hostnames or IP addresses (one per line)</label>
            <textarea value={form.serverInput} onChange={(e) => setForm({...form, serverInput: e.target.value})} className="input-field font-mono" rows="4" placeholder={"10.10.10.5\n10.10.10.8\napp01\ndb01"} />
          </div>
          <button type="button" onClick={addServers} className="btn-secondary">Add Servers</button>

          {servers.length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Servers ({servers.length}):</p>
              <div className="flex flex-wrap gap-2">
                {servers.map((s, i) => (
                  <span key={i} className="inline-flex items-center gap-1 rounded-full bg-gray-100 dark:bg-gray-700 px-3 py-1 text-sm">
                    {s.hostname || s.ip_address}
                    <button type="button" onClick={() => removeServer(i)} className="text-gray-400 hover:text-red-500">&times;</button>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Submit */}
        <div className="flex justify-end gap-3">
          <button type="button" onClick={() => navigate('/requests')} className="btn-secondary">Cancel</button>
          <button type="submit" disabled={loading} className="btn-primary">{loading ? 'Submitting...' : 'Submit Request'}</button>
        </div>
      </form>
    </div>
  );
}
