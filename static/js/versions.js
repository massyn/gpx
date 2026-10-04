// Previous versions dialog: lists the file's saved versions, with download and restore for each.
// The list is fetched each time the dialog opens, so versions saved by edits in this visit appear.

(() => {
  const { esc } = editor;
  const listUrl = window.GPX_EDITOR.urls.versions;
  const body = document.getElementById('versionsBody');
  const restoreForm = document.getElementById('restoreForm');

  async function load() {
    body.innerHTML = '<p class="text-muted small mb-0">Loading…</p>';
    try {
      const res = await fetch(listUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      render((await res.json()).versions);
    } catch (err) {
      body.innerHTML = `<p class="text-danger small mb-0">Could not load versions (${esc(err.message)}).</p>`;
    }
  }

  function render(versions) {
    if (!versions.length) {
      body.innerHTML = '<p class="text-muted small mb-0">No previous versions yet. One is saved the first time this file changes.</p>';
      return;
    }
    body.innerHTML = `<table class="table table-hover align-middle mb-0">
      <thead><tr><th>Saved</th><th class="text-end">Size</th><th></th></tr></thead>
      <tbody>${versions.map(v => `
        <tr>
          <td>${esc(v.saved)}${v.undone ? ' <span class="badge bg-secondary" title="Replaced by Undo">undone</span>' : ''}</td>
          <td class="text-end text-nowrap">${v.size_kb.toLocaleString()} KB</td>
          <td class="text-end text-nowrap">
            <a class="btn btn-sm btn-outline-secondary" href="${esc(`${listUrl}/${v.stamp}`)}">Download</a>
            <button class="btn btn-sm btn-outline-amber" data-stamp="${esc(v.stamp)}" data-saved="${esc(v.saved)}">Restore</button>
          </td>
        </tr>`).join('')}</tbody></table>`;
  }

  body.addEventListener('click', e => {
    const button = e.target.closest('button[data-stamp]');
    if (!button) return;
    if (!confirm(`Restore the version saved ${button.dataset.saved}? The current file will be kept as a version.`)) return;
    restoreForm.action = `${listUrl}/${button.dataset.stamp}/restore`;
    restoreForm.submit();
  });

  document.getElementById('versionsModal').addEventListener('show.bs.modal', load);
})();
