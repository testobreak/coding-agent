import Keycloak from 'keycloak-js';

let keycloakInstance: Keycloak | null = null;

function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, '');
}

export function createKeycloak(): Keycloak {
  const baseUrl = import.meta.env.VITE_KEYCLOAK_URL;
  const realm = import.meta.env.VITE_KEYCLOAK_REALM;
  const clientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID;

  if (!baseUrl || !realm || !clientId) {
    throw new Error(
      'Missing VITE_KEYCLOAK_URL, VITE_KEYCLOAK_REALM, or VITE_KEYCLOAK_CLIENT_ID. See .env.example.',
    );
  }

  const issuer = `${stripTrailingSlash(baseUrl)}/realms/${encodeURIComponent(realm)}`;

  return new Keycloak({
    clientId,
    oidcProvider: issuer,
  });
}

export function setKeycloakInstance(instance: Keycloak | null): void {
  keycloakInstance = instance;
}

export async function getAccessToken(): Promise<string> {
  if (!keycloakInstance) {
    throw new Error('Auth client is not initialized');
  }

  await keycloakInstance.updateToken(30);

  if (!keycloakInstance.token) {
    throw new Error('Access token is missing');
  }

  return keycloakInstance.token;
}
