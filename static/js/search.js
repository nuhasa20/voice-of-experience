/**
 * static/js/search.js - Stage 4 Character N-Gram Search & Knowledge Library Controller
 */

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Normalizes text for client-side search/suggestions.
 * Matches the backend normalizer (tashkeel, tatweel, alef variants, teh marbuta, yaa).
 */
function normalizeSearchText(text) {
  if (!text) return '';
  return String(text)
    .toLowerCase()
    .replace(/[\u064B-\u0652\u0670]/g, '') // tashkeel
    .replace(/\u0640/g, '')               // tatweel
    .replace(/[إأآا]/g, 'ا')              // alef variants
    .replace(/ة/g, 'ه')                   // teh marbuta
    .replace(/[يى]/g, 'ي')                // yaa / alef maqsura
    .trim();
}

export class SearchController {
  /**
   * Asserts a required DOM element exists. Throws loudly if missing so the
   * failure is never silently swallowed.
   */
  static _require(id) {
    const el = document.getElementById(id);
    if (!el) {
      console.error(`SearchController: required element #${id} not found in DOM`);
      throw new Error(`SearchController: missing required element #${id}`);
    }
    return el;
  }

  constructor() {
    // ── Required elements (loud failure if missing) ──────────────────────────
    this.searchInput            = SearchController._require('searchInput');
    this.searchSubmitBtn        = SearchController._require('searchSubmitBtn');
    this.searchResultsMeta      = SearchController._require('searchResultsMeta');
    this.resultsCountText       = SearchController._require('resultsCountText');
    this.searchLoading          = SearchController._require('searchLoading');
    this.searchFallbackState    = SearchController._require('searchFallbackState');
    this.searchResultsContainer = SearchController._require('searchResultsContainer');
    this.searchPillWrapper      = SearchController._require('searchPillWrapper');
    this.searchSuggestionsList  = SearchController._require('searchSuggestionsList');

    // ── Optional elements (null-safe, no throw) ──────────────────────────────
    this.searchClearBtn         = document.getElementById('searchClearBtn');
    this.browseAllBtn           = document.getElementById('browseAllBtn');
    this.fallbackBrowseAllBtn   = document.getElementById('fallbackBrowseAllBtn');
    this.fallbackRecordBtn      = document.getElementById('fallbackRecordBtn');

    this.cachedCards             = [];
    this.isSearching             = false;
    this.debounceTimer           = null;
    this.activeSuggestionIndex   = -1;
    this.currentSuggestions      = [];

    this.tryQueries = [
      { label: 'Data leakage', query: 'data leakage in model' },
      { label: 'داتا ليكج في التست', query: 'داتا ليكج في التست' },
      { label: 'Sensor drift', query: 'sensor drift in telemetry' },
      { label: 'انحراف الحساسات', query: 'انحراف الحساسات' },
      { label: 'Missing NaN values', query: 'missing NaN values' },
      { label: 'قيم ناقصة', query: 'قيم ناقصة' },
    ];

    this.bindEvents();
    // Fire-and-forget: attach .catch() so unhandled rejections surface in DevTools
    this.loadAllCards().catch(err =>
      console.error('SearchController: loadAllCards() failed:', err)
    );
  }

