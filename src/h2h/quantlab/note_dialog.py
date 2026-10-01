"""Shared modal presentation for pick explanations on QuantLab pages."""

NOTE_DIALOG_CSS = """
.pick-note-dialog{width:min(680px,calc(100vw - 24px));max-width:none;max-height:min(85vh,800px);padding:20px;border:1px solid #3b434a;border-radius:14px;background:#111518;color:#edf0f2;box-shadow:0 24px 70px rgba(0,0,0,.6);overflow:auto}
.pick-note-dialog::backdrop{background:rgba(0,0,0,.72)}
.pick-note-dialog .note-popover{position:static;width:auto;min-width:0;max-width:none;max-height:none;margin:0;padding:0;border:0;box-shadow:none;background:transparent;white-space:normal}
.pick-note-dialog .note-close{position:sticky;top:0;float:right;width:30px;height:30px;margin:-8px -8px 4px 12px;padding:0;border:1px solid #4a535b;border-radius:8px;background:#242b31;color:#edf0f2;font-size:21px;line-height:1;cursor:pointer}
.pick-note-dialog .note-close:hover{background:#39434b}
"""

NOTE_DIALOG_HTML = """<dialog class="pick-note-dialog" aria-label="Objašnjenje pika"></dialog>
<script>
(() => {
  const dialog = document.querySelector('.pick-note-dialog');
  document.addEventListener('click', (event) => {
    const summary = event.target.closest('.pick-note > summary');
    if (!summary) return;
    const note = summary.parentElement.querySelector('.note-popover');
    if (!note) return;
    event.preventDefault();
    dialog.replaceChildren();
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'note-close';
    close.setAttribute('aria-label', 'Zatvori objašnjenje');
    close.textContent = '×';
    close.addEventListener('click', () => dialog.close());
    dialog.append(close, note.cloneNode(true));
    dialog.showModal();
    close.focus();
  });
  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
})();
</script>"""
