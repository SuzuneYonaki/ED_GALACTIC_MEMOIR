// Traffic Monitor Addon Frontend Controller (opt-in manual EDSM/EDDN traffic lookup & cache display)
(function () {
  let activeFetchSeq = 0;

  function tr(key, fallback, vars) {
    if (typeof window.t === 'function') {
      const val = window.t(key, vars);
      if (val && val !== key) return val;
    }
    if (!vars) return fallback;
    let out = fallback;
    Object.keys(vars).forEach(k => {
      out = out.replace(new RegExp(`\\{${k}\\}`, 'g'), vars[k]);
    });
    return out;
  }

  function isTrafficAddonActive() {
    if (!window.__addonsInitialized) return false;
    return !(window.__disabledAddons && window.__disabledAddons.traffic_monitor);
  }

  function formatBreakdownTooltip(data) {
    const lines = [
      tr('traffic_badge_header_tip', 'EDSM / EDDN 通行統計 (累計: {total} / 週間: {week} / 24時間: {day})', {
        total: Number(data.total || 0).toLocaleString(),
        week: Number(data.week || 0).toLocaleString(),
        day: Number(data.day || 0).toLocaleString(),
      }),
    ];
    if (Array.isArray(data.breakdown) && data.breakdown.length > 0) {
      const topList = data.breakdown
        .slice(0, 8)
        .map(item => `${item.ship}: ${Number(item.count || 0).toLocaleString()}`)
        .join(', ');
      lines.push(tr('traffic_ships_label', '主な艦種内訳: {ships}', { ships: topList }));
    }
    if (data.fetched_at) {
      lines.push(tr('traffic_cached_at_label', '取得日時: {ts}', { ts: data.fetched_at }));
    }
    return lines.join('\n');
  }

  function renderTrafficBadge(sysAddr, data) {
    const badge = document.getElementById('current-system-traffic-badge');
    if (!badge) return;

    const currentSys = window.state && window.state.selectedSystem;
    if (!currentSys || String(currentSys.system_address) !== String(sysAddr)) return;

    if (!isTrafficAddonActive() || !data || !data.cached) {
      badge.style.display = 'none';
      badge.textContent = '';
      badge.title = '';
      return;
    }

    badge.style.display = 'inline-flex';
    badge.textContent = tr('traffic_badge_fmt', '🚦 通行: {total} (週:{week} / 日:{day})', {
      total: Number(data.total || 0).toLocaleString(),
      week: Number(data.week || 0).toLocaleString(),
      day: Number(data.day || 0).toLocaleString(),
    });
    badge.title = formatBreakdownTooltip(data);
  }

  async function refreshTrafficMonitorBadge() {
    const badge = document.getElementById('current-system-traffic-badge');
    const sys = window.state && window.state.selectedSystem;
    if (!sys || !sys.system_address || !isTrafficAddonActive()) {
      if (badge) {
        badge.style.display = 'none';
        badge.textContent = '';
      }
      return;
    }

    const seq = ++activeFetchSeq;
    const sysAddr = sys.system_address;
    try {
      const res = await fetch(`/api/systems/${sysAddr}/traffic`);
      if (!res.ok || seq !== activeFetchSeq) return;
      const data = await res.json();
      renderTrafficBadge(sysAddr, data);
    } catch (err) {
      console.warn('[TrafficMonitor] Failed to read traffic cache:', err);
    }
  }

  async function syncTrafficNow() {
    const btn = document.getElementById('btn-sync-traffic');
    const sys = window.state && window.state.selectedSystem;
    if (!sys || !sys.system_address || !btn) return;

    const sysAddr = sys.system_address;
    const idleLabel = tr('btn_sync_traffic_label', '🚦 トラフィック');
    btn.disabled = true;
    btn.textContent = tr('traffic_sync_running', '⏳ 照会中...');
    try {
      const res = await fetch(`/api/systems/${sysAddr}/traffic_sync`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderTrafficBadge(sysAddr, data);
      btn.textContent = tr('sync_done_label', '✓ 完了');
    } catch (err) {
      console.warn('[TrafficMonitor] Traffic sync failed:', err);
      btn.textContent = '⚠ Error';
    } finally {
      setTimeout(() => {
        btn.disabled = false;
        btn.textContent = tr('btn_sync_traffic_label', idleLabel);
      }, 1400);
    }
  }

  function initTrafficMonitor() {
    const btn = document.getElementById('btn-sync-traffic');
    btn?.addEventListener('click', syncTrafficNow);
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', initTrafficMonitor);
  }

  if (typeof window !== 'undefined') {
    window.refreshTrafficMonitorBadge = refreshTrafficMonitorBadge;
    window.syncTrafficNow = syncTrafficNow;
  }
})();
