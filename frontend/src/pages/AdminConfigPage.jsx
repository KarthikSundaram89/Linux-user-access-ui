import React, { useEffect, useState } from 'react';
import { adminAPI } from '../services/api';
import toast from 'react-hot-toast';

const categories = ['azure_ad', 'smtp', 'ssh', 'sudo', 'branding'];

export default function AdminConfigPage() {
  const [configs, setConfigs] = useState([]);
  const [sshKeys, setSSHKeys] = useState([]);
  const [scripts, setScripts] = useState([]);
  const [workflow, setWorkflow] = useState([]);
  const [activeTab, setActiveTab] = useState('config');
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [cfgRes, keysRes, scriptsRes, wfRes] = await Promise.all([
        adminAPI.config(),
        adminAPI.sshKeys(),
        adminAPI.scripts(),
        adminAPI.workflow(),
      ]);
      setConfigs(cfgRes.data || []);
      setSSHKeys(keysRes.data || []);
      setScripts(scriptsRes.data || []);
      setWorkflow(wfRes.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    { id: 'config', label: 'System Config' },
    { id: 'ssh', label: 'SSH Keys' },
    { id: 'scripts', label: 'Provisioning Scripts' },
    { id: 'workflow', label: 'Approval Workflow' },
  ];

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div></div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Configuration</h1>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-4">
          {tabs.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`pb-3 text-sm font-medium border-b-2 transition-colors ${activeTab === tab.id ? 'border-primary-500 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'}`}>
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* System Config Tab */}
      {activeTab === 'config' && (
        <div className="card">
          {configs.length === 0 ? (
            <p className="text-gray-500 text-sm">No configurations found. Configurations are created on first setup.</p>
          ) : (
            <div className="space-y-3">
              {configs.map(cfg => (
                <div key={cfg.id} className="flex items-center justify-between border-b border-gray-100 dark:border-gray-700 pb-2">
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{cfg.key}</p>
                    <p className="text-xs text-gray-500">{cfg.category} - {cfg.description || ''}</p>
                  </div>
                  <span className="text-sm text-gray-600 dark:text-gray-300 font-mono">{cfg.value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* SSH Keys Tab */}
      {activeTab === 'ssh' && (
        <div className="card">
          <h3 className="text-md font-medium text-gray-900 dark:text-white mb-4">SSH Keys</h3>
          {sshKeys.length === 0 ? (
            <p className="text-gray-500 text-sm">No SSH keys uploaded. Upload a key to enable provisioning.</p>
          ) : (
            <div className="space-y-2">
              {sshKeys.map(key => (
                <div key={key.id} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 rounded">
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{key.name}</p>
                    <p className="text-xs text-gray-500">{key.key_type} | {key.is_default ? 'Default' : 'Standard'}</p>
                  </div>
                  <span className={key.is_active ? 'badge-success' : 'badge-danger'}>{key.is_active ? 'Active' : 'Inactive'}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Scripts Tab */}
      {activeTab === 'scripts' && (
        <div className="card">
          <h3 className="text-md font-medium text-gray-900 dark:text-white mb-4">Provisioning Scripts</h3>
          {scripts.length === 0 ? (
            <p className="text-gray-500 text-sm">No scripts configured.</p>
          ) : (
            <div className="space-y-4">
              {scripts.map(script => (
                <div key={script.id} className="border border-gray-200 dark:border-gray-600 rounded p-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{script.name}</p>
                    <span className="badge-info">{script.script_type}</span>
                  </div>
                  <pre className="text-xs bg-gray-50 dark:bg-gray-900 p-2 rounded overflow-x-auto">{script.script_content}</pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Workflow Tab */}
      {activeTab === 'workflow' && (
        <div className="card">
          <h3 className="text-md font-medium text-gray-900 dark:text-white mb-4">Approval Workflow Steps</h3>
          {workflow.length === 0 ? (
            <p className="text-gray-500 text-sm">Default workflow is used. Configure steps here to customize.</p>
          ) : (
            <div className="space-y-2">
              {workflow.map((step, idx) => (
                <div key={step.id} className="flex items-center gap-4 p-3 bg-gray-50 dark:bg-gray-700 rounded">
                  <span className="text-lg font-bold text-primary-500">{step.step_order}</span>
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">{step.name}</p>
                    <p className="text-xs text-gray-500">{step.approver_role} | {step.approval_type} | Timeout: {step.timeout_hours}h</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
