import React, { useState } from 'react';
import { reportsAPI } from '../services/api';
import toast from 'react-hot-toast';

const reports = [
  { id: 'user-access', name: 'User Access Report', desc: 'All provisioned user access', api: 'userAccess' },
  { id: 'sudo-access', name: 'Sudo Access Report', desc: 'Active and expired sudo access', api: 'sudoAccess' },
];

export default function ReportsPage() {
  const [selectedReport, setSelectedReport] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const generateReport = async (report, format = 'json') => {
    setLoading(true);
    setSelectedReport(report.id);
    try {
      if (format === 'json') {
        const res = await reportsAPI[report.api]('json');
        setData(res.data);
      } else {
        const res = await reportsAPI[report.api](format);
        // Download the file
        const blob = new Blob([res.data], { type: format === 'csv' ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${report.id}.${format === 'csv' ? 'csv' : 'xlsx'}`;
        a.click();
        toast.success('Report downloaded');
      }
    } catch (err) {
      toast.error('Failed to generate report');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Reports</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {reports.map((report) => (
          <div key={report.id} className="card">
            <h3 className="text-md font-semibold text-gray-900 dark:text-white">{report.name}</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{report.desc}</p>
            <div className="flex gap-2 mt-4">
              <button onClick={() => generateReport(report, 'json')} className="btn-primary text-sm">View</button>
              <button onClick={() => generateReport(report, 'csv')} className="btn-secondary text-sm">CSV</button>
              <button onClick={() => generateReport(report, 'excel')} className="btn-secondary text-sm">Excel</button>
            </div>
          </div>
        ))}
      </div>

      {/* Report Data */}
      {loading && <div className="flex justify-center py-8"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div></div>}

      {data && !loading && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-md font-semibold text-gray-900 dark:text-white">Results ({data.total || data.data?.length || 0})</h3>
            <button onClick={() => setData(null)} className="text-sm text-gray-500 hover:text-gray-700">Clear</button>
          </div>
          {data.data && data.data.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                <thead>
                  <tr>
                    {Object.keys(data.data[0]).map(key => (
                      <th key={key} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{key.replace(/_/g, ' ')}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {data.data.map((row, i) => (
                    <tr key={i}>
                      {Object.values(row).map((val, j) => (
                        <td key={j} className="px-3 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap">{String(val)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No data available.</p>
          )}
        </div>
      )}
    </div>
  );
}
