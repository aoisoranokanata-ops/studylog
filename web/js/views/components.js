// 画面の共通部品。

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key in node && key !== 'list') node[key] = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(typeof child === 'string' || typeof child === 'number' ? String(child) : child);
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.firstChild.remove();
  return node;
}

export function card(title, children) {
  return el('section', { class: 'card' }, [title ? el('div', { class: 'card-title', text: title }) : null, ...[].concat(children)]);
}

export function toast(message, { error = false, ms = 3200 } = {}) {
  const root = document.getElementById('toast-root');
  const node = el('div', { class: `toast${error ? ' toast-error' : ''}`, text: message });
  root.append(node);
  setTimeout(() => node.remove(), ms);
}

// --- ボトムシート -----------------------------------------------------------

export function openSheet({ title, body, actions = [], onClose }) {
  const root = document.getElementById('sheet-root');
  let resolveWith;
  const done = new Promise((resolve) => {
    resolveWith = resolve;
  });

  const close = (value) => {
    backdrop.remove();
    if (onClose) onClose(value);
    resolveWith(value);
  };

  const buttons = actions.map((action) =>
    el('button', {
      type: 'button',
      class: `btn ${action.primary ? 'btn-primary' : ''} ${action.danger ? 'btn-danger' : ''}`.trim(),
      text: action.label,
      onClick: async () => {
        const value = action.value !== undefined ? action.value : await action.onClick?.();
        if (value === false) return; // 入力エラーなどで閉じたくない場合
        close(value);
      },
    }),
  );

  const sheet = el('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true' }, [
    el('div', { class: 'sheet-title', text: title }),
    ...[].concat(body || []),
    el('div', { class: 'btn-row' }, buttons),
  ]);

  const backdrop = el('div', {
    class: 'sheet-backdrop',
    onClick: (event) => {
      if (event.target === backdrop) close(undefined);
    },
  }, [sheet]);

  root.append(backdrop);
  sheet.querySelector('input, select, textarea, button')?.focus({ preventScroll: true });
  return done;
}

export function confirmSheet(title, message, { okText = 'はい', danger = false } = {}) {
  return openSheet({
    title,
    body: [el('p', { class: 'dim', text: message })],
    actions: [
      { label: 'やめる', value: false },
      { label: okText, value: true, primary: !danger, danger },
    ],
  }).then((value) => value === true);
}

// --- 分類（資格・参考書・分野） ---------------------------------------------

export function subjectLabel(subjects, subject) {
  if (!subject?.parentId) return subject?.name || '';
  const parent = subjects.find((item) => item.id === subject.parentId);
  return parent ? `${parent.name} / ${subject.name}` : subject.name;
}

/**
 * 参照用データを持っていない子機では「未分類」しか選べない（転送仕様書 A-4）。
 */
export function classificationPicker(options, initial = {}) {
  const exam = el('select', { id: 'pick-exam' });
  const material = el('select', { id: 'pick-material' });
  const subject = el('select', { id: 'pick-subject' });

  const fill = (select, items, selected, emptyLabel) => {
    clear(select);
    select.append(el('option', { value: '', text: emptyLabel }));
    for (const item of items) {
      select.append(el('option', { value: item.id, text: item.label, selected: item.id === selected }));
    }
    if (!items.some((item) => item.id === selected)) select.value = '';
  };

  const fillChildren = (values = {}) => {
    const examId = exam.value;
    const materials = (options.materials || [])
      .filter((item) => item.examId === examId && !item.archived)
      .map((item) => ({ id: item.id, label: item.name }));
    const subjects = (options.subjects || [])
      .filter((item) => item.examId === examId && !item.archived)
      .map((item) => ({ id: item.id, label: subjectLabel(options.subjects, item) }));
    fill(material, materials, values.materialId, '（指定なし）');
    fill(subject, subjects, values.subjectId, '（指定なし）');
  };

  fill(
    exam,
    (options.exams || []).filter((item) => !item.archived).map((item) => ({ id: item.id, label: item.name })),
    initial.examId,
    '（未分類）',
  );
  fillChildren(initial);
  exam.addEventListener('change', () => fillChildren());

  const element = el('div', {}, [
    el('div', { class: 'field' }, [el('label', { for: 'pick-exam', text: '資格' }), exam]),
    el('div', { class: 'field' }, [el('label', { for: 'pick-material', text: '参考書' }), material]),
    el('div', { class: 'field' }, [el('label', { for: 'pick-subject', text: '分野' }), subject]),
    options.hasMasters
      ? null
      : el('p', {
          class: 'dim small',
          text: '参照用データをまだ受け取っていないので、未分類でのみ記録できます。一度ファイルで受け取ると選べるようになります。',
        }),
  ]);

  return {
    element,
    values: () => ({
      examId: exam.value || null,
      materialId: material.value || null,
      subjectId: subject.value || null,
    }),
  };
}

// --- 入力の小物 -------------------------------------------------------------

export function field(labelText, input) {
  const id = input.id || `f-${Math.random().toString(36).slice(2, 8)}`;
  input.id = id;
  return el('div', { class: 'field' }, [el('label', { for: id, text: labelText }), input]);
}

export function numberInput(props = {}) {
  return el('input', { type: 'number', inputmode: 'numeric', ...props });
}

export function optionalInt(value) {
  if (value === '' || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}

/** datetime-local の値（ローカル時刻）をそのまま扱うための変換。 */
export function toLocalInput(isoText) {
  const date = new Date(isoText);
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function fromLocalInput(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error('日時を正しく入力してください');
  return date;
}
