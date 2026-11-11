// Global Full-Text Search Modal & Cross-Database Jump Controller
(function () {
  const CATEGORY_ORDER = [
    'all', 'bookmark', 'system', 'body', 'bio', 'mining', 'codex', 'station', 'physics'
  ];

  const searchState = {
    query: '',
    category: 'all',
    offset: 0,
    limit: 50,
    total: 0,
    categoryCounts: {},
    items: [],
    isLoading: false,
    debounceTimer: null
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

  /**
   * Safely builds DOM nodes from backend highlighted HTML, only allowing <mark class="search-hl">...</mark>.
   * All other text is inserted strictly via document.createTextNode (zero innerHTML XSS risk).
   */
  function appendSafeHighlightedNodes(parent, highlightedHtml, plainFallback) {
    const src = typeof highlightedHtml === 'string' ? highlightedHtml : (plainFallback || '');
    const markTokenRe = /<mark class="search-hl">([\s\S]*?)<\/mark>/g;
    const decodeBasicEntities = (s) =>
      String(s || '')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#x27;|&#39;/g, "'")
        .replace(/&amp;/g, '&');

    let lastIdx = 0;
    let match;
    while ((match = markTokenRe.exec(src)) !== null) {
      if (match.index > lastIdx) {
        const rawText = src.slice(lastIdx, match.index);
        parent.appendChild(document.createTextNode(decodeBasicEntities(rawText)));
      }
      const markEl = document.createElement('mark');
      markEl.className = 'search-hl';
      markEl.textContent = decodeBasicEntities(match[1]);
      parent.appendChild(markEl);
      lastIdx = markTokenRe.lastIndex;
    }
    if (lastIdx < src.length) {
      parent.appendChild(document.createTextNode(decodeBasicEntities(src.slice(lastIdx))));
    }
  }

  function getCategoryLabel(cat) {
    const map = {
      all: ['global_search_cat_all', 'すべて'],
      bookmark: ['global_search_cat_bookmark', '📌 メモ・別名'],
      system: ['global_search_cat_system', '🌌 星系'],
      body: ['global_search_cat_body', '🪐 天体'],
      bio: ['global_search_cat_bio', '🌱 生体'],
      mining: ['global_search_cat_mining', '⛏️ 採掘'],
      codex: ['global_search_cat_codex', '📖 Codex'],
      station: ['global_search_cat_station', '🛰️ 施設'],
      physics: ['global_search_cat_physics', '🔭 物理']
    };
    const pair = map[cat] || [null, cat];
    return pair[0] ? tr(pair[0], pair[1]) : pair[1];
  }

  function renderCategoryTabs() {
    const container = document.getElementById('global-search-categories');
    if (!container) return;
    container.innerHTML = '';

    const totalAll = Object.values(searchState.categoryCounts).reduce((a, b) => a + b, 0);

    CATEGORY_ORDER.forEach(cat => {
      const count = cat === 'all' ? totalAll : (searchState.categoryCounts[cat] || 0);
      if (cat !== 'all' && searchState.query.trim() && count === 0 && searchState.category !== cat) {
        return;
      }
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `global-search-cat-btn${searchState.category === cat ? ' active' : ''}`;

      const labelSpan = document.createElement('span');
      labelSpan.textContent = getCategoryLabel(cat);
      btn.appendChild(labelSpan);

      if (searchState.query.trim()) {
        const cntSpan = document.createElement('span');
        cntSpan.className = 'global-search-cat-count';
        cntSpan.textContent = String(count);
        btn.appendChild(cntSpan);
      }

      btn.addEventListener('click', () => {
        searchState.category = cat;
        searchState.offset = 0;
        executeGlobalSearch(false);
      });
      container.appendChild(btn);
    });
  }

  function renderSearchResults() {
    const resultsEl = document.getElementById('global-search-results');
    const summaryEl = document.getElementById('global-search-summary');
    const moreBtn = document.getElementById('btn-global-search-more');
    if (!resultsEl) return;

    resultsEl.innerHTML = '';

    if (!searchState.query.trim()) {
      if (summaryEl) summaryEl.textContent = '';
      if (moreBtn) moreBtn.style.display = 'none';
      const promptDiv = document.createElement('div');
      promptDiv.style.cssText = 'text-align: center; color: var(--text-secondary); padding: 36px 16px; font-size: 0.85rem;';
      promptDiv.textContent = tr(
        'global_search_empty_prompt',
        'キーワードを入力すると、全探査データ（星系・天体・メモ・生体・採掘・施設・物理レポート）を横断検索して抜粋表示します。'
      );
      resultsEl.appendChild(promptDiv);
      renderCategoryTabs();
      return;
    }

    if (summaryEl) {
      summaryEl.textContent = tr('global_search_count_fmt', '{total} 件ヒット', {
        total: searchState.total.toLocaleString()
      });
    }

    if (searchState.items.length === 0) {
      if (moreBtn) moreBtn.style.display = 'none';
      const emptyDiv = document.createElement('div');
      emptyDiv.style.cssText = 'text-align: center; color: var(--text-secondary); padding: 36px 16px; font-size: 0.85rem;';
      emptyDiv.textContent = tr('global_search_no_results', '該当するデータが見つかりませんでした。');
      resultsEl.appendChild(emptyDiv);
      renderCategoryTabs();
      return;
    }

    searchState.items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'global-search-item';

      const header = document.createElement('div');
      header.className = 'global-search-item-header';

      const titleEl = document.createElement('div');
      titleEl.className = 'global-search-item-title';
      appendSafeHighlightedNodes(titleEl, item.highlighted_title, item.title);
      header.appendChild(titleEl);

      const badgeEl = document.createElement('span');
      badgeEl.className = `global-search-cat-badge cat-badge-${item.category}`;
      badgeEl.textContent = getCategoryLabel(item.category);
      header.appendChild(badgeEl);

      card.appendChild(header);

      const pathEl = document.createElement('div');
      pathEl.className = 'global-search-item-path';
      pathEl.textContent = item.body_name && item.body_name !== item.star_system
        ? `🌌 ${item.star_system}  ▸  🪐 ${item.body_name}`
        : `🌌 ${item.star_system}`;
      card.appendChild(pathEl);

      if (item.highlighted_snippet) {
        const snipEl = document.createElement('div');
        snipEl.className = 'global-search-item-snippet';
        appendSafeHighlightedNodes(snipEl, item.highlighted_snippet, '');
        card.appendChild(snipEl);
      }

      card.addEventListener('click', () => jumpToSearchResult(item));
      resultsEl.appendChild(card);
    });

    if (moreBtn) {
      const remaining = Math.max(0, searchState.total - searchState.items.length);
      if (remaining > 0) {
        moreBtn.style.display = 'inline-block';
        moreBtn.textContent = tr('global_search_load_more', 'さらに表示 (残り {remaining} 件)', {
          remaining: remaining.toLocaleString()
        });
      } else {
        moreBtn.style.display = 'none';
      }
    }

    renderCategoryTabs();
  }

  async function jumpToSearchResult(item) {
    closeGlobalSearchModal();
    if (!item || !item.system_address) return;

    if (typeof window.selectSystem === 'function') {
      await window.selectSystem(item.system_address, false, true);
    }

    // Focus target body in Inspector if applicable
    if (window.state && window.state.currentSystemData && Array.isArray(window.state.currentSystemData.bodies)) {
      const bodies = window.state.currentSystemData.bodies;
      let targetBody = null;
      if (item.body_id !== null && item.body_id !== undefined) {
        targetBody = bodies.find(b => Number(b.body_id) === Number(item.body_id));
      }
      if (!targetBody && item.body_name) {
        targetBody = bodies.find(b => b.body_name === item.body_name);
      }
      if (targetBody) {
        window.state.selectedBody = targetBody;
        if (typeof window.renderBodyInspector === 'function') {
          window.renderBodyInspector();
        }
        const rightPane = document.getElementById('right-pane');
        if (rightPane && rightPane.classList.contains('collapsed')) {
          document.getElementById('btn-toggle-right-pane')?.click();
        }
      }
    }

    if (typeof window.switchCenterPaneView === 'function') {
      const curView = window.state ? window.state.currentView : 'sysmap';
      if (item.category === 'physics') {
        window.switchCenterPaneView('physics');
      } else if (item.category === 'bio') {
        const modSettings = (typeof window.getModuleSettings === 'function') ? window.getModuleSettings() : {};
        window.switchCenterPaneView(modSettings.exobiology !== false ? 'bio' : 'sysmap');
      } else if (curView !== 'sysmap' && curView !== 'flat' && curView !== 'orrery') {
        window.switchCenterPaneView('sysmap');
      } else if (typeof window.renderCurrentView === 'function') {
        window.renderCurrentView();
      }
    }
  }

  async function executeGlobalSearch(append = false) {
    const q = (searchState.query || '').trim();
    if (!q) {
      searchState.items = [];
      searchState.total = 0;
      searchState.categoryCounts = {};
      renderSearchResults();
      return;
    }

    if (searchState.isLoading) return;
    searchState.isLoading = true;

    try {
      const params = new URLSearchParams();
      params.set('q', q);
      if (searchState.category && searchState.category !== 'all') {
        params.set('category', searchState.category);
      }
      params.set('limit', String(searchState.limit));
      params.set('offset', String(searchState.offset));

      const res = await fetch(`/api/search?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      searchState.total = data.total || 0;
      searchState.categoryCounts = data.category_counts || {};
      const newItems = Array.isArray(data.results) ? data.results : [];
      searchState.items = append ? searchState.items.concat(newItems) : newItems;

      renderSearchResults();
    } catch (err) {
      console.error('[GlobalSearch] Query failed:', err);
    } finally {
      searchState.isLoading = false;
    }
  }

  function openGlobalSearchModal() {
    const modal = document.getElementById('modal-global-search');
    const inputEl = document.getElementById('global-search-input');
    const clearBtn = document.getElementById('btn-global-search-clear');
    if (!modal) return;

    modal.style.display = 'flex';
    const leftSearchInput = document.getElementById('system-search');
    if (inputEl) {
      if (!inputEl.value.trim() && leftSearchInput && leftSearchInput.value.trim()) {
        inputEl.value = leftSearchInput.value.trim();
        searchState.query = inputEl.value;
        searchState.offset = 0;
        if (clearBtn) clearBtn.style.display = 'block';
        executeGlobalSearch(false);
      } else {
        renderSearchResults();
      }
      setTimeout(() => {
        inputEl.focus();
        inputEl.select();
      }, 30);
    }
  }

  function closeGlobalSearchModal() {
    const modal = document.getElementById('modal-global-search');
    if (modal) modal.style.display = 'none';
  }

  function initGlobalSearchModal() {
    const btnOpen = document.getElementById('btn-open-fulltext-search');
    const btnClose = document.getElementById('btn-close-global-search');
    const btnDismiss = document.getElementById('btn-dismiss-global-search');
    const modal = document.getElementById('modal-global-search');
    const inputEl = document.getElementById('global-search-input');
    const clearBtn = document.getElementById('btn-global-search-clear');
    const moreBtn = document.getElementById('btn-global-search-more');
    const rebuildBtn = document.getElementById('btn-global-search-rebuild');
    const rebuildStatus = document.getElementById('global-search-rebuild-status');

    btnOpen?.addEventListener('click', openGlobalSearchModal);
    btnClose?.addEventListener('click', closeGlobalSearchModal);
    btnDismiss?.addEventListener('click', closeGlobalSearchModal);

    modal?.addEventListener('click', (e) => {
      if (e.target === modal) closeGlobalSearchModal();
    });

    inputEl?.addEventListener('input', () => {
      searchState.query = inputEl.value;
      searchState.offset = 0;
      if (clearBtn) {
        clearBtn.style.display = inputEl.value.length > 0 ? 'block' : 'none';
      }
      clearTimeout(searchState.debounceTimer);
      searchState.debounceTimer = setTimeout(() => {
        executeGlobalSearch(false);
      }, 200);
    });

    inputEl?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        clearTimeout(searchState.debounceTimer);
        searchState.query = inputEl.value;
        searchState.offset = 0;
        executeGlobalSearch(false);
      }
    });

    clearBtn?.addEventListener('click', () => {
      if (!inputEl) return;
      inputEl.value = '';
      searchState.query = '';
      searchState.offset = 0;
      clearBtn.style.display = 'none';
      executeGlobalSearch(false);
      inputEl.focus();
    });

    moreBtn?.addEventListener('click', () => {
      searchState.offset = searchState.items.length;
      executeGlobalSearch(true);
    });

    rebuildBtn?.addEventListener('click', async () => {
      rebuildBtn.disabled = true;
      if (rebuildStatus) rebuildStatus.textContent = tr('global_search_rebuilding', '再構築中...');
      try {
        const res = await fetch('/api/search/rebuild', { method: 'POST' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (rebuildStatus) {
          rebuildStatus.textContent = tr('global_search_rebuilt_toast', '✅ 索引を再構築しました ({count} 件)', {
            count: (data.indexed_count || 0).toLocaleString()
          });
        }
        if (searchState.query.trim()) {
          searchState.offset = 0;
          executeGlobalSearch(false);
        }
      } catch (err) {
        console.error('[GlobalSearch] Rebuild failed:', err);
        if (rebuildStatus) rebuildStatus.textContent = '⚠ Error';
      } finally {
        rebuildBtn.disabled = false;
      }
    });

    renderCategoryTabs();
  }

  document.addEventListener('DOMContentLoaded', initGlobalSearchModal);

  window.openGlobalSearchModal = openGlobalSearchModal;
  window.closeGlobalSearchModal = closeGlobalSearchModal;
  window.refreshGlobalSearchLabels = renderSearchResults;
})();
