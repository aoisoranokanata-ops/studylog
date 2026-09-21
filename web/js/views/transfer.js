// 転送：受け取る（ファイル・文字列）と送る。

import { formatDateTime } from '../clock.js';
import { supportsDecompression } from '../codec.js';
import * as store from '../store.js';
import * as transfer from '../transfer.js';
import { NeedsUpdateError } from '../validate.js';
import { card, el, openSheet, toast } from './components.js';

export async function render(root, app) {
  const [status, device] = await Promise.all([transfer.status(), store.getDevice()]);

  // --- 送る ---
  root.append(
    card('母艦へ送る', [
      el('div', { class: 'row-between' }, [
        el('span', { text: '未取り込みの記録' }),
        el('span', { class: 'strong', text: `${status.pending}件` }),
      ]),
      el('div', {
        class: 'dim small',
        text: status.lastSentAt ? `最後に送ったのは ${formatDateTime(status.lastSentAt)}` : 'まだ一度も送っていません',
      }),
      el('button', {
        type: 'button',
        class: 'btn btn-primary btn-block',
        text: '記録を送る',
        disabled: status.pending === 0,
        onClick: () => send(app),
      }),
      el('p', {
        class: 'dim small',
        text: '共有シートが出たら Googleドライブの StudyLog/inbox/ に保存してください。対応していない端末ではダウンロードになります。',
      }),
    ]),
  );

  // --- 受け取る ---
  const fileInput = el('input', {
    type: 'file',
    accept: '.json,application/json,text/plain',
    onChange: async (event) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (file) await receive(app, () => transfer.receiveFile(file));
    },
  });

  root.append(
    card('母艦から受け取る', [
      el('label', { text: 'ファイルを選ぶ' }),
      fileInput,
      el('button', {
        type: 'button',
        class: 'btn btn-block',
        text: '文字列を貼り付ける',
        onClick: () => paste(app),
      }),
      supportsDecompression()
        ? null
        : el('p', { class: 'dim small', text: 'このブラウザは文字列（SL1:）の展開に対応していません。ファイルで受け取ってください。' }),
      status.inbound
        ? el('div', { class: 'dim small', text: `最後に受け取ったのは ${formatDateTime(status.inbound.receivedAt)}（${status.inbound.targetDate}・${status.inbound.variant}）` })
        : el('div', { class: 'dim small', text: 'まだ受け取っていません' }),
    ]),
  );

  root.append(
    card('この子機', [
      el('div', { class: 'row-between' }, [el('span', { text: '表示名' }), el('span', { class: 'strong', text: device.deviceName })]),
      el('div', { class: 'dim small', text: `deviceId: ${device.deviceId.slice(0, 8)}…` }),
    ]),
  );
}

async function receive(app, action) {
  try {
    const summary = await action();
    const lines = [
      `ノルマ ${summary.quotas}件`,
      `復習 ${summary.reviews}件`,
      `取り込み済みになった記録 ${summary.acked}件`,
      summary.deleted ? `7日を過ぎた記録を${summary.deleted}件削除` : null,
      summary.hasMasters ? null : '参照用データは未受信（未分類のみ選べます）',
    ].filter(Boolean);
    await openSheet({
      title: `受け取りました（${summary.targetDate}）`,
      body: lines.map((line) => el('p', { class: 'small', text: line })),
      actions: [{ label: 'OK', value: true, primary: true }],
    });
    app.go('home');
  } catch (error) {
    await showError(error);
  }
}

async function paste(app) {
  const textarea = el('textarea', { placeholder: 'SL1:...' });
  const value = await openSheet({
    title: '文字列を貼り付ける',
    body: [textarea],
    actions: [
      { label: 'やめる', value: null },
      {
        label: '読み込む',
        primary: true,
        onClick: () => {
          if (!textarea.value.trim()) {
            toast('貼り付けてください', { error: true });
            return false;
          }
          return textarea.value;
        },
      },
    ],
  });
  if (value) await receive(app, () => transfer.receiveText(value));
}

async function send(app) {
  try {
    const result = await transfer.sendUp();
    toast(
      result.shared
        ? `${result.count}件を共有しました`
        : `${result.count}件を書き出しました（${result.filename}）`,
    );
    app.refresh();
  } catch (error) {
    await showError(error);
  }
}

async function showError(error) {
  const isUpdate = error instanceof NeedsUpdateError;
  await openSheet({
    title: isUpdate ? 'アプリの更新が必要です' : '受け取れませんでした',
    body: [
      el('p', { text: error.message }),
      error.details?.length ? el('pre', { class: 'errors', text: error.details.join('\n') }) : null,
    ],
    actions: [{ label: '閉じる', value: true, primary: true }],
  });
}
