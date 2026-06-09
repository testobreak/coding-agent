import { useEffect, type ReactNode } from 'react';
import { useAuth } from './useAuth';

type Props = {
  children: ReactNode;
};

export function ProtectedRoute({ children }: Props) {
  const auth = useAuth();

  useEffect(() => {
    if (!auth.loading && !auth.error && !auth.authenticated) {
      auth.login(window.location.pathname);
    }
  }, [auth]);

  if (auth.error) {
    return (
      <main>
        <h1>HRMS</h1>
        <p>Auth init failed: {auth.error}</p>
      </main>
    );
  }

  if (auth.loading) {
    return (
      <main>
        <p>Loading...</p>
      </main>
    );
  }

  if (!auth.authenticated) {
    return (
      <main>
        <p>Redirecting to login...</p>
      </main>
    );
  }

  return <>{children}</>;
}
