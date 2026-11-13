document.querySelectorAll('[data-sort]').forEach(button => {
  button.addEventListener('click', () => {
    const url = new URL(window.location.href);
    const same = url.searchParams.get('sort') === button.dataset.sort;
    url.searchParams.set('sort', button.dataset.sort);
    url.searchParams.set('direction', same && url.searchParams.get('direction') !== 'desc' ? 'desc' : 'asc');
    window.location.assign(url);
  });
});
document.querySelectorAll('.decision-form').forEach(form => {
  const select = form.querySelector('select');
  const note = form.querySelector('textarea');
  const update = () => { note.required = Boolean(select.value); };
  select.addEventListener('change', update);
  update();
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
if (window.location.hash) {
  const target = document.getElementById(window.location.hash.slice(1));
  if (target?.tagName === 'DETAILS') target.open = true;
}
