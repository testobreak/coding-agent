import Keycloak from 'keycloak-js';
import { createContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { createKeycloak, setKeycloakInstance } from './keycloak';

type AuthContextValue = {
  keycloak: Keycloak | null;
  loading: boolean;
  error: string | null;
  authenticated: boolean;
  token?: string;
  login: (redirectPath?: string) => void;
  logout: () => void;
};

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

type Props = {
  children: ReactNode;
};

export function AuthProvider({ children }: Props) {
  const [keycloak, setKeycloak] = useState<Keycloak | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let kc: Keycloak;
    try {
      kc = createKeycloak();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
      return;
    }

    kc.init({
      onLoad: 'check-sso',
      pkceMethod: 'S256',
      silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
    })
      .then(() => {
        setKeycloakInstance(kc);
        setKeycloak(kc);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });

    return () => {
      setKeycloakInstance(null);
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    const authenticated = keycloak?.authenticated === true;
    return {
      keycloak,
      loading,
      error,
      authenticated,
      token: keycloak?.token,
      login: (redirectPath = '/dashboard') => {
        keycloak?.login({
          redirectUri: `${window.location.origin}${redirectPath}`,
        });
      },
      logout: () => {
        keycloak?.logout({ redirectUri: window.location.origin });
      },
    };
  }, [keycloak, loading, error]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

