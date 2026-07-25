import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { Activity } from 'lucide-react';

interface HealthStatus {
  postgres?: string;
  neo4j?: string;
  redis?: string;
  status: string;
}

const fetchHealth = async (): Promise<HealthStatus> => {
  try {
    return await apiClient.get('/health/ready');
  } catch (error: unknown) {
    if (error instanceof Error) throw new Error(error.message);
    throw new Error(String(error));
  }
};

export const SystemHealth: React.FC = () => {
  const { data, error, isLoading } = useQuery<HealthStatus>({
    queryKey: ['health'],
    queryFn: fetchHealth,
    retry: false,
    refetchInterval: 5000,
  });

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-lg border border-slate-100 p-8 max-w-md w-full">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-3 bg-blue-50 rounded-lg">
            <Activity className="w-6 h-6 text-blue-600" />
          </div>
          <h1 className="text-2xl font-semibold text-slate-800">System Health</h1>
        </div>

        {isLoading ? (
          <div className="text-slate-500 text-center py-4">Checking systems...</div>
        ) : (
          <div className="space-y-4">
            <ServiceBadge name="PostgreSQL" status={data?.postgres} />
            <ServiceBadge name="Neo4j" status={data?.neo4j} />
            <ServiceBadge name="Redis" status={data?.redis} />
            
            {error && (
              <div className="mt-6 p-4 bg-red-50 text-red-700 rounded-lg text-sm">
                Failed to connect to backend: {(error as Error).message}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

const ServiceBadge: React.FC<{ name: string; status?: string }> = ({ name, status }) => {
  const isOk = status === 'ok';
  
  return (
    <div className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50">
      <span className="font-medium text-slate-700">{name}</span>
      <span
        className={`px-3 py-1 rounded-full text-xs font-medium border ${
          isOk ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 
          status ? 'bg-rose-100 text-rose-700 border-rose-200' : 
          'bg-slate-200 text-slate-600 border-slate-300'
        }`}
      >
        {status || 'unknown'}
      </span>
    </div>
  );
};
