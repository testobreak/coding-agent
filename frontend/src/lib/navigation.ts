import type { LucideIcon } from 'lucide-react';
import {
  Briefcase,
  Building2,
  ClipboardList,
  FileText,
  FolderKanban,
  LayoutDashboard,
  MapPin,
  Settings,
  Shield,
  Users,
  Wallet,
} from 'lucide-react';
import { Roles, type Role } from './roles';

export type NavItem = {
  label: string;
  path: string;
  icon: LucideIcon;
  /** Empty = any authenticated user. */
  roles: Role[];
  section?: 'main' | 'admin';
};

export const navItems: NavItem[] = [
  {
    label: 'Dashboard',
    path: '/dashboard',
    icon: LayoutDashboard,
    roles: [],
    section: 'main',
  },
  {
    label: 'Employees',
    path: '/employees',
    icon: Users,
    roles: [
      Roles.SUPER_ADMIN,
      Roles.HR_ADMIN,
      Roles.FINANCE_ADMIN,
      Roles.LEADERSHIP,
      Roles.MANAGER,
      Roles.PROJECT_MANAGER,
      Roles.EMPLOYEE,
    ],
    section: 'main',
  },
  {
    label: 'Departments',
    path: '/departments',
    icon: Building2,
    roles: [
      Roles.SUPER_ADMIN,
      Roles.HR_ADMIN,
      Roles.FINANCE_ADMIN,
      Roles.LEADERSHIP,
      Roles.MANAGER,
      Roles.PROJECT_MANAGER,
      Roles.EMPLOYEE,
    ],
    section: 'main',
  },
  {
    label: 'Designations',
    path: '/designations',
    icon: Briefcase,
    roles: [
      Roles.SUPER_ADMIN,
      Roles.HR_ADMIN,
      Roles.FINANCE_ADMIN,
      Roles.LEADERSHIP,
      Roles.MANAGER,
      Roles.PROJECT_MANAGER,
      Roles.EMPLOYEE,
    ],
    section: 'main',
  },
  {
    label: 'Locations',
    path: '/locations',
    icon: MapPin,
    roles: [
      Roles.SUPER_ADMIN,
      Roles.HR_ADMIN,
      Roles.FINANCE_ADMIN,
      Roles.LEADERSHIP,
      Roles.MANAGER,
      Roles.PROJECT_MANAGER,
      Roles.EMPLOYEE,
    ],
    section: 'main',
  },
  {
    label: 'Documents',
    path: '/documents',
    icon: FileText,
    roles: [
      Roles.SUPER_ADMIN,
      Roles.HR_ADMIN,
      Roles.EMPLOYEE,
    ],
    section: 'main',
  },
  {
    label: 'Clients',
    path: '/clients',
    icon: Building2,
    roles: [
      Roles.SUPER_ADMIN,
      Roles.HR_ADMIN,
      Roles.FINANCE_ADMIN,
      Roles.LEADERSHIP,
      Roles.MANAGER,
      Roles.PROJECT_MANAGER,
    ],
    section: 'main',
  },
  {
    label: 'Projects',
    path: '/projects',
    icon: FolderKanban,
    roles: [
      Roles.SUPER_ADMIN,
      Roles.HR_ADMIN,
      Roles.FINANCE_ADMIN,
      Roles.LEADERSHIP,
      Roles.MANAGER,
      Roles.PROJECT_MANAGER,
      Roles.EMPLOYEE,
    ],
    section: 'main',
  },
  {
    label: 'Allocations',
    path: '/allocations',
    icon: ClipboardList,
    roles: [
      Roles.SUPER_ADMIN,
      Roles.HR_ADMIN,
      Roles.FINANCE_ADMIN,
      Roles.LEADERSHIP,
      Roles.MANAGER,
      Roles.PROJECT_MANAGER,
      Roles.EMPLOYEE,
    ],
    section: 'main',
  },
  {
    label: 'Salary',
    path: '/salary',
    icon: Wallet,
    roles: [Roles.SUPER_ADMIN, Roles.HR_ADMIN, Roles.FINANCE_ADMIN, Roles.EMPLOYEE],
    section: 'main',
  },
  {
    label: 'Audit log',
    path: '/audit',
    icon: Shield,
    roles: [Roles.SUPER_ADMIN],
    section: 'admin',
  },
  {
    label: 'Settings',
    path: '/settings',
    icon: Settings,
    roles: [Roles.SUPER_ADMIN],
    section: 'admin',
  },
];

export function filterNavForRoles(roles: string[]): NavItem[] {
  return navItems.filter((item) => hasAnyRoleForNav(roles, item.roles));
}

function hasAnyRoleForNav(userRoles: string[], required: Role[]): boolean {
  if (required.length === 0) {
    return true;
  }
  const set = new Set(userRoles);
  return required.some((r) => set.has(r));
}

export const routeTitles: Record<string, string> = Object.fromEntries(
  navItems.map((item) => [item.path, item.label]),
);

routeTitles['/'] = 'Home';

export function titleForPath(pathname: string): string {
  if (routeTitles[pathname]) {
    return routeTitles[pathname];
  }
  const match = navItems.find((item) => pathname.startsWith(`${item.path}/`));
  return match?.label ?? 'Page';
}
