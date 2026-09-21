// 記録：手動での追加と、履歴（未取り込み／取り込み済み）。

import { formatClock, formatHm, nowIso, studyDate, toIso } from '../clock.js';
import * as store from '../store.js';
import {
  card,
  classificationPicker,
  confirmSheet,
  el,
  field,
  fromLocalInput,
  numberInput,
  openSheet,
  optionalInt,
  toast,
  toLocalInput,
} from './components.js';

export async function render(root, app) {
  const [sessions, settings, options] = await Promise.all([
    store.listRecords('sessions'),
    store.getSettings(),
    store.classificationOptions(),
  ]);

  root.append(
    el('button', {
      type: 'button',
      class: 'btn btn-primary btn-block',
      text: '手動で記録を追加',
      onClick: () => openManualSheet(app, options),
    }),
  );

  const sorted = [...sessions].sort((a, b) => (a.startedAt < b.startedAt ? 1 : -1));
  const pending = sorted.filter((session) => session.state !== 'acked');
  const acked = sorted.filter((session) => session.state === 'acked');

  root.append(
    card(
      `未取り込み（${pending.length}件）`,
      pending.length
        ? await Promise.all(pending.map((session) => row(session, settings, app, true)))
        : [el('p', { class: 'empty', text: '未取り込みの記録はありません' })],
    ),
  );

  root.append(
    card(
      `取り込み済み（${acked.length}件・7日で消えます）`,
      acked.length
        ? await Promise.all(acked.map((session) => row(session, settings, app, false)))
        : [el('p', { class: 'empty', text: '取り込み済みの記録はありません' })],
    ),
  );
}

async function row(session, settings, app, editable) {
  const labels = await store.labelsFor(session);
  const parts = [labels.exam, labels.material, labels.subject].filter(Boolean);
  const title = parts.length ? parts.join('　') : '未分類';
  const date = studyDate(new Date(session.startedAt), settings.dayChangeHour);

  return el('div', { class: 'record' }, [
    el('div', { class: 'row-between' }, [
      el('span', { class: 'strong truncate grow', text: title }),
      el('span', { class: 'strong', text: formatHm(session.activeSeconds) }),
    ]),
    el('div', { class: 'dim small', text: `${date} ${formatClock(session.startedAt)}〜${formatClock(session.endedAt)}　${session.entryMode === 'manual' ? '手動' : '計測'}` }),
    session.memo ? el('div', { class: 'small truncate', text: session.memo }) : null,
    session.deleted ? el('span', { class: 'badge', text: '取り消し済み（送信待ち）' }) : null,
    editable && !session.deleted
      ? el('div', { class: 'row' }, [
          el('button', {
            type: 'button',
            class: 'btn btn-small',
            text: '編集',
            onClick: () => openManualSheet(app, null, session),
          }),
          el('button', {
            type: 'button',
            class: 'btn btn-small btn-danger',
            text: '取り消す',
            onClick: async () => {
              if (!(await confirmSheet('記録を取り消す', 'この記録を取り消します。よろしいですか？', { okText: '取り消す', danger: true }))) return;
              const result = await store.removeSession(session.id);
              toast(result === 'marked' ? '取り消しを母艦に伝えます' : '削除しました');
              app.refresh();
            },
          }),
        ])
      : null,
  ]);
}

/** 手動記録と編集。時間だけ入れた場合は endedAt を補って送る（仕様書 B-5）。 */
export async function openManualSheet(app, options, session = null) {
  const picker = classificationPicker(options || (await store.classificationOptions()), session || {});
  const startedAt = el('input', {
    type: 'datetime-local',
    value: toLocalInput(session?.startedAt || nowIso()),
  });
  const hours = numberInput({ min: '0', max: '23', value: String(Math.floor((session?.activeSeconds || 3600) / 3600)) });
  const minutes = numberInput({ min: '0', max: '59', value: String(Math.floor(((session?.activeSeconds || 3600) % 3600) / 60)) });
  const memo = el('input', { type: 'text', placeholder: 'メモ（任意）', value: session?.memo || '' });
  const focus = el('select', {}, [
    el('option', { value: '', text: '（未入力）' }),
    ...[1, 2, 3, 4, 5].map((value) =>
      el('option', { value: String(value), text: String(value), selected: session?.focus === value }),
    ),
  ]);

  const result = await openSheet({
    title: session ? '記録を編集' : '手動で記録',
    body: [
      field('開始日時', startedAt),
      el('div', { class: 'field' }, [
        el('label', { text: '勉強時間' }),
        el('div', { class: 'field-row' }, [hours, minutes]),
      ]),
      picker.element,
      field('集中度（任意）', focus),
      field('メモ（任意）', memo),
    ],
    actions: [
      { label: 'やめる', value: null },
      {
        label: '保存',
        primary: true,
        onClick: () => {
          let started;
          try {
            started = fromLocalInput(startedAt.value);
          } catch (error) {
            toast(error.message, { error: true });
            return false;
          }
          const seconds = (optionalInt(hours.value) || 0) * 3600 + (optionalInt(minutes.value) || 0) * 60;
          if (seconds <= 0) {
            toast('勉強時間を入れてください', { error: true });
            return false;
          }
          return { started, seconds };
        },
      },
    ],
  });
  if (!result) return;

  const values = picker.values();
  const endedAt = new Date(result.started.getTime() + result.seconds * 1000);
  await store.putSession({
    id: session?.id || store.newId(),
    createdAt: session?.createdAt || nowIso(),
    quotaId: session?.quotaId || null,
    ...values,
    startedAt: toIso(result.started),
    endedAt: toIso(endedAt),
    activeSeconds: result.seconds,
    range: session?.range || null,
    correct: session?.correct ?? null,
    attempted: session?.attempted ?? null,
    focus: optionalInt(focus.value),
    memo: memo.value.trim(),
    entryMode: session?.entryMode || 'manual',
    deleted: false,
  });
  toast(session ? '更新しました' : '記録しました');
  app.refresh();
}
