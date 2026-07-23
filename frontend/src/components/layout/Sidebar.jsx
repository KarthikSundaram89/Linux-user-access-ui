import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import {
  HomeIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  CogIcon,
  ChartBarIcon,
  UsersIcon,
  ShieldCheckIcon,
  ClipboardDocumentListIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: HomeIcon },
  { name: 'My Requests', href: '/requests', icon: DocumentTextIcon },
  { name: 'New Request', href: '/requests/new', icon: ClipboardDocumentListIcon },
  { name: 'Approvals', href: '/approvals', icon: CheckCircleIcon },
];

const adminNavigation = [
  { name: 'Admin Dashboard', href: '/admin', icon: ShieldCheckIcon },
  { name: 'Users', href: '/admin/users', icon: UsersIcon },
  { name: 'Configuration', href: '/admin/config', icon: CogIcon },
  { name: 'Audit Logs', href: '/admin/audit', icon: ClipboardDocumentListIcon },
  { name: 'Reports', href: '/reports', icon: ChartBarIcon },
];

export default function Sidebar({ open, onClose }) {
  const { user } = useAuth();
  const isAdmin = user && ['administrator', 'super_administrator'].includes(user.role);

  const navLinkClasses = ({ isActive }) =>
    `group flex items-center gap-x-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
      isActive
        ? 'bg-primary-50 dark:bg-primary-900/50 text-primary-700 dark:text-primary-200'
        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white'
    }`;

  const sidebarContent = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center gap-x-3 px-6 border-b border-gray-200 dark:border-gray-700">
        <ShieldCheckIcon className="h-8 w-8 text-primary-600" />
        <span className="text-lg font-bold text-gray-900 dark:text-white">Linux Access</span>
      </div>
      <nav className="flex-1 overflow-y-auto px-4 py-4">
        <div className="space-y-1">
          {navigation.map((item) => (
            <NavLink key={item.name} to={item.href} className={navLinkClasses} onClick={onClose}>
              <item.icon className="h-5 w-5 shrink-0" />
              {item.name}
            </NavLink>
          ))}
        </div>
        {isAdmin && (
          <>
            <div className="mt-6 mb-2 px-3">
              <p className="text-xs font-semibold uppercase text-gray-400 dark:text-gray-500">Administration</p>
            </div>
            <div className="space-y-1">
              {adminNavigation.map((item) => (
                <NavLink key={item.name} to={item.href} className={navLinkClasses} onClick={onClose}>
                  <item.icon className="h-5 w-5 shrink-0" />
                  {item.name}
                </NavLink>
              ))}
            </div>
          </>
        )}
      </nav>
      <div className="border-t border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center gap-x-3">
          <div className="h-8 w-8 rounded-full bg-primary-600 flex items-center justify-center text-white text-sm font-medium">
            {user?.display_name?.charAt(0) || 'U'}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{user?.display_name}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{user?.email}</p>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile sidebar */}
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="fixed inset-0 bg-gray-900/50" onClick={onClose} />
          <div className="fixed inset-y-0 left-0 w-64 bg-white dark:bg-gray-800">
            <button onClick={onClose} className="absolute top-4 right-4">
              <XMarkIcon className="h-6 w-6 text-gray-500" />
            </button>
            {sidebarContent}
          </div>
        </div>
      )}
      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:z-40 lg:flex lg:w-64 lg:flex-col">
        <div className="flex grow flex-col bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
          {sidebarContent}
        </div>
      </div>
    </>
  );
}
