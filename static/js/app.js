/**
 * Voice of Experience (صوت الخبرة) — Main Application Entrypoint
 */

import { ContributionWizard } from './contribution.js';
import { SearchController } from './search.js';

document.addEventListener('DOMContentLoaded', async () => {
  console.log("Voice of Experience client initializing...");

  // Check backend health
  const statusEl = document.getElementById('apiStatusIndicator');
  try {
    const res = await fetch('/api/health');
    if (res.ok) {
      const data = await res.json();
      if (statusEl) {
        statusEl.innerHTML = `<span class="status-dot"></span><span>System Online</span>`;
        statusEl.style.color = '#065f46';
        statusEl.style.background = '#ecfdf5';
        statusEl.style.borderColor = '#a7f3d0';
      }
    }
  } catch (e) {
    if (statusEl) {
      statusEl.innerHTML = `<span class="status-dot" style="background:#ef4444;"></span><span>Offline</span>`;
      statusEl.style.color = '#991b1b';
      statusEl.style.background = '#fef2f2';
      statusEl.style.borderColor = '#fecaca';
    }
  }

  // Initialize Stage 4 Search & Knowledge Library
  window.searchController = new SearchController();

  // Initialize Contribution Wizard
  window.wizard = new ContributionWizard();
});
