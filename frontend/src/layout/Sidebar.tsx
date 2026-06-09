import { NavLink } from 'react-router-dom';
import { filterNavForRoles, type NavItem } from '@/lib/navigation';
import { cn } from '@/lib/utils';
import { useMe } from '@/hooks/useMe';

function NavSection({ title, items }: { title: string; items: NavItem[] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="mt-6">
      <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-sidebar-muted">
        {title}
      </p>
      <ul className="space-y-0.5">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-sidebar-active text-sidebar-foreground'
                      : 'text-sidebar-muted hover:bg-sidebar-active/60 hover:text-sidebar-foreground',
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                {item.label}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function Sidebar() {
  const { data: me } = useMe();
  const roles = me?.roles ?? [];
  const visible = filterNavForRoles(roles);
  const main = visible.filter((i) => i.section !== 'admin');
  const admin = visible.filter((i) => i.section === 'admin');

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-sidebar-active bg-sidebar text-sidebar-foreground">
      <div className="border-b border-sidebar-active px-4 py-5">
        <p className="text-lg font-semibold tracking-tight">HRMS</p>
        <p className="text-xs text-sidebar-muted">Acme internal</p>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-4">
        <NavSection title="Main" items={main} />
        <NavSection title="Admin" items={admin} />
      </nav>
    </aside>
  );
}
