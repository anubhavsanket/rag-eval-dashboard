interface ScoreCardProps {
  title: string;
  value: number;
  format?: 'percent' | 'decimal' | 'integer';
  color?: 'blue' | 'green' | 'yellow' | 'red';
}

const colorMap = {
  blue: 'bg-blue-50 text-blue-700 border-blue-200',
  green: 'bg-green-50 text-green-700 border-green-200',
  yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  red: 'bg-red-50 text-red-700 border-red-200',
};

function formatValue(value: number, format: string): string {
  switch (format) {
    case 'percent':
      return `${(value * 100).toFixed(1)}%`;
    case 'decimal':
      return value.toFixed(3);
    case 'integer':
      return Math.round(value).toLocaleString();
    default:
      return value.toFixed(2);
  }
}

export function ScoreCard({ title, value, format = 'percent', color = 'blue' }: ScoreCardProps) {
  return (
    <div className={`rounded-lg border p-4 ${colorMap[color]}`}>
      <p className="text-sm font-medium opacity-75">{title}</p>
      <p className="text-2xl font-bold mt-1">{formatValue(value, format)}</p>
    </div>
  );
}
