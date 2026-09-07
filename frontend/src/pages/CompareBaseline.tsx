import { useEffect, useState } from 'react';
import { EvalRun, resultsApi } from '../api/client';
import { MetricChart } from '../components/MetricChart';

export function CompareBaseline() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [baselineId, setBaselineId] = useState<number | null>(null);
  const [candidateId, setCandidateId] = useState<number | null>(null);
  const [delta, setDelta] = useState<Record<string, number> | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    resultsApi.listRuns('completed').then(setRuns);
  }, []);

  const handleCompare = async () => {
    if (!baselineId || !candidateId || baselineId === candidateId) return;
    setLoading(true);
    try {
      const data = await resultsApi.compareBaseline(baselineId, candidateId);
      setDelta(data.delta_scores);
    } finally {
      setLoading(false);
    }
  };

  const getDeltaColor = (v: number) => {
    if (v > 0) return 'text-green-600 font-semibold';
    if (v < 0) return 'text-red-600 font-semibold';
    return 'text-gray-500';
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Compare Baseline vs Candidate</h1>
        <p className="text-gray-500 mt-1">Select a baseline run and a candidate run to compare overall metrics</p>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Baseline Run</label>
            <select
              value={baselineId ?? ''}
              onChange={(e) => setBaselineId(Number(e.target.value) || null)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">Select baseline...</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>Run #{r.id} ({new Date(r.created_at).toLocaleDateString()})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Candidate Run</label>
            <select
              value={candidateId ?? ''}
              onChange={(e) => setCandidateId(Number(e.target.value) || null)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">Select candidate...</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>Run #{r.id} ({new Date(r.created_at).toLocaleDateString()})</option>
              ))}
            </select>
          </div>
        </div>
        <button
          onClick={handleCompare}
          disabled={!baselineId || !candidateId || baselineId === candidateId || loading}
          className="mt-6 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300"
        >
          {loading ? 'Comparing...' : 'Compare'}
        </button>
      </div>

      {delta && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">A/B Delta (Candidate − Baseline)</h2>
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50"><tr><th className="text-left px-4 py-2">Metric</th><th className="text-right px-4 py-2">Delta</th></tr></thead>
            <tbody>
              {Object.entries(delta).map(([k, v]) => (
                <tr key={k} className="border-t"><td className="px-4 py-2 font-medium capitalize">{k.replace('_', ' ')}</td><td className={`px-4 py-2 text-right ${getDeltaColor(v)}`}>{v > 0 ? '+' : ''}{v.toFixed(4)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
