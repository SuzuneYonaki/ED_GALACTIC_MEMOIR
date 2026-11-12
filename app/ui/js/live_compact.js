// Live Compact HUD / Simplified Display Controller
(function () {
  const LS_KEY_ENABLED = 'ed_live_compact_mode';
  const LS_KEY_AUTO_PANES = 'ed_live_compact_auto_panes';

  let lastAppliedActive = null;
  let savedPreCompactPanes = null;

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

  function isCompactEnabled() {
    if (typeof window.state !== 'undefined' && typeof window.state.liveCompactEnabled === 'boolean') {
      return window.state.liveCompactEnabled;
    }
    try { return localStorage.getItem(LS_KEY_ENABLED) === 'true'; } catch (e) { return false; }
  }

  function isAutoCollapsePanesEnabled() {
    if (typeof window.state !== 'undefined' && typeof window.state.liveCompactAutoCollapse === 'boolean') {
      return window.state.liveCompactAutoCollapse;
    }
    try { return localStorage.getItem(LS_KEY_AUTO_PANES) !== 'false'; } catch (e) { return true; }
  }

  function isLiveEnabled() {
    return typeof window.state !== 'undefined' && Boolean(window.state.liveSyncEnabled);
  }

  function isLiveCompactActive() {
    return isLiveEnabled() && isCompactEnabled();
  }

  function computeCompactHudSummary(st) {
    const sys = (st && st.selectedSystem) || null;
    const detail = (st && st.currentSystemData && st.currentSystemData.system) || sys || {};
    const bodies = (st && st.currentSystemData && Array.isArray(st.currentSystemData.bodies))
      ? st.currentSystemData.bodies
      : [];

    const jumpState = (st && st.jumpState) || 'idle';
    const targetSys = (st && st.targetJumpSystem) || '';

    const scanned = Number(detail.scanned_bodies ?? sys?.scanned_bodies ?? bodies.length ?? 0);
    const total = Number(detail.total_bodies ?? sys?.total_bodies ?? 0);

    let elw = 0;
    let ww = 0;
    let bioBodies = 0;
    let bioSignals = 0;
    let terraformable = 0;
    let highG = 0;

    bodies.forEach(b => {
      const pClass = String(b.planet_class || '').toLowerCase();
      if (pClass.includes('earthlike') || pClass.includes('earth-like')) elw++;
      if (pClass.includes('water world')) ww++;
      if (b.terraform_state && String(b.terraform_state).trim() && String(b.terraform_state) !== 'Not Terraformable') {
        terraformable++;
      }
      const bBio = Number(b.bio_signals || 0);
      if (bBio > 0) {
        bioBodies++;
        bioSignals += bBio;
      }
      const gVal = (b.surface_gravity_ms2 != null)
        ? (Number(b.surface_gravity_ms2) / 9.81)
        : Number(b.surface_gravity || 0);
      if (b.landable && gVal >= 3.0) {
        highG++;
      }
    });

    return {
      jumpState,
      targetSys,
      starSystem: detail.star_system || '',
      scanned,
      total,
      elw,
      ww,
      terraformable,
      bioBodies,
      bioSignals,
      highG,
    };
  }

  function appendHudBadge(parent, cls, text) {
    const span = document.createElement('span');
    span.className = `live-hud-pill ${cls}`;
    span.textContent = text;
    parent.appendChild(span);
  }

  function renderLiveCompactHudStrip() {
    const strip = document.getElementById('live-compact-hud-strip');
    if (!strip) return;

    const active = isLiveCompactActive();
    strip.style.display = active ? 'flex' : 'none';
    if (!active) return;

    const st = typeof window.state !== 'undefined' ? window.state : {};
    const summary = computeCompactHudSummary(st);

    strip.innerHTML = '';

    // Status pill
    let statusText = tr('live_hud_status_live', '📡 LIVE追従');
    let statusCls = 'hud-live';
    if (summary.jumpState === 'hyperspace') {
      statusText = tr('live_hud_status_jump', '🌀 ジャンプ中 -> {sys}', { sys: summary.targetSys || '...' });
      statusCls = 'hud-jump';
    } else if (summary.jumpState === 'arrived_waiting_fss') {
      statusText = tr('live_hud_status_fss_wait', '⏳ FSS待機');
      statusCls = 'hud-wait';
    } else if (summary.jumpState === 'scanned') {
      statusText = tr('live_hud_status_scanned', '✓ スキャン中');
      statusCls = 'hud-ok';
    }
    appendHudBadge(strip, statusCls, statusText);

    // Body progress pill
    const bodyLabel = summary.total > 0
      ? `🔭 ${summary.scanned}/${summary.total}`
      : `🔭 ${summary.scanned}`;
    appendHudBadge(strip, 'hud-bodies', bodyLabel);

    if (summary.elw > 0) appendHudBadge(strip, 'hud-elw', `🌍 ELW:${summary.elw}`);
    if (summary.ww > 0) appendHudBadge(strip, 'hud-ww', `💧 WW:${summary.ww}`);
    if (summary.terraformable > 0) appendHudBadge(strip, 'hud-tf', `🌱 TF:${summary.terraformable}`);
    if (summary.bioSignals > 0) appendHudBadge(strip, 'hud-bio', `🦠 Bio:${summary.bioSignals} (${summary.bioBodies})`);
    if (summary.highG > 0) appendHudBadge(strip, 'hud-highg', `⚠ High-G:${summary.highG}`);

    // Right quick-actions (expand left/right pane temporarily or exit compact HUD)
    const actions = document.createElement('div');
    actions.className = 'live-hud-actions';

    const btnLeft = document.createElement('button');
    btnLeft.type = 'button';
    btnLeft.className = 'view-btn';
    btnLeft.style.cssText = 'padding: 1px 7px; font-size: 0.68rem;';
    btnLeft.textContent = tr('live_hud_toggle_left', '◀ 星系');
    btnLeft.addEventListener('click', () => document.getElementById('btn-toggle-left-pane')?.click());
    actions.appendChild(btnLeft);

    const btnRight = document.createElement('button');
    btnRight.type = 'button';
    btnRight.className = 'view-btn';
    btnRight.style.cssText = 'padding: 1px 7px; font-size: 0.68rem;';
    btnRight.textContent = tr('live_hud_toggle_right', '天体詳細 ▶');
    btnRight.addEventListener('click', () => document.getElementById('btn-toggle-right-pane')?.click());
    actions.appendChild(btnRight);

    const btnExit = document.createElement('button');
    btnExit.type = 'button';
    btnExit.className = 'view-btn';
    btnExit.style.cssText = 'padding: 1px 7px; font-size: 0.68rem; color: #fed7aa; border-color: rgba(251, 146, 60, 0.5);';
    btnExit.textContent = tr('live_hud_exit_btn', '通常表示');
    btnExit.addEventListener('click', () => setLiveCompactMode(false));
    actions.appendChild(btnExit);

    strip.appendChild(actions);
  }

  function updateToggleButtonsUI() {
    const enabled = isCompactEnabled();
    const active = isLiveCompactActive();

    ['btn-live-compact', 'btn-live-compact-left'].forEach(id => {
      const btn = document.getElementById(id);
      if (!btn) return;
      btn.classList.toggle('active', active);
      btn.classList.toggle('armed', enabled && !active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    const cbMode = document.getElementById('cb-live-compact-mode');
    if (cbMode) cbMode.checked = enabled;

    const cbAuto = document.getElementById('cb-live-compact-auto-panes');
    if (cbAuto) cbAuto.checked = isAutoCollapsePanesEnabled();
  }

  function syncLiveCompactModeUI() {
    const active = isLiveCompactActive();
    if (typeof document !== 'undefined' && document.body) {
      document.body.classList.toggle('live-compact-active', active);
    }

    if (lastAppliedActive !== active) {
      if (active) {
        if (isAutoCollapsePanesEnabled() && typeof window.getSidePanesCollapsed === 'function' && typeof window.setSidePanesCollapsed === 'function') {
          if (!savedPreCompactPanes) {
            savedPreCompactPanes = window.getSidePanesCollapsed();
          }
          window.setSidePanesCollapsed(true, true);
        }
      } else if (lastAppliedActive === true) {
        if (savedPreCompactPanes && typeof window.setSidePanesCollapsed === 'function') {
          window.setSidePanesCollapsed(savedPreCompactPanes.left, savedPreCompactPanes.right);
        }
        savedPreCompactPanes = null;
      }
      lastAppliedActive = active;
    }

    updateToggleButtonsUI();
    renderLiveCompactHudStrip();
  }

  function setLiveCompactMode(nextEnabled, autoEnableLive = false) {
    const val = Boolean(nextEnabled);
    if (typeof window.state !== 'undefined') {
      window.state.liveCompactEnabled = val;
    }
    try { localStorage.setItem(LS_KEY_ENABLED, val ? 'true' : 'false'); } catch (e) {}

    if (autoEnableLive && val && !isLiveEnabled() && typeof window.toggleLiveSync === 'function') {
      window.toggleLiveSync();
      return;
    }
    syncLiveCompactModeUI();
  }

  async function handleToolbarCompactClick() {
    if (isLiveCompactActive()) {
      setLiveCompactMode(false, false);
    } else {
      setLiveCompactMode(true, true);
    }
  }

  function initLiveCompactMode() {
    const btnHeader = document.getElementById('btn-live-compact');
    const btnLeft = document.getElementById('btn-live-compact-left');
    const cbMode = document.getElementById('cb-live-compact-mode');
    const cbAuto = document.getElementById('cb-live-compact-auto-panes');

    btnHeader?.addEventListener('click', handleToolbarCompactClick);
    btnLeft?.addEventListener('click', handleToolbarCompactClick);

    cbMode?.addEventListener('change', () => {
      setLiveCompactMode(cbMode.checked, false);
    });

    cbAuto?.addEventListener('change', () => {
      const val = Boolean(cbAuto.checked);
      if (typeof window.state !== 'undefined') {
        window.state.liveCompactAutoCollapse = val;
      }
      try { localStorage.setItem(LS_KEY_AUTO_PANES, val ? 'true' : 'false'); } catch (e) {}
      if (isLiveCompactActive() && val && typeof window.setSidePanesCollapsed === 'function') {
        if (!savedPreCompactPanes && typeof window.getSidePanesCollapsed === 'function') {
          savedPreCompactPanes = window.getSidePanesCollapsed();
        }
        window.setSidePanesCollapsed(true, true);
      }
    });

    syncLiveCompactModeUI();
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', initLiveCompactMode);
  }

  if (typeof window !== 'undefined') {
    window.syncLiveCompactModeUI = syncLiveCompactModeUI;
    window.renderLiveCompactHudStrip = renderLiveCompactHudStrip;
    window.setLiveCompactMode = setLiveCompactMode;
    window.computeCompactHudSummary = computeCompactHudSummary;
  }
})();
