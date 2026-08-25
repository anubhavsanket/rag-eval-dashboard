import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { EvalRun, resultsApi } from '../api/client';
import { ScoreCard } from '../components/ScoreCard';
import { MetricChart } from '../components/MetricChart';

export function Dashboard() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    resultsApi.listRuns().then((data) => {
      setRuns(data);
      setLoading(false);
    });
  }, []);

  const latestRun = runs[0];
  const summary = (latestRun?.summary ?? {}) as Record<string, number>;

  // Prepare trend data from all runs
  const trendData = [...runs]
    .reverse()
    .filter((r) => r.status === 'completed')
    .map((r, i) => {
      const s = (r.summary ?? {}) as Record<string, number>;
      return {
        run: `Run ${i + 1}`,
        faithfulness: s.avg_faithfulness ?? 0,
        relevance: s.avg_relevance ?? 0,
        correctness: s.avg_correctness ?? 0,
        hallucination: s.avg_hallucination ?? 0,
      };
    });

  const chartLines = [
    { key: 'faithfulness', color: '#3b82f6', name: 'Faithfulness' },
    { key: 'relevance', color: '#10b981', name: 'Relevance' },
    { key: 'correctness', color: '#f59e0b', name: 'Correctness' },
    { key: 'hallucination', color: '#ef4444', name: 'Hallucination' },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Overview of your RAG evaluation results</p>
      </div>

      {/* Score Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <ScoreCard
          title="Avg Faithfulness"
          value={summary.avg_faithfulness ?? 0}
          color="blue"
        />
        <ScoreCard
          title="Avg Relevance"
          value={summary.avg_relevance ?? 0}
          color="green"
        />
        <ScoreCard
          title="Avg Correctness"
          value={summary.avg_correctness ?? 0}
          color="yellow"
        />
        <ScoreCard
          title="Hallucination Rate"
          value={summary.avg_hallucination ?? 0}
          color="red"
        />
      </div>

      {/* Trend Chart */}
      {trendData.length > 1 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Metric Trends</h2>
          <MetricChart
            type="line"
            data={trendData}
            xKey="run"
            lines={chartLines}
            height={350}
          />
        </div>
      )}

      {/* Recent Runs */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Recent Runs</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Run ID</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Dataset</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Config</th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Faithfulness</th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Relevance</th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Correctness</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {runs.map((run) => {
                const s = (run.summary ?? {}) as Record<string, number>;
                return (
                  <tr
                    key={run.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => navigate(`/run/${run.id}`)}
                  >
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">#{run.id}</td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                          run.status === 'completed'
                            ? 'bg-green-100 text-green-700'
                            : run.status === 'running'
                            ? 'bg-blue-100 text-blue-700'
                            : run.status === 'failed'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">Dataset #{run.dataset_id}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">Config #{run.config_id}</td>
                    <td className="px-6 py-4 text-sm text-center text-gray-600">
                      {s.avg_faithfulness != null ? `${(s.avg_faithfulness * 100).toFixed(1)}%` : '-'}
                    </td>
                    <td className="px-6 py-4 text-sm text-center text-gray-600">
                      {s.avg_relevance != null ? `${(s.avg_relevance * 100).toFixed(1)}%` : '-'}
                    </td>
                    <td className="px-6 py-4 text-sm text-center text-gray-600">
                      {s.avg_correctness != null ? `${(s.avg_correctness * 100).toFixed(1)}%` : '-'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {new Date(run.created_at).toLocaleString()}
                    </td>
                  </tr>
                );
              })}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center text-gray-500">
                    No evaluation runs yet. Start one from the Evaluate page.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
