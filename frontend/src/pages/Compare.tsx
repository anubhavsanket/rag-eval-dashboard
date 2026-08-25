import { useEffect, useState } from 'react';
import { EvalRun, EvalResult, resultsApi } from '../api/client';
import { MetricChart } from '../components/MetricChart';
import { QueryTable } from '../components/QueryTable';

export function Compare() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [comparison, setComparison] = useState<{
    runs: EvalRun[];
    per_query_comparison: Array<{ run_id: number; results: EvalResult[] }>;
  } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    resultsApi.listRuns('completed').then(setRuns);
  }, []);

  const handleCompare = async () => {
    if (selectedIds.length < 2) return;
    setLoading(true);
    try {
      const data = await resultsApi.compare(selectedIds);
      setComparison(data);
    } finally {
      setLoading(false);
    }
  };

  const toggleId = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id].slice(-3)
    );
  };

  // Build comparison chart data
  const chartData = comparison?.runs.map((run, idx) => {
    const s = (run.summary ?? {}) as Record<string, number>;
    return {
      run: `Run ${run.id}`,
      faithfulness: s.avg_faithfulness ?? 0,
      relevance: s.avg_relevance ?? 0,
      correctness: s.avg_correctness ?? 0,
      hallucination: s.avg_hallucination ?? 0,
    };
  }) ?? [];

  const chartLines = [
    { key: 'faithfulness', color: '#3b82f6', name: 'Faithfulness' },
    { key: 'relevance', color: '#10b981', name: 'Relevance' },
    { key: 'correctness', color: '#f59e0b', name: 'Correctness' },
    { key: 'hallucination', color: '#ef4444', name: 'Hallucination' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Compare Runs</h1>
        <p className="text-gray-500 mt-1">Select 2-3 completed runs to compare side by side</p>
      </div>

      {/* Run Selection */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Select Runs</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {runs.map((run) => (
            <label
              key={run.id}
              className={`flex items-center p-3 rounded-lg border cursor-pointer transition-colors ${
                selectedIds.includes(run.id)
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:bg-gray-50'
              }`}
            >
              <input
                type="checkbox"
                checked={selectedIds.includes(run.id)}
                onChange={() => toggleId(run.id)}
                className="mr-3 h-4 w-4 text-blue-600"
              />
              <div>
                <div className="text-sm font-medium text-gray-900">Run #{run.id}</div>
                <div className="text-xs text-gray-500">
                  {new Date(run.created_at).toLocaleString()}
                </div>
              </div>
            </label>
          ))}
        </div>
        <button
          onClick={handleCompare}
          disabled={selectedIds.length < 2 || loading}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          {loading ? 'Comparing...' : 'Compare Selected'}
        </button>
      </div>

      {/* Comparison Results */}
      {comparison && (
        <>
          {/* Grouped Bar Chart */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Metric Comparison</h2>
            <MetricChart type="bar" data={chartData} xKey="run" lines={chartLines} height={350} />
          </div>

          {/* Per-Query Comparison Table */}
          {comparison.per_query_comparison.length > 0 && (
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Per-Query Results</h2>
              {comparison.per_query_comparison.map((pc) => (
                <div key={pc.run_id} className="mb-6">
                  <h3 className="text-sm font-medium text-gray-700 mb-2">Run #{pc.run_id}</h3>
                  <QueryTable results={pc.results} />
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
