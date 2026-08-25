import { useEffect, useState, useRef } from 'react';
import { Dataset, DatasetDetail, datasetsApi } from '../api/client';

export function Datasets() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<DatasetDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadDatasets();
  }, []);

  const loadDatasets = async () => {
    setLoading(true);
    const data = await datasetsApi.list();
    setDatasets(data);
    setLoading(false);
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      await datasetsApi.create({
        name: json.name || file.name.replace(/\.\w+$/, ''),
        description: json.description || '',
        tags: json.tags || [],
        test_cases: json.test_cases || json,
      });
      await loadDatasets();
    } catch (err) {
      alert('Failed to upload dataset. Check the file format.');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this dataset and all its test cases?')) return;
    await datasetsApi.delete(id);
    if (selected?.id === id) setSelected(null);
    await loadDatasets();
  };

  const handleSelect = async (id: number) => {
    const detail = await datasetsApi.get(id);
    setSelected(detail);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Datasets</h1>
          <p className="text-gray-500 mt-1">Manage your test datasets</p>
        </div>
        <div className="flex gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,.csv"
            onChange={handleUpload}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300"
          >
            {uploading ? 'Uploading...' : 'Upload Dataset'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Dataset List */}
        <div className="lg:col-span-1 space-y-3">
          {datasets.map((ds) => (
            <div
              key={ds.id}
              className={`p-4 bg-white rounded-lg border cursor-pointer transition-colors ${
                selected?.id === ds.id ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'
              }`}
              onClick={() => handleSelect(ds.id)}
            >
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-gray-900">{ds.name}</h3>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(ds.id);
                  }}
                  className="text-red-500 hover:text-red-700 text-sm"
                >
                  Delete
                </button>
              </div>
              <p className="text-sm text-gray-500 mt-1">{ds.test_case_count} test cases</p>
              <div className="flex gap-1 mt-2">
                {ds.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          ))}
          {datasets.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              No datasets yet. Upload a JSON file to get started.
            </div>
          )}
        </div>

        {/* Dataset Detail */}
        <div className="lg:col-span-2">
          {selected ? (
            <div className="bg-white rounded-lg border border-gray-200">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">{selected.name}</h2>
                {selected.description && (
                  <p className="text-sm text-gray-500 mt-1">{selected.description}</p>
                )}
              </div>
              <div className="divide-y divide-gray-200">
                {selected.test_cases.map((tc) => (
                  <div key={tc.id} className="px-6 py-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="text-sm font-medium text-gray-900">{tc.query}</p>
                        <p className="text-sm text-gray-600 mt-1 line-clamp-2">
                          {tc.expected_answer}
                        </p>
                      </div>
                    </div>
                    {tc.context_chunks.length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs text-gray-400">
                          {tc.context_chunks.length} context chunk(s)
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-lg border border-gray-200 p-12 text-center text-gray-500">
              Select a dataset to view its test cases
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
