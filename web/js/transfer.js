// 母艦とのやりとり（転送仕様書 第3〜6章）。

import * as db from './db.js';
import { nowIso, parseIso, toIso } from './clock.js';
import { decode, looksLikePackageText, SCHEMA_VERSION } from './codec.js';
import * as store from './store.js';
import { NeedsUpdateError, validateDown, validateUp } from './validate.js';

export const KEEP_ACKED_DAYS = 7;
export const NUDGE_AFTER_DAYS = 3;
const KEEP_OUTBOX_DAYS = 60;

export class TransferError extends Error {
  constructor(message, details = []) {
    super(message);
    this.details = details;
  }
}

const pad = (value) => String(value).padStart(2, '0');

export function sanitizeDeviceName(name) {
  const cleaned = String(name || '')
    .trim()
    .replace(/[^0-9A-Za-z぀-ゟ゠-ヿ㐀-鿿ｦ-ﾟ_-]/g, '_')
    .slice(0, 20);
  return cleaned || 'device';
}

export function upFilename(pkg) {
  const date = parseIso(pkg.createdAt);
  const stamp =
    `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}` +
    `-${pad(date.getHours())}${pad(date.getMinutes())}`;
  return `studylog-up-${sanitizeDeviceName(pkg.deviceName)}-${stamp}-${pkg.packageId.slice(0, 8)}.json`;
}

// --- 下りを受け取る ---------------------------------------------------------

/**
 * 下りパッケージを取り込む。
 * full は masters ごと置き換え、lite は masters をそのまま残す。
 * reviews / summary は「キーが無ければ維持、null や [] ならクリア」（仕様書 B-1）。
 */
export async function receiveDown(pkg) {
  const result = validateDown(pkg);
  if (!result.ok) {
    throw new TransferError('受け取れませんでした（内容が仕様に合いません）', result.errors);
  }

  const previous = (await store.getInbound()) || {};
  const next = {
    packageId: pkg.packageId,
    hubId: pkg.hubId,
    targetDate: pkg.targetDate,
    variant: pkg.variant,
    receivedAt: nowIso(),
    settings: pkg.settings,
    quotas: pkg.quotas,
    masters: pkg.variant === 'full' ? pkg.masters : previous.masters || null,
    reviews: 'reviews' in pkg ? pkg.reviews || [] : previous.reviews || [],
    // 復習一覧を受け取った時刻。これより後に答えた問題は、ackの後も一覧に戻さない
    reviewsReceivedAt: 'reviews' in pkg ? nowIso() : previous.reviewsReceivedAt || previous.receivedAt || null,
    summary: 'summary' in pkg ? pkg.summary || null : previous.summary || null,
  };
  await store.setInbound(next);

  const acked = await applyAcks(pkg.acks || []);
  const deleted = await purgeExpired();

  return {
    quotas: next.quotas.length,
    reviews: (next.reviews || []).length,
    acked,
    deleted,
    variant: pkg.variant,
    targetDate: pkg.targetDate,
    hasMasters: Boolean(next.masters),
  };
}

export async function receiveText(text) {
  if (!looksLikePackageText(text)) {
    throw new TransferError('`SL1:` で始まる文字列を貼り付けてください');
  }
  return receiveDown(await decode(text));
}

export async function receiveFile(file) {
  const text = await file.text();
  if (looksLikePackageText(text)) return receiveText(text);
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new TransferError('JSONとして読めません');
  }
  return receiveDown(parsed);
}

// --- 取り込み済み通知（acks） -----------------------------------------------

/**
 * acks を処理する（仕様書 第5章）。
 * 送信時刻より後に編集された記録は、未取り込みのまま残す。
 * 同じ記録が複数のパッケージに入っている場合は、いずれかで条件を満たせば取り込み済み。
 * 復習結果は編集できないので、ackされた時点で無条件に取り込み済みとする（A-2）。
 */
export async function applyAcks(acks) {
  if (!acks.length) return 0;
  const outbox = await db.getAll('outbox');
  const sentAtById = new Map();
  for (const entry of outbox) {
    if (!acks.includes(entry.packageId)) continue;
    for (const id of entry.includedIds || []) {
      const current = sentAtById.get(id);
      if (!current || entry.sentAt > current) sentAtById.set(id, entry.sentAt);
    }
  }
  if (!sentAtById.size) return 0;

  const ackedAt = nowIso();
  let count = 0;
  for (const name of store.RECORD_STORES) {
    const updates = [];
    for (const record of await db.getAll(name)) {
      if (record.state === 'acked') continue;
      const sentAt = sentAtById.get(record.id);
      if (!sentAt) continue;
      const editedAfterSend = name !== 'reviewResults' && record.updatedAt && record.updatedAt > sentAt;
      if (editedAfterSend) continue;
      updates.push({ ...record, state: 'acked', ackedAt });
    }
    if (updates.length) {
      await db.putMany(name, updates);
      count += updates.length;
    }
  }
  return count;
}

