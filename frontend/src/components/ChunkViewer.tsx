interface Chunk {
  chunk_id?: number;
  text?: string;
  score?: number;
  [key: string]: unknown;
}

interface ChunkViewerProps {
  chunks: Chunk[];
}

export function ChunkViewer({ chunks }: ChunkViewerProps) {
  if (!chunks || chunks.length === 0) {
    return (
      <div className="text-sm text-gray-500 italic p-4 bg-gray-50 rounded-lg">
        No retrieved chunks
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {chunks.map((chunk, index) => (
        <div
          key={chunk.chunk_id ?? index}
          className="border border-gray-200 rounded-lg p-3 bg-white"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500">
              Chunk {chunk.chunk_id ?? index + 1}
            </span>
            {chunk.score !== undefined && (
              <span
                className={`text-xs px-2 py-0.5 rounded-full ${
                  chunk.score >= 0.8
                    ? 'bg-green-100 text-green-700'
                    : chunk.score >= 0.5
                    ? 'bg-yellow-100 text-yellow-700'
                    : 'bg-red-100 text-red-700'
                }`}
              >
                Score: {(chunk.score * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <p className="text-sm text-gray-700 whitespace-pre-wrap">
            {chunk.text ?? JSON.stringify(chunk)}
          </p>
        </div>
      ))}
    </div>
  );
}
