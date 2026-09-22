// 計測画面。

import { formatClock, formatHms } from '../clock.js';
import * as store from '../store.js';
import * as timer from '../timer.js';
import { card, classificationPicker, confirmSheet, el, toast } from './components.js';
import { openFinishSheet } from './finish-sheet.js';
import { openMistakeSheet } from './mistake-sheet.js';

let tick = null;

export function stopTicking() {
  if (tick) {
    clearInterval(tick);
    tick = null;
  }
}

export async function render(root, app) {
  stopTicking();
  const [state, inbound, options] = await Promise.all([
    timer.getState(),
    store.getInbound(),
    store.classificationOptions(),
  ]);

  const display = el('div', { class: 'timer-big', text: formatHms(timer.elapsedSeconds(state)) });
  const statusLine = el('div', { class: 'dim', style: 'text-align:center' });
  root.append(display, statusLine);

  const quota = state?.quotaId ? (inbound?.quotas || []).find((item) => item.id === state.quotaId) : null;

  if (state) {
    root.append(
      card('計測中の内容', [
        el('div', { class: 'strong', text: quota ? quota.title : '自由記録' }),
        el('div', {
          class: 'dim small',
          text: (await describe(state)) || '未分類',
        }),
      ]),
    );
  } else {
    const picker = classificationPicker(options, await lastUsed());
    const quotaSelect = el('select', {}, [
      el('option', { value: '', text: '自由記録（ノルマに紐づけない）' }),
      ...(inbound?.quotas || []).map((item) => el('option', { value: item.id, text: item.title })),
    ]);
    const memo = el('input', { type: 'text', placeholder: 'メモ（任意）' });

    root.append(
      card('何を勉強する？', [
        el('div', { class: 'field' }, [el('label', { text: 'ノルマ' }), quotaSelect]),
        picker.element,
        memo,
      ]),
    );

    root.append(
      el('button', {
        type: 'button',
        class: 'btn btn-primary btn-block',
        text: '開始',
        onClick: async () => {
          const values = picker.values();
          const quotaId = quotaSelect.value || null;
          const chosen = (inbound?.quotas || []).find((item) => item.id === quotaId);
          await timer.start({
            quotaId,
            examId: values.examId || chosen?.examId || null,
            materialId: values.materialId || chosen?.materialId || null,
            subjectId: values.subjectId || chosen?.subjectId || null,
            memo: memo.value.trim(),
          });
          await store.setMeta('lastUsed', values);
          app.refresh();
        },
      }),
    );
  }

  if (state) {
    root.append(
      el('div', { class: 'btn-row' }, [
        el('button', {
          type: 'button',
          class: 'btn',
          text: state.running ? '一時停止' : '再開',
          onClick: async () => {
            await (state.running ? timer.pause() : timer.resume());
            app.refresh();
          },
        }),
        el('button', {
          type: 'button',
          class: 'btn btn-primary',
          text: '終了',
          onClick: () => finish(app, state, quota),
        }),
      ]),
      el('button', {
        type: 'button',
        class: 'btn btn-danger btn-block',
        text: '取り消す（保存しない）',
        onClick: async () => {
          if (await confirmSheet('計測を取り消す', '保存せずに捨てます。よろしいですか？', { okText: '取り消す', danger: true })) {
            await timer.discard();
            app.refresh();
          }
        },
      }),
    );
  }

  const wakeLockEnabled = await store.getMeta('wakeLock', false);
  if (state?.running && wakeLockEnabled) app.requestWakeLock();

  const update = () => {
    display.textContent = formatHms(timer.elapsedSeconds(state));
    statusLine.textContent = !state
      ? '停止中'
      : state.running
        ? `計測中（${formatClock(state.startedAt)} 開始）`
        : '一時停止中';
  };
  update();
  if (state?.running) tick = setInterval(update, 1000);
}

async function describe(state) {
  const labels = await store.labelsFor(state);
  return [labels.exam, labels.material, labels.subject].filter(Boolean).join('　');
}

async function lastUsed() {
  return (await store.getMeta('lastUsed', {})) || {};
}

async function finish(app, state, quota) {
  const elapsed = timer.elapsedSeconds(state);
  const result = await openFinishSheet({ state, elapsed, quota });
  if (!result) return;

  const session = await timer.finish(result.values);
  if (result.quotaStatus && state.quotaId) {
    await store.setQuotaStatus(state.quotaId, result.quotaStatus);
  }
  app.releaseWakeLock();
  toast('記録しました');
  // 先にホームへ戻す（誤答シートの後ろに「計測中」の画面が残って見えないように）
  await app.go('home');

  if (result.addMistakes) {
    const count = await openMistakeSheet({
      base: {
        sessionId: session.id,
        examId: session.examId,
        materialId: session.materialId,
        subjectId: session.subjectId,
      },
    });
    if (count) await app.refresh();
  }
}
