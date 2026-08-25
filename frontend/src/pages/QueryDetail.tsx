import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { EvalResult, evaluateApi } from '../api/client';
import { ChunkViewer } from '../components/ChunkViewer';

export function QueryDetail() {
  const { runId, resultId } = useParams<{ runId: string; resultId?: string }>();
  const [results, setResults] = useState<EvalResult[]>([]);
  const [selected, setSelected] = useState<EvalResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    evaluateApi.getResults(Number(runId)).then((data) => {
      setResults(data);
      if (resultId) {
        const found = data.find((r) => r.id === Number(resultId));
        if (found) setSelected(found);
      } else if (data.length > 0) {
        setSelected(data[0]);
      }
      setLoading(false);
    });
  }, [runId, resultId]);

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
        <h1 className="text-2xl font-bold text-gray-900">Run #{runId} - Query Details</h1>
        <p className="text-gray-500 mt-1">Click a query to view detailed analysis</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Query List */}
        <div className="lg:col-span-1 bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
            <h2 className="text-sm font-semibold text-gray-700">Queries ({results.length})</h2>
          </div>
          <div className="max-h-[600px] overflow-y-auto">
            {results.map((r) => (
              <button
                key={r.id}
                onClick={() => setSelected(r)}
                className={`w-full text-left px-4 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors ${
                  selected?.id === r.id ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''
                }`}
              >
                <p className="text-sm text-gray-900 line-clamp-2">{r.query}</p>
                <div className="flex gap-2 mt-1">
                  <span className="text-xs text-gray-500">
                    F: {(r.scores.faithfulness * 100).toFixed(0)}%
                  </span>
                  <span className="text-xs text-gray-500">
                    R: {(r.scores.relevance * 100).toFixed(0)}%
                  </span>
                  <span className="text-xs text-gray-500">
                    C: {(r.scores.correctness * 100).toFixed(0)}%
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Detail View */}
        {selected && (
          <div className="lg:col-span-2 space-y-4">
            {/* Query & Answers */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-sm font-medium text-gray-500 uppercase mb-2">Query</h3>
              <p className="text-gray-900 mb-4">{selected.query}</p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <h3 className="text-sm font-medium text-gray-500 uppercase mb-2">Generated Answer</h3>
                  <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-700 whitespace-pre-wrap">
                    {selected.answer}
                  </div>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-gray-500 uppercase mb-2">Expected Answer</h3>
                  <div className="p-3 bg-green-50 rounded-lg text-sm text-gray-700 whitespace-pre-wrap">
                    {results.find((r) => r.test_case_id === selected.test_case_id)
                      ? 'See dataset for expected answer'
                      : 'N/A'}
                  </div>
                </div>
              </div>
            </div>

            {/* Scores Breakdown */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-sm font-medium text-gray-500 uppercase mb-4">Scores</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <ScoreBlock label="Faithfulness" value={selected.scores.faithfulness} />
                <ScoreBlock label="Relevance" value={selected.scores.relevance} />
                <ScoreBlock label="Correctness" value={selected.scores.correctness} />
                <ScoreBlock label="Hallucination" value={selected.scores.hallucination} />
              </div>

              {/* Judge Reasoning */}
              <div className="mt-4 space-y-3">
                {Object.entries(selected.scores.details ?? {}).map(([key, value]) => {
                  if (typeof value !== 'object' || value === null) return null;
                  const detail = value as Record<string, unknown>;
                  return (
                    <div key={key} className="p-3 bg-gray-50 rounded-lg">
                      <h4 className="text-xs font-medium text-gray-500 uppercase mb-1">
                        {key} - Judge Reasoning
                      </h4>
                      <p className="text-sm text-gray-700">
                        {typeof detail === 'string'
                          ? detail
                          : detail.reasoning
                          ? String(detail.reasoning)
                          : JSON.stringify(detail, null, 2)}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Retrieved Chunks */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-sm font-medium text-gray-500 uppercase mb-4">Retrieved Chunks</h3>
              <ChunkViewer chunks={selected.retrieved_chunks} />
            </div>

            {/* Metadata */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h3 className="text-sm font-medium text-gray-500 uppercase mb-4">Metadata</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Latency:</span>{' '}
                  <span className="text-gray-900">{selected.latency_ms ?? '-'}ms</span>
                </div>
                <div>
                  <span className="text-gray-500">Tokens Used:</span>{' '}
                  <span className="text-gray-900">{selected.tokens_used ?? '-'}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ScoreBlock({ label, value }: { label: string; value: number }) {
  const color =
    value >= 0.8 ? 'text-green-600' : value >= 0.5 ? 'text-yellow-600' : 'text-red-600';
  return (
    <div className="text-center p-3 bg-gray-50 rounded-lg">
      <p className="text-xs text-gray-500 uppercase">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{(value * 100).toFixed(1)}%</p>
    </div>
  );
}
