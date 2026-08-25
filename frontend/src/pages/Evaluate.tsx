import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Dataset, RAGConfig, EvalRun, datasetsApi, configsApi, evaluateApi } from '../api/client';

export function Evaluate() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [configs, setConfigs] = useState<RAGConfig[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<number | null>(null);
  const [selectedConfig, setSelectedConfig] = useState<number | null>(null);
  const [currentRun, setCurrentRun] = useState<EvalRun | null>(null);
  const [polling, setPolling] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([datasetsApi.list(), configsApi.list()]).then(([ds, cfg]) => {
      setDatasets(ds);
      setConfigs(cfg);
    });
  }, []);

  // Poll for run completion
  useEffect(() => {
    if (!currentRun || currentRun.status === 'completed' || currentRun.status === 'failed') {
      setPolling(false);
      return;
    }
    setPolling(true);
    const interval = setInterval(async () => {
      const updated = await evaluateApi.getRun(currentRun.id);
      setCurrentRun(updated);
      if (updated.status === 'completed' || updated.status === 'failed') {
        setPolling(false);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [currentRun]);

  const handleStart = async () => {
    if (!selectedDataset || !selectedConfig) return;
    const run = await evaluateApi.start({
      dataset_id: selectedDataset,
      config_id: selectedConfig,
    });
    setCurrentRun(run);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Evaluate</h1>
        <p className="text-gray-500 mt-1">Start a new evaluation run</p>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Configuration</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Dataset Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Dataset</label>
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

          {/* Config Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">RAG Config</label>
            <select
              value={selectedConfig ?? ''}
              onChange={(e) => setSelectedConfig(Number(e.target.value) || null)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">Select a config...</option>
              {configs.map((cfg) => (
                <option key={cfg.id} value={cfg.id}>
                  {cfg.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          onClick={handleStart}
          disabled={!selectedDataset || !selectedConfig || polling}
          className="mt-6 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          {polling ? 'Running...' : 'Start Evaluation'}
        </button>
      </div>

      {/* Run Status */}
      {currentRun && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Run Status</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Run ID:</span>{' '}
              <span className="text-gray-900">#{currentRun.id}</span>
            </div>
            <div>
              <span className="text-gray-500">Status:</span>{' '}
              <span
                className={`font-medium ${
                  currentRun.status === 'completed'
                    ? 'text-green-600'
                    : currentRun.status === 'running'
                    ? 'text-blue-600'
                    : currentRun.status === 'failed'
                    ? 'text-red-600'
                    : 'text-gray-600'
                }`}
              >
                {currentRun.status}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Started:</span>{' '}
              <span className="text-gray-900">
                {currentRun.started_at ? new Date(currentRun.started_at).toLocaleTimeString() : '-'}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Completed:</span>{' '}
              <span className="text-gray-900">
                {currentRun.completed_at
                  ? new Date(currentRun.completed_at).toLocaleTimeString()
                  : '-'}
              </span>
            </div>
          </div>

          {currentRun.status === 'completed' && (
            <div className="mt-4">
              <button
                onClick={() => navigate(`/run/${currentRun.id}`)}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
              >
                View Results
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
