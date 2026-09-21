// 計測を終えるときの確認シート。入力はすべて任意で、そのまま保存できる（2タップ）。

import { formatHms, nowIso, parseIso, toIso } from '../clock.js';
import { LONG_SESSION_SECONDS } from '../timer.js';
import {
  el,
  field,
  fromLocalInput,
  numberInput,
  openSheet,
  optionalInt,
  toast,
  toLocalInput,
} from './components.js';

export function openFinishSheet({ state, elapsed, quota }) {
  const isLong = elapsed >= LONG_SESSION_SECONDS;
  const endedAt = el('input', { type: 'datetime-local', value: toLocalInput(nowIso()) });
  const duration = el('div', { class: 'strong', text: formatHms(elapsed) });

  const rangeUnit = el('select', {}, [
    el('option', { value: '', text: '（指定なし）' }),
    el('option', { value: 'page', text: 'ページ' }),
    el('option', { value: 'question', text: '問' }),
  ]);
  const rangeFrom = numberInput({ placeholder: '開始', min: '0' });
  const rangeTo = numberInput({ placeholder: '終了', min: '0' });
  const correct = numberInput({ placeholder: '正答', min: '0' });
  const attempted = numberInput({ placeholder: '解答', min: '0' });
  const focus = el('select', {}, [
    el('option', { value: '', text: '（未入力）' }),
    ...[1, 2, 3, 4, 5].map((value) =>
      el('option', { value: String(value), text: `${value}${value === 1 ? ' 散漫' : value === 5 ? ' 集中' : ''}` }),
    ),
  ]);
  const memo = el('input', { type: 'text', placeholder: 'メモ（任意）', value: state.memo || '' });
  const quotaStatus = el('select', {}, [
    el('option', { value: '', text: '変えない' }),
    el('option', { value: 'done', text: '完了' }),
    el('option', { value: 'partial', text: '一部' }),
    el('option', { value: 'skipped', text: 'スキップ' }),
  ]);

  const computeDuration = () => {
    try {
      const span = Math.floor((fromLocalInput(endedAt.value).getTime() - parseIso(state.startedAt).getTime()) / 1000);
      duration.textContent = formatHms(Math.max(0, Math.min(elapsed, span)));
    } catch {
      duration.textContent = '—';
    }
  };
  endedAt.addEventListener('change', computeDuration);
  computeDuration();

  const body = [
    isLong
      ? el('p', {
          class: 'banner banner-warn',
          text: '5時間を超えています。つけっぱなしだった場合は、終了時刻を直してください。',
        })
      : null,
    el('div', { class: 'row-between' }, [
      el('span', { class: 'dim', text: '勉強時間' }),
      duration,
    ]),
    field('終了時刻', endedAt),
    quota ? field(`ノルマ「${quota.title}」の状況`, quotaStatus) : null,
    el('div', { class: 'field' }, [
      el('label', { text: '範囲（任意）' }),
      el('div', { class: 'field-row' }, [rangeUnit, rangeFrom, rangeTo]),
    ]),
    el('div', { class: 'field' }, [
      el('label', { text: '正答 / 解答（任意）' }),
      el('div', { class: 'field-row' }, [correct, attempted]),
    ]),
    field('集中度（任意）', focus),
    field('メモ（任意）', memo),
  ];

  const collect = () => {
    const from = optionalInt(rangeFrom.value);
    const to = optionalInt(rangeTo.value);
    const unit = rangeUnit.value || null;
    const range = unit && from !== null && to !== null ? { unit, from, to } : null;
    if (range && range.from > range.to) return { error: '範囲の開始が終了より後になっています' };

    const correctValue = optionalInt(correct.value);
    const attemptedValue = optionalInt(attempted.value);
    if (correctValue !== null && attemptedValue !== null && correctValue > attemptedValue) {
      return { error: '正答数が解答数を超えています' };
    }

    let ended;
    try {
      ended = fromLocalInput(endedAt.value);
    } catch (error) {
      return { error: error.message };
    }
    const span = Math.floor((ended.getTime() - parseIso(state.startedAt).getTime()) / 1000);
    if (span < 0) return { error: '終了時刻が開始時刻より前になっています' };

    return {
      values: {
        endedAt: toIso(ended),
        activeSeconds: Math.max(0, Math.min(elapsed, span)),
        range,
        correct: correctValue,
        attempted: attemptedValue,
        focus: optionalInt(focus.value),
        memo: memo.value.trim(),
      },
      quotaStatus: quotaStatus.value || null,
    };
  };

  return openSheet({
    title: '計測を終える',
    body,
    actions: [
      { label: '戻る', value: null },
      {
        label: '保存',
        primary: true,
        onClick: () => {
          const result = collect();
          if (result.error) {
            toast(result.error, { error: true });
            return false;
          }
          return result;
        },
      },
    ],
  });
}
