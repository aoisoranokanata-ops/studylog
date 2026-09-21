// 設定。

import { SCHEMA_VERSION } from '../codec.js';
import * as db from '../db.js';
import * as store from '../store.js';
import * as transfer from '../transfer.js';
import { APP_VERSION } from '../version.js';
import { card, confirmSheet, el, field, openSheet, toast } from './components.js';

const THEME_KEY = 'studylog-theme';

export function currentTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || 'auto';
  } catch {
    return 'auto';
  }
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* プライベートブラウズなどで保存できなくても動作は続ける */
  }
}

export async function render(root, app) {
  const [device, status, persisted, wakeLock] = await Promise.all([
    store.getDevice(),
    transfer.status(),
    navigator.storage?.persisted?.() ?? Promise.resolve(false),
    store.getMeta('wakeLock', false),
  ]);

  const name = el('input', { type: 'text', value: device.deviceName, maxlength: '20' });
  root.append(
    card('この端末', [
      field('表示名（送るファイル名に使います）', name),
      el('button', {
        type: 'button',
        class: 'btn btn-block',
        text: '保存',
        onClick: async () => {
          const value = name.value.trim();
          if (!value) {
            toast('表示名を入れてください', { error: true });
            return;
          }
          await store.updateDevice({ deviceName: value });
          toast('保存しました');
        },
      }),
      el('div', { class: 'dim small', text: `ファイル名の例: studylog-up-${transfer.sanitizeDeviceName(name.value)}-…json` }),
    ]),
  );

  const wakeToggle = el('input', { type: 'checkbox', checked: Boolean(wakeLock) });
  const themeSelect = el('select', {}, [
    el('option', { value: 'auto', text: '端末に合わせる', selected: currentTheme() === 'auto' }),
    el('option', { value: 'light', text: '明るい', selected: currentTheme() === 'light' }),
    el('option', { value: 'dark', text: '暗い', selected: currentTheme() === 'dark' }),
  ]);
  themeSelect.addEventListener('change', () => applyTheme(themeSelect.value));
  wakeToggle.addEventListener('change', async () => {
    await store.setMeta('wakeLock', wakeToggle.checked);
    if (!wakeToggle.checked) app.releaseWakeLock();
    toast(wakeToggle.checked ? '計測中は画面を消さないようにします' : '画面消灯の防止をやめました');
  });

  root.append(
    card('表示', [
      field('テーマ', themeSelect),
      el('div', { class: 'row' }, [
        wakeToggle,
        el('span', { class: 'grow', text: '計測中に画面を消さない' }),
      ]),
      'wakeLock' in navigator ? null : el('div', { class: 'dim small', text: 'この端末は画面消灯の防止に対応していません。' }),
    ]),
  );

  root.append(
    card('保存の状態', [
      el('div', { class: 'row-between' }, [
        el('span', { text: '未取り込みの記録' }),
        el('span', { class: 'strong', text: `${status.pending}件` }),
      ]),
      el('div', { class: 'row-between' }, [
        el('span', { text: '保存領域の保護' }),
        el('span', { class: 'strong', text: persisted ? '有効' : '未設定' }),
      ]),
      persisted
        ? null
        : el('div', { class: 'dim small', text: 'ホーム画面に追加して使うと、記録が消えにくくなります。' }),
    ]),
  );

  root.append(
    card('このアプリについて', [
      el('div', { class: 'row-between' }, [el('span', { text: 'バージョン' }), el('span', { text: APP_VERSION })]),
      el('div', { class: 'row-between' }, [
        el('span', { text: '対応する転送形式' }),
        el('span', { text: `schemaVersion ${SCHEMA_VERSION}` }),
      ]),
      el('div', { class: 'dim small', text: '記録は母艦に送るまでこの端末にだけあります。外部への通信は一切しません。' }),
    ]),
  );

  root.append(
    card('データ', [
      el('button', {
        type: 'button',
        class: 'btn btn-danger btn-block',
        text: 'すべてのデータを削除',
        onClick: () => wipe(app, status.pending),
      }),
    ]),
  );
}

async function wipe(app, pending) {
  const first = await confirmSheet(
    'すべてのデータを削除',
    pending
      ? `未取り込みの記録が${pending}件あります。削除すると母艦には二度と入りません。`
      : 'ノルマ・記録・端末IDをすべて消します。',
    { okText: '次へ', danger: true },
  );
  if (!first) return;

  const confirmText = el('input', { type: 'text', placeholder: '削除' });
  const ok = await openSheet({
    title: '本当に削除しますか？',
    body: [
      el('p', { class: 'small', text: '取り消せません。「削除」と入力してください。' }),
      confirmText,
    ],
    actions: [
      { label: 'やめる', value: false },
      {
        label: '削除する',
        danger: true,
        onClick: () => {
          if (confirmText.value.trim() !== '削除') {
            toast('「削除」と入力してください', { error: true });
            return false;
          }
          return true;
        },
      },
    ],
  });
  if (ok !== true) return;

  await db.wipe();
  toast('削除しました');
  app.go('home');
}
