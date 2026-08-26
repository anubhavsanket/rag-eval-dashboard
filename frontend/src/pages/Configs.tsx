import { useEffect, useState } from 'react';
import { RAGConfig, configsApi } from '../api/client';

const adapterTemplates = {
  mock: {
    name: 'Mock Adapter',
    description: 'Returns canned responses for testing the eval pipeline',
    config: { adapter_type: 'mock' },
  },
  http: {
    name: 'HTTP Adapter',
    description: 'Calls an external RAG API endpoint',
    config: { adapter_type: 'http', endpoint_url: 'http://localhost:8000/query' },
  },
  local_brain_notes: {
    name: 'LocalBrainNotes',
    description: 'Connects to a local Ollama + ChromaDB pipeline',
    config: { adapter_type: 'local_brain_notes', base_url: 'http://localhost:8000' },
  },
};

export function Configs() {
  const [configs, setConfigs] = useState<RAGConfig[]>([]);
  const [selected, setSelected] = useState<RAGConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', config: '' });

  useEffect(() => {
    loadConfigs();
  }, []);

  const loadConfigs = async () => {
    setLoading(true);
    const data = await configsApi.list();
    setConfigs(data);
    setLoading(false);
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this config?')) return;
    await configsApi.delete(id);
    if (selected?.id === id) setSelected(null);
    await loadConfigs();
  };

  const handleCreate = async () => {
    let parsedConfig;
    try {
      parsedConfig = JSON.parse(form.config || '{}');
    } catch {
      alert('Config must be valid JSON');
      return;
    }
    await configsApi.create({
      name: form.name,
      description: form.description,
      config: parsedConfig,
    });
    setForm({ name: '', description: '', config: '' });
    setShowCreate(false);
    await loadConfigs();
  };

  const applyTemplate = (key: keyof typeof adapterTemplates) => {
    const t = adapterTemplates[key];
    setForm({
      name: t.name,
      description: t.description,
      config: JSON.stringify(t.config, null, 2),
    });
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
          <h1 className="text-2xl font-bold text-gray-900">RAG Configs</h1>
          <p className="text-gray-500 mt-1">Manage RAG pipeline configurations for evaluation</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          {showCreate ? 'Cancel' : 'New Config'}
        </button>
      </div>

      {showCreate && (
        <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">Create New Config</h2>

          <div className="flex gap-2">
            <span className="text-sm text-gray-600 self-center">Quick templates:</span>
            {(Object.keys(adapterTemplates) as Array<keyof typeof adapterTemplates>).map(
              (key) => (
                <button
                  key={key}
                  onClick={() => applyTemplate(key)}
                  className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-full text-gray-700"
                >
                  {adapterTemplates[key].name}
                </button>
              )
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              placeholder="My RAG Config"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              placeholder="Optional description"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Config (JSON)
            </label>
            <textarea
              value={form.config}
              onChange={(e) => setForm({ ...form, config: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono h-40"
              placeholder='{"adapter_type": "mock"}'
            />
          </div>

          <button
            onClick={handleCreate}
            disabled={!form.name}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300"
          >
            Create
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-3">
          {configs.map((cfg) => (
            <div
              key={cfg.id}
              onClick={() => setSelected(cfg)}
              className={`p-4 bg-white rounded-lg border cursor-pointer transition-colors ${
                selected?.id === cfg.id
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-gray-900">{cfg.name}</h3>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(cfg.id);
                  }}
                  className="text-red-500 hover:text-red-700 text-sm"
                >
                  Delete
                </button>
              </div>
              {cfg.description && (
                <p className="text-sm text-gray-500 mt-1 line-clamp-2">{cfg.description}</p>
              )}
              <div className="mt-2">
                <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded-full">
                  {String(cfg.config.adapter_type || 'unknown')}
                </span>
              </div>
            </div>
          ))}
          {configs.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              No configs yet. Click "New Config" to create one.
            </div>
          )}
        </div>

        <div className="lg:col-span-2">
          {selected ? (
            <div className="bg-white rounded-lg border border-gray-200">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">{selected.name}</h2>
                {selected.description && (
                  <p className="text-sm text-gray-500 mt-1">{selected.description}</p>
                )}
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <h3 className="text-sm font-medium text-gray-500 uppercase mb-2">
                    Adapter Type
                  </h3>
                  <p className="text-sm text-gray-900">
                    {String(selected.config.adapter_type || 'unknown')}
                  </p>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-gray-500 uppercase mb-2">
                    Full Config
                  </h3>
                  <pre className="bg-gray-50 rounded-lg p-3 text-xs font-mono overflow-x-auto">
                    {JSON.stringify(selected.config, null, 2)}
                  </pre>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-gray-500 uppercase mb-2">Created</h3>
                  <p className="text-sm text-gray-900">
                    {new Date(selected.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-lg border border-gray-200 p-12 text-center text-gray-500">
              Select a config to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
