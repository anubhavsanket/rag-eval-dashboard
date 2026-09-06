import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Dataset, RAGConfig, datasetsApi, configsApi, sweepsApi } from '../api/client';

interface Sweep {
  id: number;
  name: string;
  description: string | null;
  dataset_id: number;
  status: string;
  run_ids: number[];
  summary: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
}

interface LeaderboardEntry {
  run_id: number;
  config_id: number;
  config_name: string;
  status: string;
  quality_score: number;
  avg_correctness: number;
  avg_faithfulness: number;
  avg_relevance: number;
  avg_hallucination: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  total_tokens: number;
}

const statusColor: Record<string, string> = {
  completed: 'bg-green-100 text-green-700',
  running: 'bg-blue-100 text-blue-700',
  pending: 'bg-gray-100 text-gray-700',
  failed: 'bg-red-100 text-red-700',
};

export function Sweeps() {
  const [sweeps, setSweeps] = useState<Sweep[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [configs, setConfigs] = useState<RAGConfig[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<number | null>(null);
  const [selectedConfigs, setSelectedConfigs] = useState<number[]>([]);
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[] | null>(null);
  const navigate = useNavigate();

  const loadSweeps = () => {
    sweepsApi.list().then(setSweeps);
  };

  useEffect(() => {
    Promise.all([datasetsApi.list(), configsApi.list()]).then(([ds, cfg]) => {
      setDatasets(ds);
      setConfigs(cfg);
    });
    loadSweeps();
  }, []);

  const toggleConfig = (id: number) => {
    setSelectedConfigs((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  const handleCreate = async () => {
    if (!selectedDataset || selectedConfigs.length === 0 || !name.trim()) return;
    setCreating(true);
    try {
      await sweepsApi.start({
        name: name.trim(),
        dataset_id: selectedDataset,
        config_ids: selectedConfigs,
      });
      setName('');
      setSelectedConfigs([]);
      loadSweeps();
      // Poll until the newest sweep completes
      const interval = setInterval(async () => {
        const sweepsNow = await sweepsApi.list();
        const latest = sweepsNow[0];
        if (latest && (latest.status === 'completed' || latest.status === 'failed')) {
          clearInterval(interval);
          setLeaderboard(
            (latest.summary?.leaderboard as LeaderboardEntry[] | undefined) ?? null
          );
          loadSweeps();
          setCreating(false);
        }
      }, 2000);
    } catch {
      setCreating(false);
    }
  };

  const handleViewSweep = async (sweepId: number) => {
    const sweep = await sweepsApi.get(sweepId);
    setLeaderboard(
      (sweep.summary?.leaderboard as LeaderboardEntry[] | undefined) ?? null
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Optimization Sweeps</h1>
        <p className="text-gray-500 mt-1">
          Benchmark multiple RAG configurations against one dataset to find the global optimum
        </p>
      </div>

      {/* Create Sweep */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">New Sweep</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Sweep Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              placeholder="e.g. chunk-size vs top-k sweep"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Dataset</label>
            <select
              value={selectedDataset ?? ''}
              onChange={(e) => setSelectedDataset(Number(e.target.value) || null)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">Select a dataset...</option>
              {datasets.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name} ({ds.test_case_count} test cases)
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Configurations to Sweep ({selectedConfigs.length} selected)
          </label>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {configs.map((cfg) => (
              <label
                key={cfg.id}
                className={`flex items-center p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedConfigs.includes(cfg.id)
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selectedConfigs.includes(cfg.id)}
                  onChange={() => toggleConfig(cfg.id)}
                  className="mr-3 h-4 w-4 text-blue-600"
                />
                <div>
                  <div className="text-sm font-medium text-gray-900">{cfg.name}</div>
                  <div className="text-xs text-gray-500">
                    {String(cfg.config?.adapter_type ?? 'unknown')}
                  </div>
                </div>
              </label>
            ))}
            {configs.length === 0 && (
              <p className="text-sm text-gray-500 col-span-full">
                No configs yet. Create some on the Configs page first.
              </p>
            )}
          </div>
        </div>

        <button
          onClick={handleCreate}
          disabled={!selectedDataset || selectedConfigs.length === 0 || !name.trim() || creating}
          className="mt-6 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          {creating ? 'Running Sweep...' : 'Start Sweep'}
        </button>
      </div>

      {/* Sweep History */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Sweep History</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Configs</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {sweeps.map((sweep) => (
                <tr
                  key={sweep.id}
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => handleViewSweep(sweep.id)}
                >
                  <td className="px-6 py-4 text-sm text-gray-900">#{sweep.id}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">{sweep.name}</td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                        statusColor[sweep.status] ?? 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {sweep.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">{sweep.run_ids.length}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {new Date(sweep.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
              {sweeps.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                    No sweeps yet. Create one above to compare configurations.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Leaderboard */}
      {leaderboard && leaderboard.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Leaderboard</h2>
            <p className="text-sm text-gray-500 mt-1">
              Configurations ranked by weighted Quality Score
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">#</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Config</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Quality</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Correctness</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Faithfulness</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Relevance</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Hallucin.</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Latency</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Cost</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {leaderboard.map((entry, idx) => (
                  <tr
                    key={entry.run_id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => navigate(`/run/${entry.run_id}`)}
                  >
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : idx + 1}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{entry.config_name}</td>
                    <td className="px-6 py-4 text-sm text-center font-semibold text-gray-900">
                      {(entry.quality_score * 100).toFixed(1)}%
                    </td>
                    <td className="px-6 py-4 text-sm text-center text-gray-600">
                      {(entry.avg_correctness * 100).toFixed(1)}%
                    </td>
                    <td className="px-6 py-4 text-sm text-center text-gray-600">
                      {(entry.avg_faithfulness * 100).toFixed(1)}%
                    </td>
                    <td className="px-6 py-4 text-sm text-center text-gray-600">
                      {(entry.avg_relevance * 100).toFixed(1)}%
                    </td>
                    <td className="px-6 py-4 text-sm text-center text-gray-600">
                      {(entry.avg_hallucination * 100).toFixed(1)}%
                    </td>
                    <td className="px-6 py-4 text-sm text-center text-gray-600">
                      {entry.avg_latency_ms ? `${entry.avg_latency_ms.toFixed(0)}ms` : '-'}
                    </td>
                    <td className="px-6 py-4 text-sm text-center text-gray-600">
                      ${entry.total_cost_usd.toFixed(6)}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                          statusColor[entry.status] ?? 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {entry.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}