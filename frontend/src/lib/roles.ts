export const Roles = {
  SUPER_ADMIN: 'SUPER_ADMIN',
  HR_ADMIN: 'HR_ADMIN',
  FINANCE_ADMIN: 'FINANCE_ADMIN',
  LEADERSHIP: 'LEADERSHIP',
  MANAGER: 'MANAGER',
  PROJECT_MANAGER: 'PROJECT_MANAGER',
  EMPLOYEE: 'EMPLOYEE',
} as const;

export type Role = (typeof Roles)[keyof typeof Roles];

export function hasAnyRole(userRoles: string[], required: Role[]): boolean {
  if (required.length === 0) {
    return true;
  }
  const set = new Set(userRoles);
  return required.some((r) => set.has(r));
}

export function hasAllRoles(userRoles: string[], required: Role[]): boolean {
  const set = new Set(userRoles);
  return required.every((r) => set.has(r));
}
