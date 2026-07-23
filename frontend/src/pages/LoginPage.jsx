import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../hooks/useTheme';
import { ShieldCheckIcon, SunIcon, MoonIcon } from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';

export default function LoginPage() {
  const { login, emergencyLogin } = useAuth();
  const { darkMode, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [showEmergency, setShowEmergency] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleAzureLogin = async () => {
    setLoading(true);
    try {
      await login();
    } catch (err) {
      toast.error('Login initiation failed');
      setLoading(false);
    }
  };

  const handleEmergencyLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await emergencyLogin(username, password);
      toast.success('Logged in successfully');
      navigate('/dashboard');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <button onClick={toggleTheme} className="absolute top-4 right-4 p-2 rounded-md text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
        {darkMode ? <SunIcon className="h-6 w-6" /> : <MoonIcon className="h-6 w-6" />}
      </button>

      <div className="card w-full max-w-md">
        <div className="text-center mb-8">
          <ShieldCheckIcon className="mx-auto h-16 w-16 text-primary-600" />
          <h1 className="mt-4 text-2xl font-bold text-gray-900 dark:text-white">Linux Access Portal</h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Enterprise Self-Service Access Management</p>
        </div>

        {!showEmergency ? (
          <div className="space-y-4">
            <button onClick={handleAzureLogin} disabled={loading} className="btn-primary w-full justify-center py-3">
              {loading ? 'Redirecting...' : 'Sign in with Microsoft Azure AD'}
            </button>
            <div className="relative">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200 dark:border-gray-700"></div></div>
              <div className="relative flex justify-center text-xs"><span className="bg-white dark:bg-gray-800 px-2 text-gray-500">or</span></div>
            </div>
            <button onClick={() => setShowEmergency(true)} className="btn-secondary w-full justify-center text-xs">
              Emergency Admin Login
            </button>
          </div>
        ) : (
          <form onSubmit={handleEmergencyLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Username</label>
              <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} className="input-field" required />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="input-field" required />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full justify-center py-3">
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
            <button type="button" onClick={() => setShowEmergency(false)} className="btn-secondary w-full justify-center text-xs">
              Back to Azure AD
            </button>
          </form>
        )}
      </div>

      <p className="mt-8 text-xs text-gray-500 dark:text-gray-400">Enterprise Linux Access Self-Service Portal v1.0</p>
    </div>
  );
}
