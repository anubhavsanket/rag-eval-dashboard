import { EvalResult } from '../api/client';

interface QueryTableProps {
  results: EvalResult[];
  onSelect?: (result: EvalResult) => void;
  highlightRegressions?: boolean;
  baselineScores?: Record<number, Record<string, number>>;
}

export function QueryTable({ results, onSelect, highlightRegressions, baselineScores }: QueryTableProps) {
  const getScoreColor = (score: number, key: string, testCaseId?: number) => {
    if (highlightRegressions && baselineScores && testCaseId !== undefined) {
      const baseline = baselineScores[testCaseId]?.[key];
      if (baseline !== undefined && score < baseline - 0.1) {
        return 'text-red-600 font-semibold';
      }
    }
    if (score >= 0.8) return 'text-green-600';
    if (score >= 0.5) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Query</th>
            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Faithfulness</th>
            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Relevance</th>
            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Correctness</th>
            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Hallucination</th>
            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Latency</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {results.map((result) => (
            <tr
              key={result.id}
              className="hover:bg-gray-50 cursor-pointer"
              onClick={() => onSelect?.(result)}
            >
              <td className="px-4 py-3 text-sm text-gray-900 max-w-xs truncate">
                {result.query}
              </td>
              <td className={`px-4 py-3 text-sm text-center ${getScoreColor(result.scores.faithfulness, 'faithfulness', result.test_case_id)}`}>
                {(result.scores.faithfulness * 100).toFixed(1)}%
              </td>
              <td className={`px-4 py-3 text-sm text-center ${getScoreColor(result.scores.relevance, 'relevance', result.test_case_id)}`}>
                {(result.scores.relevance * 100).toFixed(1)}%
              </td>
              <td className={`px-4 py-3 text-sm text-center ${getScoreColor(result.scores.correctness, 'correctness', result.test_case_id)}`}>
                {(result.scores.correctness * 100).toFixed(1)}%
              </td>
              <td className={`px-4 py-3 text-sm text-center ${getScoreColor(1 - result.scores.hallucination, 'hallucination', result.test_case_id)}`}>
                {(result.scores.hallucination * 100).toFixed(1)}%
              </td>
              <td className="px-4 py-3 text-sm text-center text-gray-600">
                {result.latency_ms ? `${result.latency_ms}ms` : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
