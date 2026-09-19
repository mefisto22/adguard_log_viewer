import { useEffect } from 'react';
import { Link, useRoute } from './router';
import { Banner, Spinner } from './components/ui';
import { DashboardPage } from './pages/DashboardPage';
import { LogPage } from './pages/LogPage';
import { DevicesPage } from './pages/DevicesPage';
import { DeviceDetailPage } from './pages/DeviceDetailPage';
import { PersonsPage } from './pages/PersonsPage';
import { PersonDetailPage } from './pages/PersonDetailPage';
import { DomainsPage } from './pages/DomainsPage';
import { DomainDetailPage } from './pages/DomainDetailPage';
import { RulesPage } from './pages/RulesPage';
import { TagsPage } from './pages/TagsPage';
import { SavedFiltersPage } from './pages/SavedFiltersPage';
import { SettingsPage } from './pages/SettingsPage';
import { useAppStore } from './stores/useAppStore';
import { useT } from './i18n/useT';
import { startLiveUpdates, stopLiveUpdates } from './stores/liveUpdates';
import { useFilterStore } from './stores/useFilterStore';

const NAV = [
  { to: '/', key: 'nav.dashboard' },
  { to: '/log', key: 'nav.log' },
  { to: '/devices', key: 'nav.devices' },
  { to: '/persons', key: 'nav.people' },
  { to: '/domains', key: 'nav.domains' },
  { to: '/rules', key: 'nav.rules' },
  { to: '/tags', key: 'nav.tags' },
  { to: '/filters', key: 'nav.savedFilters' },
  { to: '/settings', key: 'nav.settings' },
] as const;

function ShieldIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2 4 5.2v6c0 5 3.4 9.7 8 10.8 4.6-1.1 8-5.8 8-10.8v-6L12 2Zm0 4.2 4.4 1.7v3.6c0 3.3-2 6.5-4.4 7.4V6.2Z" />
    </svg>
  );
}

function isActive(path: string, to: string): boolean {
  if (to === '/') return path === '/';
  return path === to || path.startsWith(`${to}/`);
}

function Page({ path, segments }: { path: string; segments: string[] }) {
  const t = useT();

  if (path === '/') return <DashboardPage />;
  if (path === '/log') return <LogPage />;

  if (segments[0] === 'devices') {
    return segments[1] ? <DeviceDetailPage id={Number(segments[1])} /> : <DevicesPage />;
  }
  if (segments[0] === 'persons') {
    return segments[1] ? <PersonDetailPage id={Number(segments[1])} /> : <PersonsPage />;
  }
  if (segments[0] === 'domains') {
    return segments[1] ? <DomainDetailPage id={Number(segments[1])} /> : <DomainsPage />;
  }
  if (path === '/rules') return <RulesPage />;
  if (path === '/tags') return <TagsPage />;
  if (path === '/filters') return <SavedFiltersPage />;
  if (path === '/settings') return <SettingsPage />;

  return (
    <div className="main">
      <Banner kind="warn" title={t('app.pageNotFound')}>
        <Link to="/">{t('app.backToDashboard')}</Link>
      </Banner>
    </div>
  );
}

export function App() {
  const route = useRoute();
  const t = useT();
  const { loaded, error, bootstrap, status, defaultRange, liveUpdates } = useAppStore();
  const setRange = useFilterStore((state) => state.setRange);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    if (defaultRange) setRange(defaultRange);
  }, [defaultRange, setRange]);

  // One connection for the whole app, started once the initial data is in.
  useEffect(() => {
    if (!loaded || !liveUpdates) return;
    startLiveUpdates();
    return stopLiveUpdates;
  }, [loaded, liveUpdates]);

  const providerDown = status?.provider && !status.provider.available;

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          <ShieldIcon />
          {t('app.title')}
        </Link>
        <nav className="nav">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={isActive(route.path, item.to) ? 'active' : undefined}
            >
              {t(item.key)}
            </Link>
          ))}
        </nav>
        {providerDown ? (
          <Link to="/settings" className="badge blocked" title={status?.provider?.detail}>
            {t('app.adguardUnreachable')}
          </Link>
        ) : null}
      </header>

      {!loaded ? (
        <div className="main">
          <Spinner label={t('app.starting')} />
        </div>
      ) : error ? (
        <div className="main">
          <Banner
            kind="error"
            title={t('app.backendUnreachable')}
            action={
              <button type="button" className="btn sm" onClick={() => void bootstrap()}>
                {t('common.retry')}
              </button>
            }
          >
            {error}
          </Banner>
        </div>
      ) : (
        <Page path={route.path} segments={route.segments} />
      )}
    </div>
  );
}
