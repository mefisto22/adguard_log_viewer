/**
 * Settings and diagnostics.
 *
 * Connection details, the poll interval and the log level are add-on options —
 * Home Assistant owns them, so they are shown read-only with a pointer to where
 * they are changed. Everything else lives in the add-on's own database and is
 * editable here.
 */

import { useState } from 'react';
import { Banner, Section, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { useAppStore } from '../stores/useAppStore';
import { formatBytes, formatDateTime, formatNumber, formatRelative } from '../utils/format';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

export function SettingsPage() {
  const app = useAppStore();
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([endpoints.settings(), endpoints.status()]),
    [],
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const settings = data?.[0];
  const status = data?.[1];

  const run = async (label: string, action: () => Promise<unknown>) => {
    setBusy(label);
    setNotice(null);
    try {
      const result = (await action()) as Record<string, unknown>;
      setNotice(
        label === 'cleanup'
          ? `Removed ${formatNumber(Number(result.deleted_queries ?? 0))} old queries.`
          : label === 'reclassify'
            ? `${formatNumber(Number(result.marked ?? 0))} domains queued for re-classification.`
            : 'Done.',
      );
      reload();
      await app.refreshStatus();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const updateSetting = async (key: string, value: unknown) => {
    const updated = await endpoints.updateSettings({ [key]: value });
    app.setPreferences(updated.app);
    reload();
  };

  if (error) return <div className="main"><Banner kind="error">{error}</Banner></div>;
  if (!settings || !status)
    return (
      <div className="main">
        <Spinner label="Loading settings…" />
      </div>
    );

  const provider = status.provider;
  const discovery = status.discovery;

  return (
    <div className="main">
      {notice ? <Banner kind="info">{notice}</Banner> : null}

      {provider && !provider.available ? (
        <Banner
          kind="error"
          title="AdGuard Home is not reachable"
          action={
            <button
              type="button"
              className="btn sm"
              disabled={busy !== null}
              onClick={() => void run('reconnect', endpoints.reconnect)}
            >
              Retry discovery
            </button>
          }
        >
          {provider.detail}
        </Banner>
      ) : null}

      {(discovery?.warnings ?? []).map((warning) => (
        <Banner key={warning} kind="warn">
          {warning}
        </Banner>
      ))}
      {(provider?.warnings ?? []).map((warning) => (
        <Banner key={warning} kind="warn">
          {warning}
        </Banner>
      ))}
      {status.ingest.error ? (
        <Banner kind="warn" title="The last ingest attempt failed">
          {status.ingest.error}
        </Banner>
      ) : null}

      <div className="grid" style={{ gap: 12 }}>
        <Section title="Appearance">
          <div className="row wrap" style={{ gap: 16 }}>
            <label className="field">
              Theme
              <select
                value={app.theme}
                onChange={(event) =>
                  app.setTheme(event.target.value as 'system' | 'light' | 'dark')
                }
              >
                <option value="system">Follow the system</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>

            <label className="field">
              Row density
              <select
                value={app.density}
                onChange={(event) =>
                  app.setDensity(event.target.value as 'comfortable' | 'compact')
                }
              >
                <option value="comfortable">Comfortable</option>
                <option value="compact">Compact</option>
              </select>
            </label>

            <label className="field">
              Default time range
              <select
                value={String(settings.app['ui.default_range'] ?? '24h')}
                onChange={(event) => void updateSetting('ui.default_range', event.target.value)}
              >
                {['15m', '1h', '6h', '24h', '7d', '30d', 'all'].map((range) => (
                  <option key={range} value={range}>
                    {range}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              Rows per page
              <input
                type="number"
                min={25}
                max={500}
                step={25}
                value={Number(settings.app['ui.page_size'] ?? 100)}
                onChange={(event) => void updateSetting('ui.page_size', Number(event.target.value))}
              />
            </label>
          </div>
        </Section>

        <Section title="Data retention">
          <div className="row wrap" style={{ gap: 16, alignItems: 'flex-end' }}>
            <label className="field">
              Keep query history for
              <select
                value={String(settings.effective.retention_days)}
                onChange={(event) => void updateSetting('retention_days', Number(event.target.value))}
              >
                {settings.choices.retention_days.map((days) => (
                  <option key={days} value={days}>
                    {days === 0 ? 'Unlimited' : `${days} day${days === 1 ? '' : 's'}`}
                  </option>
                ))}
              </select>
              <span className="faint">
                Overrides the add-on option. Older queries are removed automatically.
              </span>
            </label>

            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => void run('cleanup', endpoints.runCleanup)}
            >
              {busy === 'cleanup' ? 'Cleaning…' : 'Run cleanup now'}
            </button>
          </div>
        </Section>

        <Section title="Ingest">
          <div className="row wrap" style={{ gap: 16, alignItems: 'flex-end' }}>
            <label className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={Boolean(settings.app['ingest.enabled'])}
                onChange={(event) => void updateSetting('ingest.enabled', event.target.checked)}
              />
              Import new queries from AdGuard
            </label>
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => void run('ingest', endpoints.runIngest)}
            >
              Poll now
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => void run('reclassify', endpoints.reclassify)}
            >
              {busy === 'reclassify' ? 'Queueing…' : 'Re-classify all domains'}
            </button>
          </div>

          <dl className="kv" style={{ marginTop: 14 }}>
            <Row label="Source">
              {provider ? `${provider.name} — ${provider.source}` : 'not configured'}
            </Row>
            <Row label="Status">
              {provider?.available ? (
                <span className="badge allowed">connected</span>
              ) : (
                <span className="badge blocked">unavailable</span>
              )}{' '}
              <span className="muted">{provider?.detail}</span>
            </Row>
            {discovery ? (
              <Row label="Discovered via">
                {discovery.source}
                {discovery.slug ? ` (${discovery.slug})` : ''}
                {discovery.version ? ` · AdGuard add-on ${discovery.version}` : ''}
              </Row>
            ) : null}
            <Row label="Last poll">
              {status.ingest.last.at_ns
                ? formatRelative(Number(status.ingest.last.at_ns))
                : 'not yet'}
            </Row>
            <Row label="Last import">
              {status.ingest.last_import?.at_ns ? (
                <>
                  {formatNumber(Number(status.ingest.last_import.inserted))} record(s),{' '}
                  {formatRelative(Number(status.ingest.last_import.at_ns))}
                </>
              ) : (
                <span className="muted">nothing imported yet</span>
              )}
            </Row>
            <Row label="Poll interval">{settings.effective.poll_interval}s</Row>
            <Row label="Live stream">{status.stream.subscribers} subscriber(s)</Row>
          </dl>
        </Section>

        <Section title="Database">
          <dl className="kv">
            <Row label="Queries stored">{formatNumber(status.database.queries)}</Row>
            <Row label="Oldest record">{formatDateTime(status.database.oldest_ns)}</Row>
            <Row label="Newest record">{formatDateTime(status.database.newest_ns)}</Row>
            <Row label="Domains">{formatNumber(status.database.domains)}</Row>
            <Row label="Devices">{formatNumber(status.database.clients)}</Row>
            <Row label="People">{formatNumber(status.database.persons)}</Row>
            <Row label="Tags">{formatNumber(status.database.tags)}</Row>
            <Row label="Categorisation rules">{formatNumber(status.ingest.engine_rules)}</Row>
            <Row label="Pending re-classification">
              {formatNumber(status.database.pending_reclassification)}
            </Row>
            <Row label="File size">{formatBytes(status.database.size_bytes)}</Row>
            <Row label="Location">
              <span className="mono small">{status.database.path}</span>
            </Row>
            <Row label="Schema version">
              {status.database.schema_version} of {status.schema_target}
            </Row>
          </dl>
        </Section>

        <Section title="Add-on options (read-only)">
          <p className="muted small" style={{ marginTop: 0 }}>
            These come from Home Assistant. Change them on the add-on's Configuration tab and
            restart the add-on.
          </p>
          <dl className="kv">
            {Object.entries(settings.addon_options).map(([key, value]) => (
              <Row key={key} label={key}>
                <span className="mono small">
                  {typeof value === 'boolean' ? (value ? 'yes' : 'no') : String(value)}
                </span>
              </Row>
            ))}
          </dl>
        </Section>

        <Section title="About">
          <dl className="kv">
            <Row label="Version">{status.version}</Row>
            <Row label="Started">{formatDateTime(status.started_at_ns)}</Row>
            <Row label="Privacy">
              No DNS data leaves this machine. There is no telemetry, no cloud analytics and no
              external API call other than to AdGuard Home and the Supervisor.
            </Row>
          </dl>
        </Section>
      </div>

      {loading ? <Spinner /> : null}
    </div>
  );
}
