import { useQuery } from '@tanstack/react-query';
import { fetchMe } from '@/api/services/meService';
import { useAuth } from '@/auth/useAuth';

export function useMe() {
  const { authenticated } = useAuth();

  return useQuery({
    queryKey: ['me'],
    queryFn: fetchMe,
    enabled: authenticated,
    staleTime: 60_000,
  });
}
