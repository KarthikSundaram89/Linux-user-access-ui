import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { requestsAPI, serversAPI } from '../services/api';
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
  const [serverDetails, setServerDetails] = useState({});  // EC2 inventory details keyed by identifier
  const [lookupLoading, setLookupLoading] = useState(false);

  const IP_REGEX = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/;

  const addServers = async () => {
    const lines = form.serverInput.split('\n').map(l => l.trim()).filter(Boolean);
    const newServers = [];
    const duplicates = [];
    const invalid = [];

    lines.forEach(line => {
      if (!IP_REGEX.test(line)) {
        invalid.push(line);
        return;
      }
      // Validate each octet is 0-255
      const octets = line.split('.');
      const validOctets = octets.every(o => parseInt(o, 10) >= 0 && parseInt(o, 10) <= 255);
      if (!validOctets) {
        invalid.push(line);
        return;
      }
      const existing = servers.find(s => s.ip_address === line);
      if (existing) {
        duplicates.push(line);
      } else {
        newServers.push({ ip_address: line });
      }
    });

    if (invalid.length) toast.error(`Invalid IP address(es): ${invalid.join(', ')}. Only IPv4 addresses are allowed.`);
    if (duplicates.length) toast.error(`Duplicate IP(s): ${duplicates.join(', ')}`);
    if (newServers.length) {
      setServers([...servers, ...newServers]);
      setForm({ ...form, serverInput: '' });

      // Automatically look up servers in EC2 inventory
      setLookupLoading(true);
      try {
        const identifiers = newServers.map(s => s.ip_address);
        const res = await serversAPI.lookup(identifiers);
        const details = { ...serverDetails };
        for (const result of res.data.results) {
          details[result.identifier] = result;
        }
        setServerDetails(details);
        const found = res.data.found || 0;
        const notFound = res.data.not_found || 0;
        if (found > 0) toast.success(`${found} server(s) found in EC2 inventory`);
        if (notFound > 0) toast(`${notFound} IP(s) not found in EC2 inventory`, { icon: '⚠️' });
      } catch (err) {
        console.error('Server lookup failed', err);
        toast.error('Could not look up servers in EC2 inventory');
      } finally {
        setLookupLoading(false);
      }
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
        servers: servers.map(s => ({ ip_address: s.ip_address })),
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
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Enter server IP addresses (one per line)</label>
            <textarea value={form.serverInput} onChange={(e) => setForm({...form, serverInput: e.target.value})} className="input-field font-mono" rows="4" placeholder={"10.10.10.5\n10.10.10.8\n172.16.0.100\n192.168.1.50"} />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Only IPv4 addresses are accepted. Enter one IP per line.</p>
          </div>
          <button type="button" onClick={addServers} className="btn-secondary">Add Servers</button>

          {/* CSV Upload */}
          <div className="flex items-center gap-3 mt-2">
            <label className="btn-secondary cursor-pointer text-sm">
              Upload CSV
              <input type="file" accept=".csv,.txt" className="hidden" onChange={async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                try {
                  const res = await requestsAPI.uploadCSV(file);
                  const { valid_ips, invalid, duplicates, total_valid } = res.data;
                  if (total_valid > 0) {
                    const newServers = valid_ips.filter(ip => !servers.find(s => s.ip_address === ip)).map(ip => ({ ip_address: ip }));
                    setServers([...servers, ...newServers]);
                    toast.success(`${newServers.length} IP(s) added from CSV`);
                    // Auto-lookup
                    if (newServers.length > 0) {
                      setLookupLoading(true);
                      try {
                        const lookupRes = await serversAPI.lookup(newServers.map(s => s.ip_address));
                        const details = { ...serverDetails };
                        for (const result of lookupRes.data.results) { details[result.identifier] = result; }
                        setServerDetails(details);
                      } catch (err) { console.error(err); }
                      setLookupLoading(false);
                    }
                  }
                  if (invalid.length) toast.error(`${invalid.length} invalid entries skipped`);
                  if (duplicates.length) toast(`${duplicates.length} duplicates skipped`, { icon: '⚠️' });
                } catch (err) {
                  toast.error('Failed to parse CSV file');
                }
                e.target.value = '';
              }} />
            </label>
            <span className="text-xs text-gray-500 dark:text-gray-400">Upload a CSV with IP addresses (one per line or column named "ip")</span>
          </div>

          {servers.length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Servers ({servers.length}):</p>
              {lookupLoading && <p className="text-xs text-primary-600 mb-2 animate-pulse">Looking up servers in EC2 inventory...</p>}

              {/* Server details table */}
              <div className="overflow-x-auto border border-gray-200 dark:border-gray-600 rounded-lg">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-700">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Server</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Account</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Region</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Name</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Application</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">OS</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Status</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {servers.map((s, i) => {
                      const identifier = s.ip_address;
                      const detail = serverDetails[identifier];
                      const found = detail && detail.found;
                      return (
                        <tr key={i} className={!found ? 'bg-yellow-50 dark:bg-yellow-900/10' : ''}>
                          <td className="px-3 py-2 font-mono text-gray-900 dark:text-white">{identifier}</td>
                          <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{found ? detail.account_name : <span className="text-yellow-600 text-xs">Not in inventory</span>}</td>
                          <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{found ? detail.region : '-'}</td>
                          <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{found ? detail.name_tag : '-'}</td>
                          <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{found ? detail.application_tag : '-'}</td>
                          <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{found ? detail.os_tag : '-'}</td>
                          <td className="px-3 py-2">
                            {found && detail.live_status ? (
                              <span className={`badge ${detail.live_status === 'running' ? 'badge-success' : detail.live_status === 'stopped' ? 'badge-danger' : 'badge-warning'}`}>
                                {detail.live_status}
                              </span>
                            ) : found ? (
                              <span className="badge badge-gray">unknown</span>
                            ) : null}
                          </td>
                          <td className="px-3 py-2">
                            <button type="button" onClick={() => removeServer(i)} className="text-red-400 hover:text-red-600 text-lg">&times;</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Submit */}
        <div className="flex justify-end gap-3">
          <button type="button" onClick={() => navigate('/requests')} className="btn-secondary">Cancel</button>
          <button type="button" disabled={loading || servers.length === 0} onClick={async () => {
            setLoading(true);
            try {
              const payload = { access_type: form.access_type, environment: form.environment, purpose: form.purpose || 'Draft - to be completed', business_justification: form.business_justification || 'Draft - to be completed', application_name: form.application_name || null, project_name: form.project_name || null, servers: servers.map(s => ({ ip_address: s.ip_address })), is_renewal: form.access_type === 'renew_sudo' };
              const res = await requestsAPI.saveDraft(payload);
              toast.success(`Draft saved: ${res.data.request_id}`);
              navigate(`/requests/${res.data.request_id}`);
            } catch (err) { toast.error('Failed to save draft'); }
            setLoading(false);
          }} className="btn-secondary">Save as Draft</button>
          <button type="submit" disabled={loading} className="btn-primary">{loading ? 'Submitting...' : 'Submit Request'}</button>
        </div>
      </form>
    </div>
  );
}