/** 取り込み済みから7日たった記録を消す。未取り込みは何日たっても消さない。 */
export async function purgeExpired(now = new Date()) {
  const limit = toIso(new Date(now.getTime() - KEEP_ACKED_DAYS * 86400000));
  let deleted = 0;
  for (const name of store.RECORD_STORES) {
    const expired = (await db.getAll(name))
      .filter((record) => record.state === 'acked' && record.ackedAt && record.ackedAt < limit)
      .map((record) => record.id);
    if (expired.length) {
      await db.removeMany(name, expired);
      deleted += expired.length;
    }
  }

  const outboxLimit = toIso(new Date(now.getTime() - KEEP_OUTBOX_DAYS * 86400000));
  const oldEntries = (await db.getAll('outbox'))
    .filter((entry) => entry.sentAt < outboxLimit)
    .map((entry) => entry.packageId);
  if (oldEntries.length) await db.removeMany('outbox', oldEntries);

  return deleted;
}

// --- 上りを作って送る -------------------------------------------------------

const stripInternal = ({ state, ackedAt, ...rest }) => rest;

/** 未取り込みの記録をすべて入れた上りパッケージを作る（累積送信）。 */
export async function buildUpPackage() {
  const device = await store.getDevice();
  const inbound = await store.getInbound();
  const pending = await store.allPending();

  const records = {
    sessions: pending.sessions.map(stripInternal),
    mistakes: pending.mistakes.map(stripInternal),
    reviewResults: pending.reviewResults.map(stripInternal),
    quotaStatus: pending.quotaStatus.map(stripInternal),
  };
  const includedIds = Object.values(records).flatMap((list) => list.map((record) => record.id));

  const pkg = {
    format: 'studylog-transfer',
    kind: 'up',
    schemaVersion: SCHEMA_VERSION,
    packageId: store.newId(),
    createdAt: nowIso(),
    deviceId: device.deviceId,
    deviceName: device.deviceName,
    basedOnPackageId: inbound?.packageId || null,
    records,
    includedIds,
  };

  const check = validateUp(pkg);
  if (!check.ok) {
    throw new TransferError('送るデータに問題が見つかりました', check.errors);
  }
  return pkg;
}

async function saveOutbox(pkg) {
  await db.put('outbox', {
    packageId: pkg.packageId,
    includedIds: pkg.includedIds,
    sentAt: nowIso(),
    deviceName: pkg.deviceName,
    count: pkg.includedIds.length,
  });
}

/**
 * 上りパッケージを共有またはダウンロードする。
 * 共有シートに対応していれば Googleドライブの StudyLog/inbox/ へ保存してもらう。
 */
export async function sendUp() {
  const pkg = await buildUpPackage();
  if (!pkg.includedIds.length) {
    throw new TransferError('送る記録がありません');
  }

  const filename = upFilename(pkg);
  const text = JSON.stringify(pkg, null, 2);
  const file = new File([text], filename, { type: 'application/json' });

  let shared = false;
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: filename });
      shared = true;
    } catch (error) {
      if (error?.name === 'AbortError') {
        throw new TransferError('共有をやめました（送信していません）');
      }
      shared = false; // 共有できない環境だったので、ダウンロードに切り替える
    }
  }

  if (!shared) {
    const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  await saveOutbox(pkg);
  return { package: pkg, filename, shared, count: pkg.includedIds.length };
}

// --- 状態 -------------------------------------------------------------------

export async function lastSent() {
  const outbox = await db.getAll('outbox');
  if (!outbox.length) return null;
  return outbox.sort((a, b) => (a.sentAt < b.sentAt ? 1 : -1))[0];
}

export async function status() {
  const [pending, oldest, last, inbound] = await Promise.all([
    store.pendingCount(),
    store.oldestPendingCreatedAt(),
    lastSent(),
    store.getInbound(),
  ]);
  const oldestDays = oldest ? Math.floor((Date.now() - parseIso(oldest).getTime()) / 86400000) : 0;
  return {
    pending,
    oldest,
    oldestDays,
    shouldSend: pending > 0 && oldestDays >= NUDGE_AFTER_DAYS,
    lastSentAt: last?.sentAt || null,
    inbound,
  };
}

export { NeedsUpdateError };
