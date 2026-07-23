import React, { useEffect, useState } from 'react';
import { adminAPI } from '../services/api';
import toast from 'react-hot-toast';

const roles = ['requester', 'reporting_manager', 'cloud_manager', 'infosec', 'administrator', 'super_administrator'];

export default function AdminUsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editUser, setEditUser] = useState(null);

  useEffect(() => { loadUsers(); }, []);

  const loadUsers = async () => {
    try {
      const res = await adminAPI.users({ page: 1, page_size: 100 });
      setUsers(res.data.items || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = async () => {
    if (!editUser) return;
    try {
      await adminAPI.updateUser(editUser.id, { role: editUser.role, is_active: editUser.is_active });
      toast.success('User updated');
      setEditUser(null);
      loadUsers();
    } catch (err) {
      toast.error('Failed to update user');
    }
  };

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div></div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">User Management</h1>

      <div className="card overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Department</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Role</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">{user.display_name}</td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{user.email}</td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{user.department || '-'}</td>
                  <td className="px-4 py-3"><span className="badge-info capitalize">{user.role.replace(/_/g, ' ')}</span></td>
                  <td className="px-4 py-3"><span className={user.is_active ? 'badge-success' : 'badge-danger'}>{user.is_active ? 'Active' : 'Inactive'}</span></td>
                  <td className="px-4 py-3">
                    <button onClick={() => setEditUser({...user})} className="text-sm text-primary-600 hover:text-primary-700">Edit</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Edit Modal */}
      {editUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Edit User: {editUser.display_name}</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Role</label>
                <select value={editUser.role} onChange={(e) => setEditUser({...editUser, role: e.target.value})} className="input-field">
                  {roles.map(r => <option key={r} value={r}>{r.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={editUser.is_active} onChange={(e) => setEditUser({...editUser, is_active: e.target.checked})} className="rounded" />
                <label className="text-sm text-gray-700 dark:text-gray-300">Active</label>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setEditUser(null)} className="btn-secondary">Cancel</button>
              <button onClick={handleUpdate} className="btn-primary">Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
