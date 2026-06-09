import { Link, useLocation } from 'react-router-dom';
import { routeTitles } from '@/lib/navigation';

export function Breadcrumbs() {
  const { pathname } = useLocation();

  if (pathname === '/' || pathname === '/dashboard') {
    return null;
  }

  const segments = pathname.split('/').filter(Boolean);
  const crumbs: { label: string; path: string }[] = [];
  let acc = '';

  for (const segment of segments) {
    acc += `/${segment}`;
    const label = routeTitles[acc] ?? segment;
    crumbs.push({ label, path: acc });
  }

  return (
    <nav aria-label="Breadcrumb" className="border-b border-border bg-muted/40 px-6 py-2 text-sm">
      <ol className="flex flex-wrap items-center gap-1 text-muted-foreground">
        <li>
          <Link to="/dashboard" className="hover:text-foreground">
            Dashboard
          </Link>
        </li>
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return (
            <li key={crumb.path} className="flex items-center gap-1">
              <span aria-hidden>/</span>
              {isLast ? (
                <span className="font-medium text-foreground">{crumb.label}</span>
              ) : (
                <Link to={crumb.path} className="hover:text-foreground">
                  {crumb.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