  bindEvents() {
    // Search button click
    if (this.searchSubmitBtn) {
      this.searchSubmitBtn.addEventListener('click', () => {
        this.closeSuggestions();
        this.performSearch(this.searchInput.value).catch(err =>
          console.error('SearchController: performSearch() failed:', err)
        );
      });
    }

    // Input events (keyboard, input, focus)
    if (this.searchInput) {
      this.searchInput.addEventListener('keydown', (e) => {
        const isOpen = this.searchSuggestionsList && this.searchSuggestionsList.style.display !== 'none';

        if (e.key === 'ArrowDown') {
          if (!isOpen) {
            const val = this.searchInput.value.trim();
            if (!val) this.showTrySuggestions();
            else this.computeSuggestions(val);
            return;
          }
          if (this.currentSuggestions.length > 0) {
            e.preventDefault();
            this.activeSuggestionIndex = (this.activeSuggestionIndex + 1) % this.currentSuggestions.length;
            this.updateActiveDescendant();
          }
        } else if (e.key === 'ArrowUp') {
          if (isOpen && this.currentSuggestions.length > 0) {
            e.preventDefault();
            this.activeSuggestionIndex = (this.activeSuggestionIndex - 1 + this.currentSuggestions.length) % this.currentSuggestions.length;
            this.updateActiveDescendant();
          }
        } else if (e.key === 'Enter') {
          e.preventDefault();
          if (isOpen && this.activeSuggestionIndex >= 0 && this.currentSuggestions[this.activeSuggestionIndex]) {
            this.chooseSuggestion(this.activeSuggestionIndex);
          } else {
            this.closeSuggestions();
            this.performSearch(this.searchInput.value).catch(err =>
              console.error('SearchController: performSearch() failed:', err)
            );
          }
        } else if (e.key === 'Escape') {
          this.closeSuggestions();
        }
      });

      this.searchInput.addEventListener('input', () => {
        const val = this.searchInput.value.trim();
        if (this.searchClearBtn) {
          this.searchClearBtn.style.display = val ? 'inline-flex' : 'none';
        }

        clearTimeout(this.debounceTimer);
        if (!val) {
          this.showTrySuggestions();
          return;
        }

        this.debounceTimer = setTimeout(() => {
          this.computeSuggestions(val);
        }, 150);
      });

      this.searchInput.addEventListener('focus', () => {
        const val = this.searchInput.value.trim();
        if (!val) {
          this.showTrySuggestions();
        } else {
          this.computeSuggestions(val);
        }
      });
    }

    // Close suggestions on outside click
    document.addEventListener('click', (e) => {
      if (!this.searchPillWrapper) return;
      if (!this.searchPillWrapper.contains(e.target)) {
        this.closeSuggestions();
      }
    });

    // Clear button
    if (this.searchClearBtn) {
      this.searchClearBtn.addEventListener('click', () => {
        this.searchInput.value = '';
        this.searchClearBtn.style.display = 'none';
        this.showTrySuggestions();
        this.loadAllCards().catch(err =>
          console.error('SearchController: loadAllCards() failed:', err)
        );
        this.searchInput.focus();
      });
    }

    // View all cards button in meta bar
    if (this.browseAllBtn) {
      this.browseAllBtn.addEventListener('click', () => {
        this.searchInput.value = '';
        if (this.searchClearBtn) this.searchClearBtn.style.display = 'none';
        this.closeSuggestions();
        this.loadAllCards().catch(err =>
          console.error('SearchController: loadAllCards() failed:', err)
        );
      });
    }

    // Fallback panel "Browse all cards" button
    if (this.fallbackBrowseAllBtn) {
      this.fallbackBrowseAllBtn.addEventListener('click', () => {
        this.searchInput.value = '';
        if (this.searchClearBtn) this.searchClearBtn.style.display = 'none';
        this.closeSuggestions();
        this.loadAllCards().catch(err =>
          console.error('SearchController: loadAllCards() failed:', err)
        );
      });
    }

    // Scroll to contribution flow buttons
    const scrollToContribute = () => {
      this.closeSuggestions();
      const target = document.getElementById('contributionFlowCard') || document.getElementById('sectionSetup');
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        const nameInput = document.getElementById('expertName');
        if (nameInput) {
          setTimeout(() => nameInput.focus(), 600);
        }
      }
    };

