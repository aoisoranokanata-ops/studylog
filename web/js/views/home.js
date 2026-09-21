// 今日（ホーム）。カウントダウン、ノルマ、今週、復習件数、送信の催促。

import { formatDateTime, formatHm, todayStudyDate } from '../clock.js';
import * as store from '../store.js';
import * as transfer from '../transfer.js';
import { card, el, toast } from './components.js';

const STATUS_LABEL = { none: '未着手', done: '完了', partial: '一部', skipped: 'スキップ' };

export async function render(root, app) {
  const [inbound, settings, status, week, today, statusMap] = await Promise.all([
    store.getInbound(),
    store.getSettings(),
    transfer.status(),
    store.weekSeconds(),
    store.todaySeconds(),
    store.quotaStatusMap(),
  ]);

  if (!inbound) {
    root.append(
      card('はじめに', [
        el('p', { text: 'まだ母艦からノルマを受け取っていません。' }),
        el('p', { class: 'dim small', text: '「転送」タブで、ファイルまたは文字列を受け取ってください。' }),
        el('button', {
          type: 'button',
          class: 'btn btn-primary btn-block',
          text: '転送へ',
          onClick: () => app.go('transfer'),
        }),
      ]),
    );
    return;
  }

  const ymd = todayStudyDate(settings.dayChangeHour);

  // --- 警告 ---
  if (status.shouldSend) {
    root.append(
      el('div', { class: 'banner banner-warn' }, [
        el('span', { text: `未送信の記録が${status.pending}件（最も古いもので${status.oldestDays}日前）` }),
        el('button', { type: 'button', class: 'btn btn-small', text: '送る', onClick: () => app.go('transfer') }),
      ]),
    );
  }
  if (inbound.targetDate !== ymd) {
    root.append(
      el('div', { class: 'banner banner-warn', text: `受け取ったノルマは ${inbound.targetDate} のものです（今日は ${ymd}）` }),
    );
  }

  // --- カウントダウン ---
  const countdowns = inbound.summary?.countdowns || [];
  if (countdowns.length) {
    root.append(
      card(
        '試験日まで',
        countdowns.map((item) =>
          el('div', { class: 'row-between' }, [
            el('span', { class: 'truncate', text: item.name }),
            el('span', { class: 'strong', text: `あと ${item.daysLeft} 日（${item.examDate}）` }),
          ]),
        ),
      ),
    );
  }

  // --- 今日のノルマ ---
  const quotas = inbound.quotas || [];
  const quotaNodes = [];
  for (const quota of quotas) {
    const actual = await store.secondsForQuota(quota.id);
    const state = statusMap[quota.id]?.status || 'none';
    const ratio = quota.targetSeconds ? Math.min(1, actual / quota.targetSeconds) : 0;
    quotaNodes.push(
      el(
        'button',
        {
          type: 'button',
          class: 'quota',
          dataset: { status: state },
          onClick: () => app.startQuota(quota),
        },
        [
          el('div', { class: 'row-between' }, [
            el('span', { class: 'strong truncate grow', text: quota.title }),
            el('span', { class: 'badge', text: STATUS_LABEL[state] || state }),
          ]),
          el('div', { class: 'dim small', text: [quota.labels?.exam, quota.labels?.material, quota.labels?.subject].filter(Boolean).join('　') }),
          el('div', { class: 'bar' }, [el('span', { style: `width:${Math.round(ratio * 100)}%` })]),
          el('div', { class: 'dim small', text: `実績 ${formatHm(actual)} / 目標 ${formatHm(quota.targetSeconds)}` }),
        ],
      ),
    );
  }
  root.append(
    card(
      `今日のノルマ（${inbound.targetDate}）`,
      quotaNodes.length ? quotaNodes : [el('p', { class: 'empty', text: 'ノルマはありません。自由記録で計測できます。' })],
    ),
  );

  // --- 今週・今日 ---
  const goalText = week.goal ? ` / 目標 ${formatHm(week.goal)}` : '';
  root.append(
    card('勉強時間', [
      el('div', { class: 'row-between' }, [el('span', { text: '今日' }), el('span', { class: 'strong', text: formatHm(today) })]),
      el('div', { class: 'row-between' }, [
        el('span', { text: '今週' }),
        el('span', { class: 'strong', text: `${formatHm(week.total)}${goalText}` }),
      ]),
      week.local
        ? el('div', { class: 'dim small', text: `うち未取り込み ${formatHm(week.local)}（母艦にはまだ入っていません）` })
        : null,
    ]),
  );

  // --- 復習・送信状況 ---
  const reviews = inbound.reviews || [];
  root.append(
    card('状況', [
      el('div', { class: 'row-between' }, [
        el('span', { text: '今日の復習対象' }),
        el('span', { class: 'strong', text: `${reviews.length}件` }),
      ]),
      reviews.length ? el('div', { class: 'dim small', text: '復習はフェーズ3で記録できるようになります。' }) : null,
      el('div', { class: 'row-between' }, [
        el('span', { text: '未取り込みの記録' }),
        el('span', { class: 'strong', text: `${status.pending}件` }),
      ]),
      el('div', {
        class: 'dim small',
        text: status.lastSentAt ? `最後に送ったのは ${formatDateTime(status.lastSentAt)}` : 'まだ一度も送っていません',
      }),
      el('div', { class: 'dim small', text: `受け取ったのは ${formatDateTime(inbound.receivedAt)}（${inbound.variant}）` }),
    ]),
  );

  if (!inbound.masters) {
    root.append(
      el('div', {
        class: 'banner banner-info',
        text: '参照用データが未受信です。自由記録は「未分類」になります。一度ファイルで受け取ると分類できます。',
      }),
    );
  }
}

export function quotaStatusLabel(status) {
  return STATUS_LABEL[status] || status;
}

export { toast };
