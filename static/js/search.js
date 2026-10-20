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

export class SearchController {
  constructor() {
    this.searchInput            = document.getElementById('searchInput');
    this.searchSubmitBtn         = document.getElementById('searchSubmitBtn');
    this.searchClearBtn          = document.getElementById('searchClearBtn');
    this.searchResultsMeta       = document.getElementById('searchResultsMeta');
    this.resultsCountText        = document.getElementById('resultsCountText');
    this.browseAllBtn            = document.getElementById('browseAllBtn');
    this.searchLoading           = document.getElementById('searchLoading');
    this.searchFallbackState     = document.getElementById('searchFallbackState');
    this.searchResultsContainer  = document.getElementById('searchResultsContainer');
    this.scrollToContributeBtn   = document.getElementById('scrollToContributeBtn');
    this.fallbackBrowseAllBtn    = document.getElementById('fallbackBrowseAllBtn');
    this.fallbackRecordBtn       = document.getElementById('fallbackRecordBtn');

    this.chipButtons             = document.querySelectorAll('.search-chip');
    this.isSearching             = false;

    this.bindEvents();
    this.loadAllCards();
  }

  bindEvents() {
    // Search button click
    if (this.searchSubmitBtn) {
      this.searchSubmitBtn.addEventListener('click', () => {
        this.performSearch(this.searchInput.value);
      });
    }

    // Enter key in input
    if (this.searchInput) {
      this.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.performSearch(this.searchInput.value);
        }
      });

      this.searchInput.addEventListener('input', () => {
        const val = this.searchInput.value.trim();
        if (this.searchClearBtn) {
          this.searchClearBtn.style.display = val ? 'inline-block' : 'none';
        }
      });
    }

    // Clear button
    if (this.searchClearBtn) {
      this.searchClearBtn.addEventListener('click', () => {
        this.searchInput.value = '';
        this.searchClearBtn.style.display = 'none';
        this.loadAllCards();
        this.searchInput.focus();
      });
    }

    // View all cards button in meta bar
    if (this.browseAllBtn) {
      this.browseAllBtn.addEventListener('click', () => {
        this.searchInput.value = '';
        if (this.searchClearBtn) this.searchClearBtn.style.display = 'none';
        this.loadAllCards();
      });
    }

    // Fallback panel "Browse all cards" button
    if (this.fallbackBrowseAllBtn) {
      this.fallbackBrowseAllBtn.addEventListener('click', () => {
        this.searchInput.value = '';
        if (this.searchClearBtn) this.searchClearBtn.style.display = 'none';
        this.loadAllCards();
      });
    }

    // Scroll to contribution flow buttons
    const scrollToContribute = () => {
      const target = document.getElementById('contributionFlowCard') || document.getElementById('sectionSetup');
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        const nameInput = document.getElementById('expertName');
        if (nameInput) {
          setTimeout(() => nameInput.focus(), 600);
        }
      }
    };

    if (this.scrollToContributeBtn) {
      this.scrollToContributeBtn.addEventListener('click', scrollToContribute);
    }
    if (this.fallbackRecordBtn) {
      this.fallbackRecordBtn.addEventListener('click', scrollToContribute);
    }

    // Hint chips
    this.chipButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const query = btn.dataset.query || btn.textContent.trim();
        this.searchInput.value = query;
        if (this.searchClearBtn) this.searchClearBtn.style.display = 'inline-block';
        this.performSearch(query);
      });
    });
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

      if (cards.length === 0) {
        this.resultsCountText.textContent = "No cards preserved yet — record the first note below.";
        this.searchResultsMeta.style.display = 'flex';
        this.searchResultsContainer.innerHTML = `
          <div class="empty-library-note">
            <span style="font-size: 2rem;">🎙</span>
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

      const scoreBadgeHtml = (isSearchResult && typeof card.score === 'number')
        ? `<span class="badge badge-score" title="Cosine Similarity Score">Match: ${(card.score * 100).toFixed(1)}%</span>`
        : '';

      const bestMatchBadgeHtml = (isSearchResult && index === 0)
        ? `<span class="badge badge-best-match">★ Best match</span>`
        : '';

      const quoteText = card.problem_summary_quote || card.transcript || 'No quote recorded.';
      const summaryText = card.problem_summary || '';

      cardEl.innerHTML = `
        <div class="result-card-header">
          <div class="result-card-author">
            <span class="author-icon" aria-hidden="true">👤</span>
            <span class="author-name">${escapeHtml(card.expert_name || 'Anonymous Contributor')}</span>
          </div>
          <div class="result-card-badges">
            ${bestMatchBadgeHtml}
            ${scoreBadgeHtml}
            <span class="badge ${isReal ? 'badge-real' : 'badge-demo'}">[${isReal ? 'Real' : 'Demo'}]</span>
            <span class="badge badge-approved" title="Verified by expert contributor">✓ Expert-Approved</span>
          </div>
        </div>

        <!-- Verbatim Quote First (Grounded human advice) -->
        <div class="result-card-quote-section">
          <div class="result-quote-header">
            <span class="quote-type-pill">Spoken Diagnostic Quote (الخبرة المنطوقة):</span>
          </div>
          <blockquote class="result-verbatim-quote" dir="rtl" lang="ar">
            “${escapeHtml(quoteText)}”
          </blockquote>
          ${summaryText ? `<div class="result-quote-summary">${escapeHtml(summaryText)}</div>` : ''}
        </div>

        <!-- Audio Player -->
        ${audioUrl ? `
          <div class="result-audio-wrapper">
            <span class="audio-caption">🎙 Original Voice Recording:</span>
            <audio controls preload="none" src="${escapeHtml(audioUrl)}"></audio>
          </div>
        ` : ''}

        <!-- Expandable Full Diagnostic Fields -->
        <details class="result-card-details">
          <summary class="details-toggle-btn">
            <span>Diagnostic Breakdown (Causes, Checks, Solutions, Cautions)</span>
            <span class="details-chevron">▾</span>
          </summary>
          <div class="details-content-grid">
            ${(card.possible_causes_quote || card.possible_causes) ? `
              <div class="detail-box">
                <div class="detail-label">⚙ Possible Causes</div>
                ${card.possible_causes_quote ? `<blockquote class="detail-quote" dir="rtl" lang="ar">${escapeHtml(card.possible_causes_quote)}</blockquote>` : ''}
                ${card.possible_causes ? `<div class="detail-summary">${escapeHtml(card.possible_causes)}</div>` : ''}
              </div>
            ` : ''}

            ${(card.checks_quote || card.checks) ? `
              <div class="detail-box">
                <div class="detail-label">✓ Verification Checks</div>
                ${card.checks_quote ? `<blockquote class="detail-quote" dir="rtl" lang="ar">${escapeHtml(card.checks_quote)}</blockquote>` : ''}
                ${card.checks ? `<div class="detail-summary">${escapeHtml(card.checks)}</div>` : ''}
              </div>
            ` : ''}

            ${(card.solution_steps_quote || card.solution_steps) ? `
              <div class="detail-box">
                <div class="detail-label">🛠 Solution Steps</div>
                ${card.solution_steps_quote ? `<blockquote class="detail-quote" dir="rtl" lang="ar">${escapeHtml(card.solution_steps_quote)}</blockquote>` : ''}
                ${card.solution_steps ? `<div class="detail-summary">${escapeHtml(card.solution_steps)}</div>` : ''}
              </div>
            ` : ''}

            ${(card.has_caution || card.cautions_quote || card.cautions) ? `
              <div class="detail-box detail-box-caution">
                <div class="detail-label detail-label-caution">⚠ Cautions & Warnings</div>
                ${card.cautions_quote ? `<blockquote class="detail-quote" dir="rtl" lang="ar">${escapeHtml(card.cautions_quote)}</blockquote>` : ''}
                ${card.cautions ? `<div class="detail-summary">${escapeHtml(card.cautions)}</div>` : ''}
              </div>
            ` : ''}

            <div class="detail-box detail-box-transcript">
              <div class="detail-label">📝 Full Approved Transcript</div>
              <div class="detail-transcript-text" dir="rtl" lang="ar">${escapeHtml(card.transcript || '')}</div>
            </div>
          </div>
        </details>
      `;

      this.searchResultsContainer.appendChild(cardEl);
    });
  }
}