    if (this.fallbackRecordBtn) {
      this.fallbackRecordBtn.addEventListener('click', scrollToContribute);
    }
  }

  showTrySuggestions() {
    if (!this.searchSuggestionsList) return;

    this.currentSuggestions = this.tryQueries.map((item, idx) => ({
      type: 'try',
      query: item.query,
      label: item.label,
      id: `suggestion-item-${idx}`,
    }));
    this.activeSuggestionIndex = -1;

    this.searchSuggestionsList.innerHTML = `
      <div class="suggestions-header">Try example queries:</div>
      <div class="suggestion-chips-grid">
        ${this.tryQueries.map((item, idx) => `
          <button
            type="button"
            class="suggestion-chip-btn search-chip"
            data-idx="${idx}"
            data-query="${escapeHtml(item.query)}"
            role="option"
            id="suggestion-item-${idx}"
            aria-selected="false"
            dir="auto"
          >
            ${escapeHtml(item.label)}
          </button>
        `).join('')}
      </div>
    `;

    this.bindSuggestionClicks();
    this.openSuggestions();
  }

  computeSuggestions(query) {
    if (!this.searchSuggestionsList) return;

    const clean = (query || '').trim();
    if (!clean) {
      this.showTrySuggestions();
      return;
    }

    const normQuery = normalizeSearchText(clean);
    if (!normQuery) {
      this.closeSuggestions();
      return;
    }

    const matches = [];
    for (const card of this.cachedCards) {
      const textPool = [
        card.problem_summary || '',
        card.problem_summary_quote || '',
        card.transcript || '',
        card.possible_causes_quote || '',
        card.checks_quote || '',
        card.solution_steps_quote || '',
      ].join(' ');

      if (normalizeSearchText(textPool).includes(normQuery)) {
        matches.push(card);
        if (matches.length >= 5) break;
      }
    }

    if (matches.length === 0) {
      this.closeSuggestions();
      return;
    }

    this.currentSuggestions = matches.map((card, idx) => ({
      type: 'card',
      query: card.problem_summary || card.problem_summary_quote || clean,
      id: `suggestion-item-${idx}`,
      card: card,
    }));
    this.activeSuggestionIndex = -1;

    this.searchSuggestionsList.innerHTML = `
      <div class="suggestions-header">Matching Preserved Notes (${matches.length})</div>
      <div class="suggestions-items-list">
        ${matches.map((card, idx) => {
          const isReal = card.origin_tag === 'Real';
          return `
            <div
              class="suggestion-item"
              data-idx="${idx}"
              role="option"
              id="suggestion-item-${idx}"
              aria-selected="false"
              tabindex="-1"
            >
              <div class="suggestion-item-text" dir="auto">${escapeHtml(card.problem_summary || card.problem_summary_quote || 'Preserved Note')}</div>
              <div class="suggestion-item-meta">
                <span class="suggestion-item-expert">${escapeHtml(card.expert_name || 'Anonymous Contributor')}</span>
                <span class="pill ${isReal ? 'pill-real' : 'pill-demo'}">${isReal ? 'Real' : 'Demo'}</span>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    this.bindSuggestionClicks();
    this.openSuggestions();
  }

  bindSuggestionClicks() {
    if (!this.searchSuggestionsList) return;

    const elements = this.searchSuggestionsList.querySelectorAll('[data-idx]');
    elements.forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const idx = parseInt(el.dataset.idx, 10);
        this.chooseSuggestion(idx);
      });
    });
  }

  chooseSuggestion(idx) {
    const item = this.currentSuggestions[idx];
    if (!item) return;

    this.searchInput.value = item.query;
    if (this.searchClearBtn) {
      this.searchClearBtn.style.display = 'inline-flex';
    }
    this.closeSuggestions();
    this.performSearch(item.query).catch(err =>
      console.error('SearchController: performSearch() failed:', err)
    );
  }

  updateActiveDescendant() {
    if (!this.searchSuggestionsList) return;

    const items = this.searchSuggestionsList.querySelectorAll('[role="option"]');
    items.forEach((item, idx) => {
      const isSelected = idx === this.activeSuggestionIndex;
      item.setAttribute('aria-selected', isSelected ? 'true' : 'false');
      item.classList.toggle('is-active', isSelected);
      if (isSelected) {
        this.searchInput.setAttribute('aria-activedescendant', item.id);
        item.scrollIntoView({ block: 'nearest' });
      }
    });

    if (this.activeSuggestionIndex === -1) {
      this.searchInput.removeAttribute('aria-activedescendant');
    }
  }

  openSuggestions() {
    if (this.searchPillWrapper) {
      this.searchPillWrapper.classList.add('is-open');
    }
    if (this.searchInput) {
      this.searchInput.setAttribute('aria-expanded', 'true');
    }
    if (this.searchSuggestionsList) {
      this.searchSuggestionsList.style.display = 'block';
    }
  }

  closeSuggestions() {
    if (this.searchPillWrapper) {
      this.searchPillWrapper.classList.remove('is-open');
    }
    if (this.searchInput) {
      this.searchInput.setAttribute('aria-expanded', 'false');
      this.searchInput.removeAttribute('aria-activedescendant');
    }
    if (this.searchSuggestionsList) {
      this.searchSuggestionsList.style.display = 'none';
    }
    this.activeSuggestionIndex = -1;
    this.currentSuggestions = [];
  }

  async performSearch(query) {
    const cleanQuery = (query || '').trim();
    if (!cleanQuery) {
      this.loadAllCards();
      return;
    }

    if (this.isSearching) return;
    this.isSearching = true;

    // UI state
    this.searchLoading.style.display          = 'flex';
    this.searchFallbackState.style.display    = 'none';
    this.searchResultsContainer.style.display = 'none';
    this.searchResultsMeta.style.display      = 'none';

    try {
      const resp = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: cleanQuery }),
      });

      if (!resp.ok) {
        throw new Error(`Search request failed (${resp.status})`);
      }

      const data = await resp.json();
      const results = data.results || [];

      if (results.length === 0) {
        // Fallback state: "I don't know — no expert has covered this yet"
        this.searchFallbackState.style.display = 'block';
        this.resultsCountText.textContent = `No expert has covered "${cleanQuery}" yet`;
        this.searchResultsMeta.style.display = 'flex';
      } else {
        // Render ranked results
        this.resultsCountText.textContent = `Found ${results.length} expert note${results.length > 1 ? 's' : ''} matching "${cleanQuery}"`;
        this.searchResultsMeta.style.display = 'flex';
        this.renderCards(results, true);
        this.searchResultsContainer.style.display = 'grid';
      }
    } catch (err) {
      console.error("Search error:", err);
      this.searchFallbackState.style.display = 'block';
      this.resultsCountText.textContent = `Search error occurred`;
      this.searchResultsMeta.style.display = 'flex';
    } finally {
      this.searchLoading.style.display = 'none';
      this.isSearching = false;
    }
  }

  async loadAllCards() {
    this.searchLoading.style.display          = 'flex';
    this.searchFallbackState.style.display    = 'none';
    this.searchResultsContainer.style.display = 'none';
    this.searchResultsMeta.style.display      = 'none';

    try {
      const resp = await fetch('/api/cards');
      if (!resp.ok) throw new Error("Failed to load cards");

      const data = await resp.json();
      const cards = data.cards || [];
      this.cachedCards = cards;

      if (cards.length === 0) {
        this.resultsCountText.textContent = "No cards preserved yet — record the first note below.";
        this.searchResultsMeta.style.display = 'flex';
        this.searchResultsContainer.innerHTML = `
          <div class="empty-library-note">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="margin: 0 auto 0.5rem auto; color: var(--text-muted); display: block;">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
              <line x1="12" y1="19" x2="12" y2="22"></line>
            </svg>
            <p><strong>The knowledge base is currently empty.</strong></p>
            <p>Use the contribution flow below to record the first diagnostic note!</p>
          </div>
        `;
        this.searchResultsContainer.style.display = 'block';
      } else {
        this.resultsCountText.textContent = `Preserved Diagnostic Library (${cards.length} expert card${cards.length > 1 ? 's' : ''})`;
        this.searchResultsMeta.style.display = 'flex';
        this.renderCards(cards, false);
        this.searchResultsContainer.style.display = 'grid';
      }
    } catch (err) {
      console.error("Error loading library cards:", err);
    } finally {
      this.searchLoading.style.display = 'none';
    }
  }

  renderCards(cards, isSearchResult) {
    this.searchResultsContainer.innerHTML = '';

    cards.forEach((card, index) => {
      const cardEl = document.createElement('article');
      cardEl.className = 'result-card' + (isSearchResult && index === 0 ? ' result-card--best-match' : '');

      const isReal = card.origin_tag === 'Real';
      const audioUrl = card.audio_path
        ? (card.audio_path.startsWith('/') ? card.audio_path : `/${card.audio_path}`)
        : '';

      const quoteText = card.problem_summary_quote || card.transcript || 'No quote recorded.';
      const summaryText = card.problem_summary || '';

      cardEl.innerHTML = `
        <!-- Verbatim Quote First -->
        <div class="result-card-quote-section">
          <blockquote class="result-verbatim-quote" dir="auto">“${escapeHtml(quoteText)}”</blockquote>
          ${summaryText ? `<p class="result-quote-summary" dir="auto">${escapeHtml(summaryText)}</p>` : ''}
        </div>

        <!-- Meta Bar: Expert Name, Origin, Expert-Approved, Score -->
        <div class="result-card-meta">
          <div class="result-card-author">
            <span class="author-name">${escapeHtml(card.expert_name || 'Anonymous Contributor')}</span>
          </div>
          <div class="result-card-pills">
            ${isSearchResult && index === 0 ? `<span class="pill pill-best-match">Best match</span>` : ''}
            <span class="pill ${isReal ? 'pill-real' : 'pill-demo'}">${isReal ? 'Real' : 'Demo'}</span>
            <span class="pill pill-approved" title="Verified and approved by expert contributor">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
              <span>Expert-Approved</span>
            </span>
            ${isSearchResult && typeof card.score === 'number' ? `<span class="result-meta-score" title="Relevance Score">Score: ${(card.score * 100).toFixed(0)}%</span>` : ''}
          </div>
        </div>

        <!-- Full-Width Audio Player -->
        ${audioUrl ? `
          <div class="result-audio-wrapper">
            <audio controls preload="none" src="${escapeHtml(audioUrl)}"></audio>
          </div>
        ` : ''}

        <!-- Expandable Full Diagnostic Fields -->
        <details class="result-card-details">
          <summary class="details-toggle-btn">
            <span>Diagnostic Breakdown (Causes, Checks, Solutions, Cautions)</span>
            <svg class="details-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary>
          <div class="details-content-grid">
            ${(card.possible_causes_quote || card.possible_causes) ? `
              <div class="detail-box">
                <div class="detail-label">Possible Causes</div>
                ${card.possible_causes_quote ? `<blockquote class="detail-quote" dir="auto">${escapeHtml(card.possible_causes_quote)}</blockquote>` : ''}
                ${card.possible_causes ? `<div class="detail-summary" dir="auto">${escapeHtml(card.possible_causes)}</div>` : ''}
              </div>
            ` : ''}

            ${(card.checks_quote || card.checks) ? `
              <div class="detail-box">
                <div class="detail-label">Verification Checks</div>
                ${card.checks_quote ? `<blockquote class="detail-quote" dir="auto">${escapeHtml(card.checks_quote)}</blockquote>` : ''}
                ${card.checks ? `<div class="detail-summary" dir="auto">${escapeHtml(card.checks)}</div>` : ''}
              </div>
            ` : ''}

            ${(card.solution_steps_quote || card.solution_steps) ? `
              <div class="detail-box">
                <div class="detail-label">Solution Steps</div>
                ${card.solution_steps_quote ? `<blockquote class="detail-quote" dir="auto">${escapeHtml(card.solution_steps_quote)}</blockquote>` : ''}
                ${card.solution_steps ? `<div class="detail-summary" dir="auto">${escapeHtml(card.solution_steps)}</div>` : ''}
              </div>
            ` : ''}

            ${(card.has_caution || card.cautions_quote || card.cautions) ? `
              <div class="detail-box detail-box-caution">
                <div class="detail-label detail-label-caution">Cautions & Warnings</div>
                ${card.cautions_quote ? `<blockquote class="detail-quote" dir="auto">${escapeHtml(card.cautions_quote)}</blockquote>` : ''}
                ${card.cautions ? `<div class="detail-summary" dir="auto">${escapeHtml(card.cautions)}</div>` : ''}
              </div>
            ` : ''}

            <div class="detail-box detail-box-transcript">
              <div class="detail-label">Full Approved Transcript</div>
              <div class="detail-transcript-text" dir="auto">${escapeHtml(card.transcript || '')}</div>
            </div>
          </div>
        </details>
      `;

      this.searchResultsContainer.appendChild(cardEl);
    });
  }
}
