import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { useMe } from '@/hooks/useMe';
import { hasAnyRole, type Role } from '@/lib/roles';

type Props = {
  children: ReactNode;
  roles: Role[];
};

export function RoleRoute({ children, roles }: Props) {
  const { data: me, isLoading, isError } = useMe();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (isError || !me) {
    return <Navigate to="/dashboard" replace />;
  }

  if (!hasAnyRole(me.roles, roles)) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}
