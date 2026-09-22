// レコードの読み書き。母艦とのやりとりに必要な形をそのまま持つ。

import * as db from './db.js';
import { DEFAULT_SETTINGS, nowIso, studyDate, todayStudyDate } from './clock.js';

export const RECORD_STORES = ['sessions', 'mistakes', 'reviewResults', 'quotaStatus'];
const CURRENT = 'current';

export const newId = () => {
  if (crypto.randomUUID) return crypto.randomUUID();
  // 古い環境向けの保険（UUID v4 の形をつくる）
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

// --- 端末 -------------------------------------------------------------------

export async function getDevice() {
  let device = await db.get('device', CURRENT);
  if (!device) {
    device = { id: CURRENT, deviceId: newId(), deviceName: '子機', onboarded: false };
    await db.put('device', device);
  }
  return device;
}

export async function updateDevice(values) {
  const device = await getDevice();
  const updated = { ...device, ...values };
  await db.put('device', updated);
  return updated;
}

// --- 受け取った下り ---------------------------------------------------------

export async function getInbound() {
  return (await db.get('inbound', CURRENT)) || null;
}

export async function setInbound(value) {
  await db.put('inbound', { ...value, id: CURRENT });
}

export async function getSettings() {
  const inbound = await getInbound();
  return { ...DEFAULT_SETTINGS, ...(inbound?.settings || {}) };
}

export async function getMasters() {
  const inbound = await getInbound();
  return inbound?.masters || null;
}

export async function getQuotas() {
  const inbound = await getInbound();
  return inbound?.quotas || [];
}

export async function getReviews() {
  const inbound = await getInbound();
  return inbound?.reviews || [];
}

/** 参照用データが無ければ「未分類」しか選べない（転送仕様書 A-4）。 */
export async function classificationOptions() {
  const masters = await getMasters();
  if (!masters) return { hasMasters: false, exams: [], materials: [], subjects: [] };
  return {
    hasMasters: true,
    exams: masters.exams || [],
    materials: masters.materials || [],
    subjects: masters.subjects || [],
  };
}

export async function labelsFor({ examId, materialId, subjectId }) {
  const masters = await getMasters();
  if (!masters) return { exam: null, material: null, subject: null };
  const find = (list, id) => (id ? (list || []).find((item) => item.id === id) : null);
  const subject = find(masters.subjects, subjectId);
  let subjectLabel = subject?.name || null;
  if (subject?.parentId) {
    const parent = find(masters.subjects, subject.parentId);
    if (parent) subjectLabel = `${parent.name} / ${subject.name}`;
  }
  return {
    exam: find(masters.exams, examId)?.name || null,
    material: find(masters.materials, materialId)?.name || null,
    subject: subjectLabel,
  };
}

// --- レコード ---------------------------------------------------------------

export async function listRecords(store) {
  return db.getAll(store);
}

export async function pendingRecords(store) {
  return (await db.getAll(store)).filter((record) => record.state !== 'acked');
}

export async function ackedRecords(store) {
  return (await db.getAll(store)).filter((record) => record.state === 'acked');
}

export async function allPending() {
  const result = {};
  for (const store of RECORD_STORES) result[store] = await pendingRecords(store);
  return result;
}

export async function pendingCount() {
  const pending = await allPending();
  return RECORD_STORES.reduce((total, store) => total + pending[store].length, 0);
}

/** 未取り込みの記録のうち、いちばん古いものの作成日時。 */
export async function oldestPendingCreatedAt() {
  const pending = await allPending();
  const stamps = RECORD_STORES.flatMap((store) =>
    pending[store].map((record) => record.createdAt || record.reviewedAt || record.updatedAt),
  ).filter(Boolean);
  return stamps.length ? stamps.sort()[0] : null;
}

function touch(record) {
  return { ...record, updatedAt: nowIso(), state: 'pending', ackedAt: null };
}

export async function putSession(session) {
  const record = touch({ entryMode: 'timer', deleted: false, ...session });
  record.unclassified = !record.examId;
  await db.put('sessions', record);
  return record;
}

export async function getSession(id) {
  return db.get('sessions', id);
}

/** 送ったことがあるか（取り消しを物理削除にするか deleted にするかの判断）。 */
export async function wasSent(id) {
  const outbox = await db.getAll('outbox');
  return outbox.some((entry) => (entry.includedIds || []).includes(id));
}

export async function removeSession(id) {
  const session = await getSession(id);
  if (!session) return 'missing';
  if (session.state === 'acked') return 'acked';
  if (await wasSent(id)) {
    await db.put('sessions', touch({ ...session, deleted: true }));
    return 'marked';
  }
  await db.remove('sessions', id);
  return 'removed';
}

export async function putMistake(mistake) {
  const record = touch({ deleted: false, memo: '', reason: null, ...mistake });
  await db.put('mistakes', record);
  return record;
}

export async function getMistake(id) {
  return db.get('mistakes', id);
}

/** 誤答の取り消し。送ったことが無ければ消し、送っていれば deleted にして母艦へ伝える。 */
export async function removeMistake(id) {
  const mistake = await getMistake(id);
  if (!mistake) return 'missing';
  if (mistake.state === 'acked') return 'acked';
  if (await wasSent(id)) {
    await db.put('mistakes', touch({ ...mistake, deleted: true }));
    return 'marked';
  }
  await db.remove('mistakes', id);
  return 'removed';
}

export async function putReviewResult(result) {
  // 復習結果は追記専用（転送仕様書 A-2）。updatedAt は持たない。
  const record = { ...result, state: 'pending', ackedAt: null };
  await db.put('reviewResults', record);
  return record;
}

/** 復習の結果を1件記録する。result は 'ok'（できた）か 'ng'（できなかった）。 */
export async function recordReview(mistakeId, result) {
  return putReviewResult({ id: newId(), mistakeId, result, reviewedAt: nowIso() });
}

/**
 * 押し間違いの取り消し。追記専用なので、まだ送っていない結果だけ消せる。
 * 戻り値: 'removed' / 'sent'（送信済みなので消せない） / 'missing'
 */
export async function removeReviewResult(id) {
  const record = await db.get('reviewResults', id);
  if (!record) return 'missing';
  if (record.state === 'acked' || (await wasSent(id))) return 'sent';
  await db.remove('reviewResults', id);
  return 'removed';
}

/**
 * いま表示すべき復習対象。未ackの回答がある問題は外す（転送仕様書 B-11：二重回答を防ぐ）。
 * 期限の古い順に並べる。
 */
export async function visibleReviews() {
  const [inbound, results] = await Promise.all([getInbound(), db.getAll('reviewResults')]);
  const reviews = inbound?.reviews || [];
  const since = inbound?.reviewsReceivedAt || null;
  // 未ackの回答がある問題（B-11）に加え、この一覧を受け取った後に答えた問題も外す。
  // 下りに reviews が無いと前回の一覧が残る（B-1）ので、ack済みになった回答で問題が戻ってこないようにする。
  const answered = new Set(
    results
      .filter((result) => result.state !== 'acked' || (since && result.reviewedAt >= since))
      .map((result) => result.mistakeId),
  );
  return reviews
    .filter((review) => !answered.has(review.mistakeId))
    .sort((a, b) => (a.dueDate === b.dueDate ? 0 : a.dueDate < b.dueDate ? -1 : 1));
}

export async function setQuotaStatus(quotaId, status) {
  const existing = (await db.getAllByIndex('quotaStatus', 'quotaId', quotaId))[0];
  const record = touch({
    id: existing?.id || newId(),
    createdAt: existing?.createdAt || nowIso(),
    quotaId,
    status,
  });
  await db.put('quotaStatus', record);
  return record;
}

export async function quotaStatusMap() {
  const all = await db.getAll('quotaStatus');
  const map = {};
  for (const record of all) {
    const current = map[record.quotaId];
    if (!current || record.updatedAt > current.updatedAt) map[record.quotaId] = record;
  }
  return map;
}

// --- 集計（画面用） ---------------------------------------------------------

export async function secondsForQuota(quotaId) {
  const sessions = await db.getAll('sessions');
  return sessions
    .filter((session) => session.quotaId === quotaId && !session.deleted)
    .reduce((total, session) => total + (session.activeSeconds || 0), 0);
}

export async function secondsForDay(ymdText, dayChangeHour) {
  const sessions = await db.getAll('sessions');
  return sessions
    .filter((session) => !session.deleted && studyDate(new Date(session.startedAt), dayChangeHour) === ymdText)
    .reduce((total, session) => total + (session.activeSeconds || 0), 0);
}

/**
 * 今週の合計。母艦から受け取った値に「未ack」の記録を足す（転送仕様書 A-5）。
 * 「未送信」ではないので、送ったが取り込まれていない分も含まれる。
 */
export async function weekSeconds() {
  const inbound = await getInbound();
  const base = inbound?.summary?.weekTotalSeconds || 0;
  const sessions = await db.getAll('sessions');
  const local = sessions
    .filter((session) => session.state !== 'acked' && !session.deleted)
    .reduce((total, session) => total + (session.activeSeconds || 0), 0);
  return { total: base + local, base, local, goal: inbound?.summary?.weekGoalSeconds || 0 };
}

export async function todaySeconds() {
  const settings = await getSettings();
  return secondsForDay(todayStudyDate(settings.dayChangeHour), settings.dayChangeHour);
}

// --- メタ情報 ---------------------------------------------------------------

export async function getMeta(key, fallback = null) {
  const record = await db.get('meta', key);
  return record ? record.value : fallback;
}

export async function setMeta(key, value) {
  await db.put('meta', { key, value });
}
