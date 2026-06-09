import { LogOut, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/auth/useAuth';
import { useMe } from '@/hooks/useMe';
import { titleForPath } from '@/lib/navigation';
import { useLocation } from 'react-router-dom';

export function Header() {
  const auth = useAuth();
  const { data: me, isLoading } = useMe();
  const { pathname } = useLocation();
  const pageTitle = titleForPath(pathname);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-6">
      <h1 className="text-lg font-semibold">{pageTitle}</h1>
      <div className="flex items-center gap-4">
        {isLoading ? (
          <Skeleton className="h-8 w-32" />
        ) : (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <User className="h-4 w-4" aria-hidden />
            {me?.username ?? me?.email ?? 'User'}
          </span>
        )}
        <Button type="button" variant="outline" size="sm" onClick={auth.logout}>
          <LogOut className="h-4 w-4" aria-hidden />
          Sign out
        </Button>
      </div>
    </header>
  );
}

