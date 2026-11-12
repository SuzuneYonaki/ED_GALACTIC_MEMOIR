// Interactive 42 Galactic Regions Map & Sector Exploration Progress Modal
(function () {
  const rmState = {
    overview: null,
    gridFlat: null, // Uint8Array(width * height)
    width: 256,
    height: 256,
    regionStatsById: {},
    selectedRegionId: null,
    hoveredRegionId: null,
    sectorsData: null,
    sectorsCache: {},
    sectorQuery: '',
    sectorSort: 'visited',
    showVisitedDots: true,
    showLandmarks: true,
    isLoadingMap: false,
    isLoadingSectors: false,
  };

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

  function esc(str) {
    if (typeof window.escapeHtml === 'function') return window.escapeHtml(str);
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function getLang() {
    if (typeof window.getAppLang === 'function') return window.getAppLang();
    return (typeof window.currentLang === 'string') ? window.currentLang : 'ja';
  }

  function regionDisplayNames(rid) {
    const stat = rmState.regionStatsById[rid];
    if (!stat) return { primary: `Region #${rid}`, secondary: '' };
    const isEn = getLang() === 'en';
    const primary = isEn ? stat.name_en : stat.name_ja;
    const secondary = isEn ? (stat.name_ja !== stat.name_en ? stat.name_ja : '') : stat.name_en;
    return { primary, secondary };
  }

  // Deterministic HSL -> RGB palette using golden-angle spacing across 42 regions
  function regionColorRgb(rid) {
    const hue = ((rid * 137.508) % 360) / 360;
    const sat = 0.55;
    const light = 0.44;
    const q = light < 0.5 ? light * (1 + sat) : light + sat - light * sat;
    const p = 2 * light - q;
    const hue2rgb = (t) => {
      let x = t;
      if (x < 0) x += 1;
      if (x > 1) x -= 1;
      if (x < 1 / 6) return p + (q - p) * 6 * x;
      if (x < 1 / 2) return q;
      if (x < 2 / 3) return p + (q - p) * (2 / 3 - x) * 6;
      return p;
    };
    return [
      Math.round(hue2rgb(hue + 1 / 3) * 255),
      Math.round(hue2rgb(hue) * 255),
      Math.round(hue2rgb(hue - 1 / 3) * 255),
    ];
  }

  function decodeRleGrid(gridObj) {
    const w = gridObj.width || 256;
    const h = gridObj.height || 256;
    const flat = new Uint8Array(w * h);
    const rows = gridObj.rle_rows || [];
    for (let gz = 0; gz < h && gz < rows.length; gz++) {
      let gx = 0;
      const rowOffset = gz * w;
      const runs = rows[gz];
      for (let i = 0; i < runs.length; i++) {
        const len = runs[i][0];
        const rid = runs[i][1];
        const end = Math.min(w, gx + len);
        for (; gx < end; gx++) {
          flat[rowOffset + gx] = rid;
        }
      }
    }
    rmState.width = w;
    rmState.height = h;
    rmState.gridFlat = flat;
  }

  function renderMapCanvas() {
    const canvas = document.getElementById('region-map-canvas');
    if (!canvas || !rmState.gridFlat) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = rmState.width;
    const h = rmState.height;
    const scale = 2;
    const targetW = w * scale;
    const targetH = h * scale;
    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }

    // Build low-res 256x256 ImageData then upscale crisply
    const offscreen = document.createElement('canvas');
    offscreen.width = w;
    offscreen.height = h;
    const offCtx = offscreen.getContext('2d');
    const img = offCtx.createImageData(w, h);
    const data = img.data;
    const flat = rmState.gridFlat;
    const selId = rmState.selectedRegionId;
    const hovId = rmState.hoveredRegionId;

    // Precompute color table [0..42]
    const colors = new Array(45);
    for (let rid = 1; rid <= 44; rid++) {
      const rgb = regionColorRgb(rid);
      const stat = rmState.regionStatsById[rid];
      const hasVisits = Boolean(stat && stat.visited_systems > 0);
      colors[rid] = { rgb, hasVisits };
    }

    for (let gz = 0; gz < h; gz++) {
      const cy = h - 1 - gz; // North (+Z) at top of canvas
      const srcRow = gz * w;
      const dstRow = cy * w * 4;
      for (let gx = 0; gx < w; gx++) {
        const rid = flat[srcRow + gx];
        const px = dstRow + gx * 4;
        if (!rid) {
          data[px] = 7;
          data[px + 1] = 11;
          data[px + 2] = 22;
          data[px + 3] = 255;
          continue;
        }
        const entry = colors[rid] || { rgb: [80, 120, 160], hasVisits: false };
        const [r, g, b] = entry.rgb;
        const isSel = rid === selId;
        const isHov = rid === hovId;
        const isBorder = (
          (gx > 0 && flat[srcRow + gx - 1] !== rid) ||
          (gx + 1 < w && flat[srcRow + gx + 1] !== rid) ||
          (gz > 0 && flat[(gz - 1) * w + gx] !== rid) ||
          (gz + 1 < h && flat[(gz + 1) * w + gx] !== rid)
        );

        if (isSel && isBorder) {
          data[px] = 0;
          data[px + 1] = 225;
          data[px + 2] = 255;
          data[px + 3] = 255;
        } else if (isSel) {
          data[px] = Math.min(255, Math.round(r * 0.85 + 35));
          data[px + 1] = Math.min(255, Math.round(g * 0.85 + 55));
          data[px + 2] = Math.min(255, Math.round(b * 0.85 + 75));
          data[px + 3] = 255;
        } else if (isHov) {
          data[px] = Math.min(255, Math.round(r * 0.78 + 45));
          data[px + 1] = Math.min(255, Math.round(g * 0.78 + 45));
          data[px + 2] = Math.min(255, Math.round(b * 0.78 + 45));
          data[px + 3] = 255;
        } else if (isBorder) {
          const dim = entry.hasVisits ? 0.55 : 0.30;
          data[px] = Math.round(r * dim);
          data[px + 1] = Math.round(g * dim);
          data[px + 2] = Math.round(b * dim);
          data[px + 3] = 255;
        } else {
          const factor = entry.hasVisits ? 0.48 : 0.20;
          data[px] = Math.round(r * factor + 8);
          data[px + 1] = Math.round(g * factor + 12);
          data[px + 2] = Math.round(b * factor + 22);
          data[px + 3] = 255;
        }
      }
    }

    offCtx.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(offscreen, 0, 0, targetW, targetH);

    // Visited system grid heatmap dots
    const ov = rmState.overview;
    if (rmState.showVisitedDots && ov && Array.isArray(ov.visited_cells)) {
      ov.visited_cells.forEach(([gx, gz, cnt]) => {
        const cx = gx * scale;
        const cy = (h - 1 - gz) * scale;
        ctx.fillStyle = cnt >= 5 ? '#facc15' : (cnt >= 2 ? '#38bdf8' : 'rgba(56, 189, 248, 0.85)');
        ctx.fillRect(cx, cy, Math.max(2, scale), Math.max(2, scale));
      });
    }

    // Landmarks + Current CMDR location
    if (rmState.showLandmarks && ov) {
      if (Array.isArray(ov.landmarks)) {
        ov.landmarks.forEach(lm => {
          const cx = lm.gx * scale + scale / 2;
          const cy = (h - 1 - lm.gz) * scale + scale / 2;
          ctx.beginPath();
          ctx.arc(cx, cy, 3.2, 0, Math.PI * 2);
          ctx.fillStyle = '#f97316';
          ctx.fill();
          ctx.strokeStyle = '#0f172a';
          ctx.lineWidth = 1;
          ctx.stroke();

          ctx.font = 'bold 10px sans-serif';
          ctx.fillStyle = '#fed7aa';
          ctx.fillText(lm.name || lm.system_name || '', cx + 5, cy + 3);
        });
      }

      if (ov.current_location && ov.current_location.gx != null && ov.current_location.gz != null) {
        const cx = ov.current_location.gx * scale + scale / 2;
        const cy = (h - 1 - ov.current_location.gz) * scale + scale / 2;
        ctx.beginPath();
        ctx.arc(cx, cy, 6, 0, Math.PI * 2);
        ctx.strokeStyle = '#00ff88';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = '#00ff88';
        ctx.fill();
      }
    }
  }

  function renderClickedRegionBanner() {
    const banner = document.getElementById('region-map-selected-banner');
    if (!banner) return;
    const rid = rmState.selectedRegionId;
    if (!rid) {
      banner.textContent = tr(
        'region_map_click_prompt',
        '地図上のリージョンをクリックすると、リージョン名と探索済みセクターが表示されます'
      );
      return;
    }
    const { primary, secondary } = regionDisplayNames(rid);
    const stat = rmState.regionStatsById[rid] || {};
    banner.innerHTML = `
      <span class="region-id-pill">#${Number(rid)}</span>
      <strong style="color: var(--ed-cyan); font-size: 0.92rem;">${esc(primary)}</strong>
      ${secondary ? `<span style="color: var(--text-secondary); font-size: 0.76rem;">(${esc(secondary)})</span>` : ''}
      <span style="margin-left: auto; font-size: 0.74rem; color: #cbd5e1;">
        ${esc(tr('region_map_banner_counts', '訪問: {sys} 星系 / セクター: {sec}', {
          sys: (stat.visited_systems || 0).toLocaleString(),
          sec: (stat.sector_count || 0).toLocaleString()
        }))}
      </span>
    `;
  }

  function populateRegionSelect() {
    const sel = document.getElementById('region-map-select');
    if (!sel || !rmState.overview) return;
    const list = rmState.overview.regions || [];
    sel.innerHTML = '';

    // Sort explored regions first when helpful, or keep official 1..42 order with visit indicator
    list.forEach(r => {
      const opt = document.createElement('option');
      opt.value = String(r.region_id);
      const { primary } = regionDisplayNames(r.region_id);
      const suffix = r.visited_systems > 0 ? ` (${r.visited_systems})` : '';
      opt.textContent = `#${r.region_id} ${primary}${suffix}`;
      sel.appendChild(opt);
    });
    if (rmState.selectedRegionId != null) {
      sel.value = String(rmState.selectedRegionId);
    }
  }

  function renderSectorsPanel() {
    const headerEl = document.getElementById('region-detail-summary');
    const listEl = document.getElementById('region-sectors-list');
    if (!listEl) return;

    const rid = rmState.selectedRegionId;
    if (!rid) {
      if (headerEl) headerEl.innerHTML = '';
      listEl.innerHTML = `<div class="region-empty-state">${esc(tr('region_map_click_prompt', '地図上のリージョンをクリックすると、リージョン名と探索済みセクターが表示されます'))}</div>`;
      return;
    }

    const data = rmState.sectorsData;
    if (rmState.isLoadingSectors || !data || !data.region || data.region.region_id !== rid) {
      listEl.innerHTML = `<div class="region-empty-state">${esc(tr('loading', '読み込み中...'))}</div>`;
      return;
    }

    const reg = data.region;
    const { primary, secondary } = regionDisplayNames(reg.region_id);
    if (headerEl) {
      headerEl.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
          <div style="min-width: 0;">
            <div style="font-size: 0.96rem; font-weight: bold; color: var(--ed-cyan);">
              🧭 #${Number(reg.region_id)} ${esc(primary)}
            </div>
            ${secondary ? `<div style="font-size: 0.72rem; color: var(--text-secondary);">${esc(secondary)}</div>` : ''}
          </div>
          <button type="button" id="btn-region-filter-left" class="btn-page" style="padding: 3px 9px; font-size: 0.72rem; color: #38bdf8; border-color: rgba(56, 189, 248, 0.45);">
            🔍 ${esc(tr('region_filter_in_left', '左リストをこのリージョンに絞込'))}
          </button>
        </div>
        <div class="region-detail-kpis">
          <span><strong>${(reg.visited_systems || 0).toLocaleString()}</strong> ${esc(tr('region_kpi_systems', '訪問星系'))}</span>
          <span><strong>${(reg.sector_count || 0).toLocaleString()}</strong> ${esc(tr('region_kpi_sectors', '探索セクター'))}</span>
          <span><strong>${(reg.scanned_bodies || 0).toLocaleString()}</strong> ${esc(tr('region_kpi_bodies', 'スキャン天体'))}</span>
        </div>
      `;
      document.getElementById('btn-region-filter-left')?.addEventListener('click', () => {
        applyRegionFilterToLeftPane(reg.region_id, null, false);
      });
    }

    const q = (rmState.sectorQuery || '').trim().toLowerCase();
    let sectors = Array.isArray(data.sectors) ? data.sectors.slice() : [];
    if (q) {
      sectors = sectors.filter(s => {
        const disp = s.is_named_catalog
          ? tr('region_named_catalog_sector', '固有名称・星表星系 (Sol 等)')
          : s.sector_name;
        return disp.toLowerCase().includes(q);
      });
    }

    sectors.sort((a, b) => {
      if (rmState.sectorSort === 'scanned') {
        return (b.scanned_bodies - a.scanned_bodies) || (b.visited_systems - a.visited_systems);
      }
      if (rmState.sectorSort === 'name') {
        const na = a.is_named_catalog ? 'zzz' : a.sector_name.toLowerCase();
        const nb = b.is_named_catalog ? 'zzz' : b.sector_name.toLowerCase();
        return na.localeCompare(nb);
      }
      if (rmState.sectorSort === 'recent') {
        return String(b.last_visited || '').localeCompare(String(a.last_visited || ''));
      }
      return (b.visited_systems - a.visited_systems) || (b.scanned_bodies - a.scanned_bodies);
    });

    if (sectors.length === 0) {
      listEl.innerHTML = `<div class="region-empty-state">${esc(tr('region_no_visited_sectors', 'このリージョンで訪問済みの星系・セクターはまだありません。'))}</div>`;
      return;
    }

    const maxVisitedInRegion = Math.max(1, ...sectors.map(s => s.visited_systems || 0));
    listEl.innerHTML = '';

    sectors.forEach(sec => {
      const card = document.createElement('div');
      card.className = 'region-sector-card';

      const displayName = sec.is_named_catalog
        ? tr('region_named_catalog_sector', '固有名称・星表星系 (Sol 等)')
        : sec.sector_name;
      const pct = sec.visited_systems > 0
        ? Math.max(6, Math.round((sec.visited_systems / maxVisitedInRegion) * 100))
        : 0;
      const lastDate = sec.last_visited ? sec.last_visited.replace('T', ' ').slice(0, 10) : '--';

      const topRow = document.createElement('div');
      topRow.className = 'region-sector-top';

      const titleEl = document.createElement('span');
      titleEl.className = 'region-sector-name';
      titleEl.textContent = sec.is_named_catalog ? `★ ${displayName}` : displayName;
      topRow.appendChild(titleEl);

      const actionWrap = document.createElement('div');
      actionWrap.style.cssText = 'display: flex; align-items: center; gap: 6px; flex-shrink: 0;';

      const countBadge = document.createElement('span');
      countBadge.className = 'region-sector-count';
      countBadge.textContent = tr('region_sector_sys_cnt', '{count} 星系', {
        count: (sec.visited_systems || 0).toLocaleString()
      });
      actionWrap.appendChild(countBadge);

      const filterBtn = document.createElement('button');
      filterBtn.type = 'button';
      filterBtn.className = 'btn-page';
      filterBtn.style.cssText = 'padding: 1px 6px; font-size: 0.67rem; color: #38bdf8;';
      filterBtn.textContent = '🔍';
      filterBtn.title = tr('region_sector_filter_tip', 'このセクターの星系を左リストに表示');
      filterBtn.addEventListener('click', () => {
        applyRegionFilterToLeftPane(reg.region_id, sec.is_named_catalog ? null : sec.sector_name, Boolean(sec.is_named_catalog));
      });
      actionWrap.appendChild(filterBtn);

      topRow.appendChild(actionWrap);
      card.appendChild(topRow);

      // Relative progress bar
      const barTrack = document.createElement('div');
      barTrack.className = 'region-sector-bar-track';
      const barFill = document.createElement('div');
      barFill.className = 'region-sector-bar-fill';
      barFill.style.width = `${pct}%`;
      barTrack.appendChild(barFill);
      card.appendChild(barTrack);

      const metaRow = document.createElement('div');
      metaRow.className = 'region-sector-meta';
      const statsText = tr(
        'region_sector_meta_fmt',
        '訪問 {visits}回 · スキャン {scanned}/{total}天体 · FSS完 {fss}/{sys} · 最終 {date}',
        {
          visits: (sec.total_visits || 0).toLocaleString(),
          scanned: (sec.scanned_bodies || 0).toLocaleString(),
          total: (sec.total_bodies || 0).toLocaleString(),
          fss: (sec.fss_complete_systems || 0).toLocaleString(),
          sys: (sec.visited_systems || 0).toLocaleString(),
          date: lastDate
        }
      );
      metaRow.textContent = statsText;
      card.appendChild(metaRow);

      if (Array.isArray(sec.sample_systems) && sec.sample_systems.length > 0) {
        const samplesRow = document.createElement('div');
        samplesRow.className = 'region-sector-samples';
        sec.sample_systems.forEach(s => {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'region-sample-sys-btn';
          btn.textContent = s.star_system;
          btn.title = `${s.star_system} (${s.scanned_bodies}/${s.total_bodies || '?'})`;
          btn.addEventListener('click', async () => {
            closeRegionMapModal();
            if (typeof window.selectSystem === 'function') {
              await window.selectSystem(s.system_address, false, true);
            }
          });
          samplesRow.appendChild(btn);
        });
        card.appendChild(samplesRow);
      }

      listEl.appendChild(card);
    });
  }

  async function selectRegion(rid) {
    if (!rid) return;
    rmState.selectedRegionId = Number(rid);
    const sel = document.getElementById('region-map-select');
    if (sel) sel.value = String(rmState.selectedRegionId);

    renderClickedRegionBanner();
    renderMapCanvas();

    if (rmState.sectorsCache[rmState.selectedRegionId]) {
      rmState.sectorsData = rmState.sectorsCache[rmState.selectedRegionId];
      renderSectorsPanel();
      return;
    }

    rmState.isLoadingSectors = true;
    renderSectorsPanel();
    try {
      const res = await fetch(`/api/regions/${rmState.selectedRegionId}/sectors`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      rmState.sectorsCache[rmState.selectedRegionId] = data;
      if (rmState.selectedRegionId === data.region?.region_id) {
        rmState.sectorsData = data;
      }
    } catch (err) {
      console.error('[RegionMap] Failed to load region sectors:', err);
    } finally {
      rmState.isLoadingSectors = false;
      renderSectorsPanel();
    }
  }

  function applyRegionFilterToLeftPane(regionId, sectorName, sectorNamedOnly) {
    if (typeof window.state !== 'undefined') {
      const names = regionDisplayNames(regionId);
      window.state.regionFilter = {
        region_id: regionId,
        region_name_primary: names.primary,
        sector: sectorName || null,
        sector_named_only: Boolean(sectorNamedOnly),
      };
      window.state.page = 1;
    }
    closeRegionMapModal();
    if (typeof window.renderActiveRegionFilterBanner === 'function') {
      window.renderActiveRegionFilterBanner();
    }
    if (typeof window.fetchSystems === 'function') {
      window.fetchSystems({ autoSelectTop: true });
    }
  }

  async function openRegionMapModal(initialRegionId = null) {
    const modal = document.getElementById('modal-region-map');
    if (!modal) return;
    modal.style.display = 'flex';

    // Always fetch fresh overview on modal open so newly visited systems show up immediately
    rmState.sectorsCache = {};
    rmState.isLoadingMap = true;
    const summaryBar = document.getElementById('region-map-global-summary');
    if (summaryBar) summaryBar.textContent = tr('loading', '読み込み中...');

    try {
      const res = await fetch('/api/regions/map');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const ov = await res.json();
      rmState.overview = ov;
      rmState.regionStatsById = {};
      (ov.regions || []).forEach(r => {
        rmState.regionStatsById[r.region_id] = r;
      });
      if (ov.grid) decodeRleGrid(ov.grid);

      if (summaryBar && ov.summary) {
        summaryBar.textContent = tr(
          'region_map_global_summary_fmt',
          '探索リージョン: {explored} / {total} · 訪問星系: {sys} · 探索セクター: {sec}',
          {
            explored: ov.summary.explored_regions,
            total: ov.summary.total_regions,
            sys: (ov.summary.total_visited_systems || 0).toLocaleString(),
            sec: (ov.summary.total_sectors || 0).toLocaleString(),
          }
        );
      }
      populateRegionSelect();

      let targetRid = initialRegionId;
      if (!targetRid && window.state && window.state.selectedSystem && window.state.selectedSystem.galactic_region_id) {
        targetRid = window.state.selectedSystem.galactic_region_id;
      }
      if (!targetRid && ov.current_location && ov.current_location.region_id) {
        targetRid = ov.current_location.region_id;
      }
      if (!targetRid) {
        const firstExplored = (ov.regions || []).find(r => r.visited_systems > 0);
        targetRid = firstExplored ? firstExplored.region_id : 18;
      }

      renderMapCanvas();
      await selectRegion(targetRid);
    } catch (err) {
      console.error('[RegionMap] Failed to load regions overview:', err);
      if (summaryBar) summaryBar.textContent = '⚠ Error';
    } finally {
      rmState.isLoadingMap = false;
    }
  }

  function closeRegionMapModal() {
    const modal = document.getElementById('modal-region-map');
    if (modal) modal.style.display = 'none';
  }

  function canvasCellAtEvent(canvas, e) {
    if (!rmState.gridFlat) return { gx: -1, gz: -1, rid: 0 };
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return { gx: -1, gz: -1, rid: 0 };
    const normX = (e.clientX - rect.left) / rect.width;
    const normY = (e.clientY - rect.top) / rect.height;
    const w = rmState.width;
    const h = rmState.height;
    const gx = Math.min(w - 1, Math.max(0, Math.floor(normX * w)));
    const gz = Math.min(h - 1, Math.max(0, h - 1 - Math.floor(normY * h)));
    const rid = rmState.gridFlat[gz * w + gx] || 0;
    return { gx, gz, rid, rect };
  }

  function initRegionMapModal() {
    const modal = document.getElementById('modal-region-map');
    const btnOpen = document.getElementById('btn-open-region-map');
    const btnClose = document.getElementById('btn-close-region-map');
    const btnDismiss = document.getElementById('btn-dismiss-region-map');
    const canvas = document.getElementById('region-map-canvas');
    const tooltip = document.getElementById('region-map-hover-tooltip');
    const sel = document.getElementById('region-map-select');
    const searchInput = document.getElementById('region-sector-search');
    const sortSel = document.getElementById('region-sector-sort');
    const cbDots = document.getElementById('cb-region-map-dots');
    const cbLandmarks = document.getElementById('cb-region-map-landmarks');

    btnOpen?.addEventListener('click', () => openRegionMapModal(null));
    btnClose?.addEventListener('click', closeRegionMapModal);
    btnDismiss?.addEventListener('click', closeRegionMapModal);

    modal?.addEventListener('click', (e) => {
      if (e.target === modal) closeRegionMapModal();
    });

    sel?.addEventListener('change', () => {
      const rid = Number(sel.value);
      if (rid) selectRegion(rid);
    });

    searchInput?.addEventListener('input', () => {
      rmState.sectorQuery = searchInput.value;
      renderSectorsPanel();
    });

    sortSel?.addEventListener('change', () => {
      rmState.sectorSort = sortSel.value;
      renderSectorsPanel();
    });

    cbDots?.addEventListener('change', () => {
      rmState.showVisitedDots = cbDots.checked;
      renderMapCanvas();
    });

    cbLandmarks?.addEventListener('change', () => {
      rmState.showLandmarks = cbLandmarks.checked;
      renderMapCanvas();
    });

    if (canvas) {
      canvas.addEventListener('mousemove', (e) => {
        const { rid, rect } = canvasCellAtEvent(canvas, e);
        if (rid !== rmState.hoveredRegionId) {
          rmState.hoveredRegionId = rid || null;
          renderMapCanvas();
        }
        if (tooltip) {
          if (rid > 0) {
            const { primary, secondary } = regionDisplayNames(rid);
            const stat = rmState.regionStatsById[rid] || {};
            tooltip.style.display = 'block';
            tooltip.style.left = `${Math.min(rect.width - 140, Math.max(8, e.clientX - rect.left + 12))}px`;
            tooltip.style.top = `${Math.min(rect.height - 48, Math.max(8, e.clientY - rect.top + 12))}px`;
            tooltip.textContent = `#${rid} ${primary}${secondary ? ' / ' + secondary : ''} (${stat.visited_systems || 0})`;
          } else {
            tooltip.style.display = 'none';
          }
        }
      });

      canvas.addEventListener('mouseleave', () => {
        if (rmState.hoveredRegionId !== null) {
          rmState.hoveredRegionId = null;
          renderMapCanvas();
        }
        if (tooltip) tooltip.style.display = 'none';
      });

      canvas.addEventListener('click', (e) => {
        const { rid } = canvasCellAtEvent(canvas, e);
        if (rid > 0) {
          selectRegion(rid);
        }
      });
    }
  }

  document.addEventListener('DOMContentLoaded', initRegionMapModal);

  window.openRegionMapModal = openRegionMapModal;
  window.closeRegionMapModal = closeRegionMapModal;
  window.refreshRegionMapLabels = () => {
    const modal = document.getElementById('modal-region-map');
    if (modal && modal.style.display !== 'none' && rmState.overview) {
      populateRegionSelect();
      renderClickedRegionBanner();
      renderSectorsPanel();
    }
  };
})();
