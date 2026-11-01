// IABuddy · comportamiento de los componentes (sin dependencias). Ver COMPONENTS.md
// Un solo listener delegado: funciona también con HTML añadido después.

document.addEventListener('click', (e) => {
  const el = e.target.closest('button, [data-open]');
  if (!el || el.disabled) return;

  // Grupo de una sola opción: .segmented / role=group con aria-pressed
  const group = el.closest('.segmented, [data-single]');
  if (group && el.hasAttribute('aria-pressed')) {
    group.querySelectorAll('[aria-pressed]').forEach((b) => b.setAttribute('aria-pressed', String(b === el)));
    group.dispatchEvent(new CustomEvent('change', { detail: el.value || el.textContent.trim() }));
    return;
  }

  // Pestañas
  if (el.getAttribute('role') === 'tab') {
    el.closest('[role=tablist]').querySelectorAll('[role=tab]').forEach((t) => t.setAttribute('aria-selected', String(t === el)));
    return;
  }

  // Alternables sueltos: chips, botones de ícono, tarjetas, interruptores, casillas
  for (const attr of ['aria-pressed', 'aria-checked']) {
    if (el.hasAttribute(attr)) {
      el.setAttribute(attr, String(el.getAttribute(attr) !== 'true'));
      return;
    }
  }

  // Modales: <button data-open="id"> abre; <button data-close> o <form method="dialog"> cierra.
  // showModal() atrapa el foco, Esc cierra y el foco vuelve al botón que lo abrió.
  if (el.dataset.open) document.getElementById(el.dataset.open)?.showModal();
  if (el.hasAttribute('data-close')) el.closest('dialog')?.close();
});

// Esc oculta el tooltip visible sin mover el foco
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  document.querySelectorAll('.tt-wrap:hover, .tt-wrap:focus-within').forEach((w) => w.setAttribute('data-dismissed', ''));
});
document.addEventListener('focusout', (e) => e.target.closest?.('.tt-wrap')?.removeAttribute('data-dismissed'));
document.addEventListener('mouseout', (e) => e.target.closest?.('.tt-wrap')?.removeAttribute('data-dismissed'));

// Aviso: máximo uno a la vez; se cierra a los 5 s salvo que lleve acción.
export function toast({ title, text = '', kind = '', action = null }) {
  let region = document.querySelector('.toast-region');
  if (!region) {
    region = Object.assign(document.createElement('div'), { className: 'toast-region' });
    region.setAttribute('role', 'status');
    document.body.append(region);
  }
  const t = document.createElement('div');
  t.className = `toast ${kind ? 'toast-' + kind : ''}`;
  const body = document.createElement('div');
  body.className = 'toast-body';
  body.innerHTML = '<span class="toast-title"></span><span class="toast-text"></span>';
  body.children[0].textContent = title;
  body.children[1].textContent = text;
  t.append(body);
  if (action) {
    const b = Object.assign(document.createElement('button'), { className: 'btn btn-primary btn-s', textContent: action.label });
    b.addEventListener('click', () => { action.onClick?.(); t.remove(); });
    t.append(b);
  }
  region.replaceChildren(t);
  if (!action) setTimeout(() => t.remove(), 5000);
}
