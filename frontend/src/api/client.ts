const API_BASE = '/api/v1';

async function request<T>(url: string, options?: RequestInit & { isFormData?: boolean }): Promise<T> {
  const headers: HeadersInit = options?.isFormData ? {} : { 'Content-Type': 'application/json' };
  
  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      ...headers,
      ...options?.headers,
    },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

// Types
export interface Dataset {
  id: number;
  name: string;
  description: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
  test_case_count: number;
}

export interface TestCase {
  id: number;
  query: string;
  expected_answer: string;
  context_chunks: string[];
  metadata: Record<string, unknown>;
}

export interface DatasetDetail extends Dataset {
  test_cases: TestCase[];
}

export interface RAGConfig {
  id: number;
  name: string;
  description: string | null;
  config: Record<string, unknown>;
  created_at: string;
}

export interface EvalRun {
  id: number;
  dataset_id: number;
  config_id: number;
  status: string;
  summary: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface EvalResult {
  id: number;
  run_id: number;
  test_case_id: number;
  query: string;
  answer: string;
  retrieved_chunks: Array<{ chunk_id: number; text: string; score: number }>;
  scores: {
    faithfulness: number;
    relevance: number;
    correctness: number;
    hallucination: number;
    details: Record<string, unknown>;
  };
  latency_ms: number | null;
  tokens_used: number | null;
  created_at: string;
}

// Datasets API
export const datasetsApi = {
  list: () => request<Dataset[]>('/datasets'),
  get: (id: number) => request<DatasetDetail>(`/datasets/${id}`),
  create: (data: { name: string; description?: string; tags?: string[]; test_cases: Array<{ query: string; expected_answer: string; context_chunks?: string[] }> }) =>
    request<DatasetDetail>('/datasets', { method: 'POST', body: JSON.stringify(data) }),
  delete: (id: number) => request(`/datasets/${id}`, { method: 'DELETE' }),
  upload: (formData: FormData) => {
    // Don't set Content-Type for FormData - browser sets it with boundary
    return request<DatasetDetail>('/datasets/upload', {
      method: 'POST',
      body: formData,
      headers: {},
    });
  },
};

// Configs API
export const configsApi = {
  list: () => request<RAGConfig[]>('/configs'),
  create: (data: { name: string; description?: string; config: Record<string, unknown> }) =>
    request<RAGConfig>('/configs', { method: 'POST', body: JSON.stringify(data) }),
  delete: (id: number) => request(`/configs/${id}`, { method: 'DELETE' }),
};

// Evaluate API
export const evaluateApi = {
  start: (data: { dataset_id: number; config_id: number }) =>
    request<EvalRun>('/evaluate', { method: 'POST', body: JSON.stringify(data) }),
  getRun: (runId: number) => request<EvalRun>(`/evaluate/${runId}`),
  getResults: (runId: number) => request<EvalResult[]>(`/evaluate/${runId}/results`),
};

// Results API
export const resultsApi = {
  listRuns: (status?: string) =>
    request<EvalRun[]>(`/results/runs${status ? `?status=${status}` : ''}`),
  compare: (ids: number[]) =>
    request<{ runs: EvalRun[]; per_query_comparison: Array<{ run_id: number; results: EvalResult[] }> }>(
      `/results/compare?ids=${ids.join(',')}`
    ),
  getFailures: (runId: number, failureType: string = 'hallucination', threshold: number = 0.5) =>
    request<{ failures: Array<{ id: number; query: string; answer: string; failure_type: string; score: number; scores: Record<string, unknown> }>; total: number }>(
      `/results/failures?run_id=${runId}&failure_type=${failureType}&threshold=${threshold}`
    ),
  exportResults: (runId: number, format: string = 'json') => {
    window.open(`${API_BASE}/results/export?run_id=${runId}&format=${format}`, '_blank');
  },
};
