document.querySelectorAll('[data-sort]').forEach(button => {
  button.addEventListener('click', () => {
    const url = new URL(window.location.href);
    const same = (url.searchParams.get('sort') || 'name') === button.dataset.sort;
    url.searchParams.set('sort', button.dataset.sort);
    url.searchParams.set('direction', same && url.searchParams.get('direction') !== 'desc' ? 'desc' : 'asc');
    window.location.assign(url);
  });
});
const upload = document.querySelector('[data-upload-form]');
if (upload) {
  const file = upload.querySelector('input[type=file]');
  file.addEventListener('change', () => {
    document.querySelector('[data-file-name]').textContent = file.files[0]?.name || 'No file selected';
  });
  upload.addEventListener('submit', () => {
    const button = upload.querySelector('button[type=submit]');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = 'Reading archive…';
  });
}
const progress = document.querySelector('[data-progress-url]');
if (progress) {
  const poll = async () => {
    try {
      const response = await fetch(progress.dataset.progressUrl, {cache: 'no-store'});
      if (!response.ok) throw new Error('Progress unavailable');
      const data = await response.json();
      if (String(data.done) !== progress.dataset.done || !['queued', 'running'].includes(data.state)) {
        window.location.reload();
        return;
      }
    } catch {
      progress.querySelector('p').textContent = 'Connection interrupted. Reconnecting; saved results are retained.';
    }
    window.setTimeout(poll, 2500);
  };
  window.setTimeout(poll, 2500);
}

// Store position per browser tab and review, without student information.
const gridPanel = document.querySelector('[data-grid-review]');
if (gridPanel) {
  const tableScroll = gridPanel.querySelector('.table-scroll');
  const positionKey = `moderation-grid:${gridPanel.dataset.gridReview}`;
  [...gridPanel.querySelectorAll('a[href*="/reviews/"]'), ...document.querySelectorAll('[data-review-next]')].forEach(link => {
    link.addEventListener('click', () => {
      try {
        sessionStorage.setItem(positionKey, JSON.stringify({
          query: window.location.search.replace(/([?&])saved=[^&]*&?/, '$1').replace(/[?&]$/, ''),
          y: window.scrollY, x: window.scrollX, table: tableScroll.scrollLeft,
        }));
      } catch { /* Navigation works when storage is unavailable. */ }
    });
  });
  const savedCell = gridPanel.dataset.savedCell;
  const savedTarget = Array.from(gridPanel.querySelectorAll('[data-grid-cell]')).find(cell => cell.dataset.gridCell === savedCell);
  if (savedTarget) {
    savedTarget.classList.add('decision-saved');
    window.setTimeout(() => savedTarget.classList.remove('decision-saved'), 5000);
  }
  try {
    const stored = JSON.parse(sessionStorage.getItem(positionKey));
    const currentQuery = new URLSearchParams(window.location.search);
    currentQuery.delete('saved');
    const previousQuery = new URLSearchParams(stored?.query || '');
    currentQuery.sort(); previousQuery.sort();
    if (stored && currentQuery.toString() === previousQuery.toString()) {
      requestAnimationFrame(() => {
        tableScroll.scrollLeft = stored.table;
        window.scrollTo(stored.x, stored.y);
      });
    }
  } catch { /* No saved grid position yet. */ }
}
const reviewFindings = Array.from(document.querySelectorAll('.finding'));
if (reviewFindings.length) {
  let activeFinding = null;
  const activateFinding = finding => {
    if (activeFinding === finding) return;
    reviewFindings.forEach(other => {
      const evidence = other.querySelector('.evidence');
      if (evidence) evidence.open = other === finding;
    });
    activeFinding = finding;
  };
  const openCurrentFinding = () => {
    const finding = document.getElementById(window.location.hash.slice(1));
    if (finding && reviewFindings.includes(finding)) {
      finding.open = true;
      activateFinding(finding);
      finding.querySelector('select')?.focus({preventScroll: true});
      window.requestAnimationFrame(() => finding.scrollIntoView({block: 'start'}));
    }
  };
  reviewFindings.forEach(finding => {
    finding.querySelector('summary')?.addEventListener('click', () => activateFinding(finding));
    finding.querySelector('.decision-form')?.addEventListener('focusin', () => activateFinding(finding));
  });
  openCurrentFinding();
  window.addEventListener('hashchange', openCurrentFinding);
}

document.querySelectorAll('[data-copy-feedback]').forEach(feedbackCopy => {
  feedbackCopy.addEventListener('click', async () => {
    const textarea = document.getElementById(feedbackCopy.dataset.feedbackTarget || 'elp-feedback');
    const status = feedbackCopy.dataset.statusTarget ? document.getElementById(feedbackCopy.dataset.statusTarget) : document.querySelector('[data-copy-status]');
    try {
      const response = await fetch(feedbackCopy.dataset.verifyUrl, {cache: 'no-store'});
      if (!response.ok || !(await response.json()).current) {
        textarea.value = '';
        feedbackCopy.disabled = true;
        status.textContent = 'The moderation results changed. Return to the submission, finish its review and regenerate feedback.';
        return;
      }
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(textarea.value);
        status.textContent = 'Feedback copied. Paste it into eLP.';
      } else {
        textarea.select();
        status.textContent = 'Feedback selected. Press Ctrl+C to copy, then paste into eLP.';
      }
    } catch {
      status.textContent = 'Could not verify and copy feedback. Check the server is running and try again.';
    }
  });
});

const auditComplete = document.querySelector('[data-audit-complete]');
if (auditComplete) {
  auditComplete.addEventListener('click', () => {
    document.querySelectorAll('[data-audit-row]').forEach(row => {
      if (!row.querySelector('input:checked')) {
        row.querySelector('input[value="complete"]').checked = true;
      }
    });
  });
}
