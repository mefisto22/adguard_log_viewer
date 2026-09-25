/**
 * Settings and diagnostics.
 *
 * Connection details, the poll interval and the log level are app options —
 * Home Assistant owns them, so they are shown read-only with a pointer to where
 * they are changed. Everything else lives in the app's own database and is
 * editable here.
 */

import { useState } from 'react';
import { Banner, Section, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { useAppStore } from '../stores/useAppStore';
import { formatBytes, formatDateTime, formatNumber, formatRelative } from '../utils/format';
import { rangeKey, type LanguagePreference } from '../i18n';
import { useLanguage, useT } from '../i18n/useT';

/**
 * The language menu. Each language names itself — a Hungarian reader looking
 * for their language should find "Magyar", not "Hungarian", whichever language
 * the page happens to be in at the time.
 */
const LANGUAGE_NAMES: Record<string, string> = { en: 'English', hu: 'Magyar' };

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

export function SettingsPage() {
  const t = useT();
  const language = useLanguage();
  const app = useAppStore();
  // The status carries text the backend translated for us — the AdGuard
  // diagnostics below — so a language change has to fetch it again.
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([endpoints.settings(), endpoints.status()]),
    [language],
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
          ? t('settings.cleanupDone', {
              count: formatNumber(Number(result.deleted_queries ?? 0)),
            })
          : label === 'reclassify'
            ? t('settings.reclassifyDone', { count: formatNumber(Number(result.marked ?? 0)) })
            : t('settings.done'),
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
        <Spinner label={t('settings.loading')} />
      </div>
    );

  const provider = status.provider;
  const discovery = status.discovery;

  const retentionLabel = (days: number) =>
    days === 0 ? t('settings.unlimited') : days === 1 ? t('settings.day') : t('settings.days', { count: days });

  return (
    <div className="main">
      {notice ? <Banner kind="info">{notice}</Banner> : null}

      {provider && !provider.available ? (
        <Banner
          kind="error"
          title={t('settings.adguardNotReachable')}
          action={
            <button
              type="button"
              className="btn sm"
              disabled={busy !== null}
              onClick={() => void run('reconnect', endpoints.reconnect)}
            >
              {t('settings.retryDiscovery')}
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
        <Banner kind="warn" title={t('settings.ingestFailed')}>
          {status.ingest.error}
        </Banner>
      ) : null}

      <div className="grid" style={{ gap: 12 }}>
        <Section title={t('settings.appearance')}>
          {/* Top-aligned: only the language field carries a hint, and centring
              the row would leave its select sitting above the others. */}
          <div className="row wrap" style={{ gap: 16, alignItems: 'flex-start' }}>
            <label className="field">
              {t('settings.language')}
              <select
                value={app.languagePreference}
                onChange={(event) => app.setLanguage(event.target.value as LanguagePreference)}
              >
                <option value="auto">{t('settings.languageAuto')}</option>
                {Object.entries(LANGUAGE_NAMES).map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
              <span className="faint">{t('settings.languageHint')}</span>
            </label>

            <label className="field">
              {t('settings.theme')}
              <select
                value={app.theme}
                onChange={(event) =>
                  app.setTheme(event.target.value as 'system' | 'light' | 'dark')
                }
              >
                <option value="system">{t('settings.themeSystem')}</option>
                <option value="light">{t('settings.themeLight')}</option>
                <option value="dark">{t('settings.themeDark')}</option>
              </select>
            </label>

            <label className="field">
              {t('settings.density')}
              <select
                value={app.density}
                onChange={(event) =>
                  app.setDensity(event.target.value as 'comfortable' | 'compact')
                }
              >
                <option value="comfortable">{t('settings.densityComfortable')}</option>
                <option value="compact">{t('settings.densityCompact')}</option>
              </select>
            </label>

            <label className="field">
              {t('settings.defaultRange')}
              <select
                value={String(settings.app['ui.default_range'] ?? '24h')}
                onChange={(event) => void updateSetting('ui.default_range', event.target.value)}
              >
                {['15m', '1h', '6h', '24h', '7d', '30d', 'all'].map((range) => {
                  const key = rangeKey(range);
                  return (
                    <option key={range} value={range}>
                      {key ? t(key) : range}
                    </option>
                  );
                })}
              </select>
            </label>

            <label className="field">
              {t('settings.pageSize')}
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

        <Section title={t('settings.retention')}>
          {/* The hint sits under the whole row rather than inside the field:
              as part of the label it made the field taller than the button
              beside it, which then hung below the select it belongs with. */}
          <div className="row wrap" style={{ gap: 16, alignItems: 'flex-end' }}>
            <label className="field">
              {t('settings.keepFor')}
              <select
                value={String(settings.effective.retention_days)}
                onChange={(event) => void updateSetting('retention_days', Number(event.target.value))}
              >
                {settings.choices.retention_days.map((days) => (
                  <option key={days} value={days}>
                    {retentionLabel(days)}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => void run('cleanup', endpoints.runCleanup)}
            >
              {busy === 'cleanup' ? t('settings.cleaning') : t('settings.runCleanup')}
            </button>
          </div>
          <div className="faint small" style={{ marginTop: 6 }}>
            {t('settings.retentionHint')}
          </div>
        </Section>

        <Section title={t('settings.ingest')}>
          <div className="row wrap" style={{ gap: 16, alignItems: 'flex-end' }}>
            <label className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={Boolean(settings.app['ingest.enabled'])}
                onChange={(event) => void updateSetting('ingest.enabled', event.target.checked)}
              />
              {t('settings.importNew')}
            </label>
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => void run('ingest', endpoints.runIngest)}
            >
              {t('settings.pollNow')}
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => void run('reclassify', endpoints.reclassify)}
            >
              {busy === 'reclassify' ? t('settings.queueing') : t('settings.reclassifyAll')}
            </button>
          </div>

          <dl className="kv" style={{ marginTop: 14 }}>
            <Row label={t('settings.source')}>
              {provider ? `${provider.name} — ${provider.source}` : t('settings.notConfigured')}
            </Row>
            <Row label={t('settings.status')}>
              {provider?.available ? (
                <span className="badge allowed">{t('settings.connected')}</span>
              ) : (
                <span className="badge blocked">{t('settings.unavailable')}</span>
              )}{' '}
              <span className="muted">{provider?.detail}</span>
            </Row>
            {discovery ? (
              <Row label={t('settings.address')}>
                {discovery.url ? (
                  <span className="mono">{discovery.url}</span>
                ) : (
                  <span className="muted">{t('settings.addressUnknown')}</span>
                )}
                {discovery.source === 'configuration'
                  ? ` ${t('settings.fromOptions')}`
                  : discovery.slug
                    ? ` ${t('settings.foundAs', { slug: discovery.slug })}`
                    : ''}
              </Row>
            ) : null}
            {discovery && discovery.source !== 'configuration' ? (
              <Row label={t('settings.howLookedUp')}>
                {discovery.steps.length ? (
                  <ol style={{ margin: 0, paddingLeft: '1.1em' }}>
                    {discovery.steps.map((step) => (
                      <li key={step} className="small">
                        {step}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <span className="muted">—</span>
                )}
                {Object.keys(discovery.ports).length ? (
                  <div className="small muted" style={{ marginTop: 6 }}>
                    {t('settings.reportedPorts', {
                      ports: Object.entries(discovery.ports)
                        .map(
                          ([key, value]) =>
                            `${key} → ${value ?? t('settings.portNotPublished')}`,
                        )
                        .join(', '),
                    })}
                  </div>
                ) : null}
              </Row>
            ) : null}
            <Row label={t('settings.lastPoll')}>
              {status.ingest.last.at_ns
                ? formatRelative(Number(status.ingest.last.at_ns))
                : t('settings.notYet')}
            </Row>
            <Row label={t('settings.lastImport')}>
              {status.ingest.last_import?.at_ns ? (
                t('settings.records', {
                  count: formatNumber(Number(status.ingest.last_import.inserted)),
                  when: formatRelative(Number(status.ingest.last_import.at_ns)),
                })
              ) : (
                <span className="muted">{t('settings.nothingImported')}</span>
              )}
            </Row>
            <Row label={t('settings.pollInterval')}>{settings.effective.poll_interval}s</Row>
            <Row label={t('settings.liveStream')}>
              {t('settings.subscribers', { count: status.stream.subscribers })}
            </Row>
          </dl>
        </Section>

        <Section title={t('settings.database')}>
          <dl className="kv">
            <Row label={t('settings.queriesStored')}>{formatNumber(status.database.queries)}</Row>
            <Row label={t('settings.oldestRecord')}>{formatDateTime(status.database.oldest_ns)}</Row>
            <Row label={t('settings.newestRecord')}>{formatDateTime(status.database.newest_ns)}</Row>
            <Row label={t('settings.domains')}>{formatNumber(status.database.domains)}</Row>
            <Row label={t('settings.devices')}>{formatNumber(status.database.clients)}</Row>
            <Row label={t('settings.people')}>{formatNumber(status.database.persons)}</Row>
            <Row label={t('settings.tags')}>{formatNumber(status.database.tags)}</Row>
            <Row label={t('settings.categorisationRules')}>
              {formatNumber(status.ingest.engine_rules)}
            </Row>
            <Row label={t('settings.pendingReclassification')}>
              {formatNumber(status.database.pending_reclassification)}
            </Row>
            <Row label={t('settings.fileSize')}>{formatBytes(status.database.size_bytes)}</Row>
            <Row label={t('settings.location')}>
              <span className="mono small">{status.database.path}</span>
            </Row>
            <Row label={t('settings.schemaVersion')}>
              {t('settings.schemaOf', {
                current: status.database.schema_version,
                target: status.schema_target,
              })}
            </Row>
          </dl>
        </Section>

        <Section title={t('settings.addonOptions')}>
          <p className="muted small" style={{ marginTop: 0 }}>
            {t('settings.addonOptionsIntro')}
          </p>
          <dl className="kv">
            {Object.entries(settings.addon_options).map(([key, value]) => (
              <Row key={key} label={key}>
                <span className="mono small">
                  {typeof value === 'boolean'
                    ? value
                      ? t('common.yes')
                      : t('common.no')
                    : String(value)}
                </span>
              </Row>
            ))}
          </dl>
        </Section>

        <Section title={t('settings.about')}>
          <dl className="kv">
            <Row label={t('settings.version')}>{status.version}</Row>
            <Row label={t('settings.started')}>{formatDateTime(status.started_at_ns)}</Row>
            {status.process?.descriptors ? (
              <Row label={t('settings.descriptors')}>
                <span
                  className={status.process.descriptors.ratio >= 0.8 ? 'badge blocked' : undefined}
                >
                  {t('settings.descriptorsValue', {
                    open: formatNumber(status.process.descriptors.open),
                    limit: formatNumber(status.process.descriptors.limit),
                  })}
                </span>
              </Row>
            ) : null}
            <Row label={t('settings.privacy')}>{t('settings.privacyText')}</Row>
          </dl>
        </Section>
      </div>

      {loading ? <Spinner /> : null}
    </div>
  );
}
