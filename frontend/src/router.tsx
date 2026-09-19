/**
 * Hash-based router.
 *
 * Home Assistant ingress mounts the app under a generated path prefix. With
 * hash routing the browser's path never changes, so relative asset and API URLs
 * stay correct no matter what prefix the session was given — and a reload deep
 * in the app still lands on the right page.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

export interface Route {
  path: string;
  segments: string[];
  query: URLSearchParams;
}

function parse(): Route {
  const raw = window.location.hash.replace(/^#/, '') || '/';
  const [pathPart, queryPart] = raw.split('?');
  const path = pathPart.startsWith('/') ? pathPart : `/${pathPart}`;
  return {
    path,
    segments: path.split('/').filter(Boolean),
    query: new URLSearchParams(queryPart ?? ''),
  };
}

export function navigate(to: string, options: { replace?: boolean } = {}): void {
  const target = `#${to.startsWith('/') ? to : `/${to}`}`;
  if (options.replace) {
    window.history.replaceState(null, '', target);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  } else {
    window.location.hash = target;
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse);

  useEffect(() => {
    const onChange = () => {
      setRoute(parse());
      // A new page should start at the top, like a real navigation.
      document.querySelector('.main')?.scrollTo({ top: 0 });
    };
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  return route;
}

interface LinkProps {
  to: string;
  children: ReactNode;
  className?: string;
  title?: string;
  onClick?: () => void;
}

export function Link({ to, children, className, title, onClick }: LinkProps) {
  const handle = useCallback(
    (event: React.MouseEvent<HTMLAnchorElement>) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      onClick?.();
      navigate(to);
    },
    [to, onClick],
  );
  return (
    <a href={`#${to}`} className={className} title={title} onClick={handle}>
      {children}
    </a>
  );
}

/** True when `prefix` is the active section. */
export function useIsActive(prefix: string): boolean {
  const route = useRoute();
  return useMemo(() => {
    if (prefix === '/') return route.path === '/';
    return route.path === prefix || route.path.startsWith(`${prefix}/`);
  }, [route.path, prefix]);
}
