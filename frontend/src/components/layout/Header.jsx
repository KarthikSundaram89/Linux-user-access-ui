import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';
import {
  Bars3Icon,
  MagnifyingGlassIcon,
  BellIcon,
  SunIcon,
  MoonIcon,
  ArrowRightOnRectangleIcon,
} from '@heroicons/react/24/outline';
import { searchAPI } from '../../services/api';

export default function Header({ onMenuClick }) {
  const { user, logout } = useAuth();
  const { darkMode, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    try {
      const res = await searchAPI.search(searchQuery);
      setSearchResults(res.data);
    } catch (err) {
      console.error('Search failed', err);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <header className="sticky top-0 z-30 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
      <div className="flex h-16 items-center gap-x-4 px-4 sm:px-6 lg:px-8">
        <button onClick={onMenuClick} className="lg:hidden -m-2.5 p-2.5 text-gray-700 dark:text-gray-200">
          <Bars3Icon className="h-6 w-6" />
        </button>

        <div className="flex flex-1 gap-x-4 items-center">
          <form onSubmit={handleSearch} className="relative flex-1 max-w-md">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search users, requests, servers..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="input-field pl-10"
            />
          </form>
        </div>

        <div className="flex items-center gap-x-3">
          <button onClick={toggleTheme} className="p-2 rounded-md text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
            {darkMode ? <SunIcon className="h-5 w-5" /> : <MoonIcon className="h-5 w-5" />}
          </button>
          <button className="relative p-2 rounded-md text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
            <BellIcon className="h-5 w-5" />
            <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-red-500"></span>
          </button>
          <button onClick={handleLogout} className="p-2 rounded-md text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200" title="Logout">
            <ArrowRightOnRectangleIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Search Results Dropdown */}
      {searchResults && (
        <div className="absolute right-4 left-4 md:left-64 mt-1 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-4 max-h-64 overflow-y-auto z-50">
          <button onClick={() => setSearchResults(null)} className="float-right text-gray-400 hover:text-gray-600 text-sm">Close</button>
          {searchResults.users?.length > 0 && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">Users</h4>
              {searchResults.users.map(u => (
                <p key={u.id} className="text-sm text-gray-700 dark:text-gray-300">{u.name} - {u.email}</p>
              ))}
            </div>
          )}
          {searchResults.requests?.length > 0 && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">Requests</h4>
              {searchResults.requests.map(r => (
                <p key={r.id} className="text-sm text-gray-700 dark:text-gray-300 cursor-pointer hover:text-primary-600" onClick={() => { navigate(`/requests/${r.request_id}`); setSearchResults(null); }}>{r.request_id} - {r.status}</p>
              ))}
            </div>
          )}
          {searchResults.servers?.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">Servers</h4>
              {searchResults.servers.map(s => (
                <p key={s.id} className="text-sm text-gray-700 dark:text-gray-300">{s.hostname || s.ip}</p>
              ))}
            </div>
          )}
          {!searchResults.users?.length && !searchResults.requests?.length && !searchResults.servers?.length && (
            <p className="text-sm text-gray-500">No results found.</p>
          )}
        </div>
      )}
    </header>
  );
}
