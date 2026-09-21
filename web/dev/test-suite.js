// 子機の自動テスト。pytest が使えないので、ブラウザで走らせる。
// 仕様書のサンプルをそのまま受け入れ条件として使う。

import * as clock from '../js/clock.js';
import * as codec from '../js/codec.js';
import * as db from '../js/db.js';
import * as store from '../js/store.js';
import * as timer from '../js/timer.js';
import * as transfer from '../js/transfer.js';
import { NeedsUpdateError, validateDown, validateUp } from '../js/validate.js';

const EXAMPLES = '../../spec/examples/';
const results = [];
let currentGroup = '';

function group(name) {
  currentGroup = name;
}

async function test(name, fn) {
  try {
    await fn();
    results.push({ group: currentGroup, name, ok: true });
  } catch (error) {
    results.push({ group: currentGroup, name, ok: false, message: error.message });
    console.error(name, error);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message || '条件を満たしませんでした');
}

function equal(actual, expected, message) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) throw new Error(`${message || ''} 期待 ${b} / 実際 ${a}`);
}

async function example(name) {
  const response = await fetch(EXAMPLES + name);
  if (!response.ok) throw new Error(`${name} を読めません（studylog/ をルートに配信してください）`);
  return response.json();
}

async function reset() {
  await db.wipe();
}

/** テスト用に「送信済み」の状態を作る。 */
async function pretendSent(pkg, sentAt) {
  await db.put('outbox', {
    packageId: pkg.packageId,
    includedIds: pkg.includedIds,
    sentAt: sentAt || clock.nowIso(),
    count: pkg.includedIds.length,
  });
}

function iso(offsetMs) {
  return clock.toIso(new Date(Date.now() + offsetMs));
}

async function makeSession(overrides = {}) {
  return store.putSession({
    id: store.newId(),
    createdAt: clock.nowIso(),
    startedAt: iso(-3600 * 1000),
    endedAt: clock.nowIso(),
    activeSeconds: 1800,
    examId: null,
    materialId: null,
    subjectId: null,
    quotaId: null,
    range: null,
    correct: null,
    attempted: null,
    focus: null,
    memo: 'テスト',
    entryMode: 'manual',
    ...overrides,
  });
}

// --- 日時 -------------------------------------------------------------------

group('日時と学習日');

await test('深夜2時は前日の学習日になる', () => {
  const date = new Date(2026, 8, 21, 2, 0, 0); // 2026-09-21 02:00 ローカル
  equal(clock.studyDate(date, 4), '2026-09-20');
  equal(clock.studyDate(date, 0), '2026-09-21');
});

await test('日付変更時刻ちょうどは当日', () => {
  equal(clock.studyDate(new Date(2026, 8, 20, 4, 0, 0), 4), '2026-09-20');
});

await test('週の開始（1=月曜 / 7=日曜）', () => {
  equal(clock.weekStart('2026-09-20', 1), '2026-09-14');
  equal(clock.weekStart('2026-09-20', 7), '2026-09-20');
  equal(clock.weekStart('2026-09-19', 7), '2026-09-13');
});

await test('タイムゾーンの無い日時は拒否する', () => {
  let failed = false;
  try {
    clock.parseIso('2026-09-20T14:30:00');
  } catch {
    failed = true;
  }
  assert(failed, '拒否されませんでした');
});

await test('書き出す日時はオフセット付き', () => {
  assert(/[+-]\d{2}:\d{2}$/.test(clock.nowIso()), clock.nowIso());
});

await test('時間の表示', () => {
  equal(clock.formatHm(5400), '1:30');
  equal(clock.formatHms(3661), '01:01:01');
});

// --- 文字列（SL1:） ---------------------------------------------------------

group('QR・貼り付け文字列');

await test('SL1: の文字列を展開できる', async () => {
  const pkg = await example('down-02-lite-valid.json');
  const json = JSON.stringify(pkg);
  const compressed = new Blob([new TextEncoder().encode(json)])
    .stream()
    .pipeThrough(new CompressionStream('deflate-raw'));
  const bytes = new Uint8Array(await new Response(compressed).arrayBuffer());
  let binary = '';
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  const base64url = btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const decoded = await codec.decode(`SL1:${base64url}`);
  equal(decoded.packageId, pkg.packageId);
});

await test('SL2: は更新を促す', async () => {
  let message = '';
  try {
    await codec.decode('SL2:abcd');
  } catch (error) {
    message = error.message;
  }
  assert(message.includes('更新が必要'), message);
});

await test('壊れた文字列は拒否する', async () => {
  for (const text of ['ただの文字列', 'SL1:', 'SL1:!!!!']) {
    let failed = false;
    try {
      await codec.decode(text);
    } catch {
      failed = true;
    }
    assert(failed, `${text} が通ってしまいました`);
  }
});

// --- 検証 -------------------------------------------------------------------

group('仕様書サンプルの検証');

for (const name of ['down-01-full-valid.json', 'down-02-lite-valid.json', 'down-03-acks-valid.json']) {
  await test(`${name} を受け入れる`, async () => {
    const result = validateDown(await example(name));
    assert(result.ok, result.errors.join(' / '));
  });
}

await test('invalid-down-01（新しいschemaVersion）は更新を促す', async () => {
  let caught = null;
  try {
    validateDown(await example('invalid-down-01-future-version.json'));
  } catch (error) {
    caught = error;
  }
  assert(caught instanceof NeedsUpdateError, '更新を促しませんでした');
});

for (const name of ['invalid-down-02-missing-required.json', 'invalid-down-03-bad-formats.json']) {
  await test(`${name} を拒否する`, async () => {
    const result = validateDown(await example(name));
    assert(!result.ok, '通ってしまいました');
    assert(result.errors.length > 0, '理由がありません');
  });
}

await test('上りサンプルも自分の検証を通る', async () => {
  const result = validateUp(await example('up-01-normal-valid.json'));
  assert(result.ok, result.errors.join(' / '));
});

await test('unclassified:false で examId が無い上りは拒否する', async () => {
  const result = validateUp(await example('invalid-up-02-unclassified-conflict.json'));
  assert(!result.ok, '通ってしまいました');
});

await test('includedIds の不一致を検出する', async () => {
  const result = validateUp(await example('invalid-up-03-app-level-checks.json'));
  assert(!result.ok, '通ってしまいました');
  assert(result.errors.join(' ').includes('includedIds'), result.errors.join(' / '));
});

// --- 受け取り ---------------------------------------------------------------

group('下りの受け取り');

await test('full を受け取ると masters とノルマが入る', async () => {
  await reset();
  const summary = await transfer.receiveDown(await example('down-01-full-valid.json'));
  equal(summary.quotas, 3);
  equal(summary.reviews, 2);
  const inbound = await store.getInbound();
  assert(inbound.masters, 'masters がありません');
  equal(inbound.quotas.length, 3);
});

await test('lite を受け取っても masters は残る', async () => {
  await reset();
  await transfer.receiveDown(await example('down-01-full-valid.json'));
  await transfer.receiveDown(await example('down-02-lite-valid.json'));
  const inbound = await store.getInbound();
  assert(inbound.masters, 'masters が消えました');
  equal(inbound.quotas.length, 2);
});

await test('reviews は null でクリア、summary はキーが無ければ維持', async () => {
  await reset();
  await transfer.receiveDown(await example('down-01-full-valid.json'));
  await transfer.receiveDown(await example('down-03-acks-valid.json'));
  const inbound = await store.getInbound();
  equal(inbound.reviews.length, 0);
  assert(inbound.summary, 'summary が消えました');
  equal(inbound.summary.weekTotalSeconds, 43200);
});

await test('未対応の形式は受け取らない', async () => {
  await reset();
  let caught = null;
  try {
    await transfer.receiveDown(await example('invalid-down-01-future-version.json'));
  } catch (error) {
    caught = error;
  }
  assert(caught instanceof NeedsUpdateError, '更新を促しませんでした');
});

await test('壊れたパッケージは理由つきで拒否する', async () => {
  await reset();
  let caught = null;
  try {
    await transfer.receiveDown(await example('invalid-down-02-missing-required.json'));
  } catch (error) {
    caught = error;
  }
  assert(caught, '拒否しませんでした');
  assert(caught.details.length > 0, '理由がありません');
});

// --- 上りの作成 -------------------------------------------------------------

group('上りの作成');

await test('未取り込みの記録をすべて含む', async () => {
  await reset();
  await transfer.receiveDown(await example('down-01-full-valid.json'));
  await makeSession({ memo: '1件目' });
  await makeSession({ memo: '2件目' });
  await store.setQuotaStatus('9c000001-0000-4000-8000-000000000001', 'done');

  const pkg = await transfer.buildUpPackage();
  equal(pkg.includedIds.length, 3);
  equal(pkg.records.sessions.length, 2);
  equal(pkg.records.quotaStatus.length, 1);
  equal(pkg.basedOnPackageId, 'd0000001-0000-4000-8000-000000000001');
  const check = validateUp(pkg);
  assert(check.ok, check.errors.join(' / '));
});

await test('内部の項目（state）は送らない', async () => {
  await reset();
  await makeSession();
  const pkg = await transfer.buildUpPackage();
  assert(!('state' in pkg.records.sessions[0]), 'state が混ざっています');
  assert(!('ackedAt' in pkg.records.sessions[0]), 'ackedAt が混ざっています');
});

await test('ファイル名は端末名をそのまま使わない', () => {
  equal(transfer.sanitizeDeviceName('iPhone 12/Pro'), 'iPhone_12_Pro');
  equal(transfer.sanitizeDeviceName(''), 'device');
  equal(transfer.sanitizeDeviceName('あ'.repeat(40)), 'あ'.repeat(20));
});

// --- 取り込み済み通知 -------------------------------------------------------

group('acks と削除');

await test('ackを受けた記録は取り込み済みになる', async () => {
  await reset();
  const session = await makeSession();
  const pkg = await transfer.buildUpPackage();
  await pretendSent(pkg, iso(1000));

  const acked = await transfer.applyAcks([pkg.packageId]);
  equal(acked, 1);
  const stored = await store.getSession(session.id);
  equal(stored.state, 'acked');
});

await test('送信後に編集した記録は未取り込みのまま', async () => {
  await reset();
  const session = await makeSession();
  const pkg = await transfer.buildUpPackage();
  await pretendSent(pkg, iso(-60 * 1000)); // 1分前に送った

  await store.putSession({ ...session, memo: '送信後に編集' }); // updatedAt が新しくなる
  const acked = await transfer.applyAcks([pkg.packageId]);
  equal(acked, 0);
  const stored = await store.getSession(session.id);
  equal(stored.state, 'pending');
});

await test('ackを受けなければ何日たっても消えない', async () => {
  await reset();
  const session = await makeSession({ createdAt: iso(-40 * 86400000) });
  await transfer.purgeExpired();
  assert(await store.getSession(session.id), '未取り込みの記録が消えました');
});

await test('取り込み済みは7日で消える', async () => {
  await reset();
  const session = await makeSession();
  const pkg = await transfer.buildUpPackage();
  await pretendSent(pkg, iso(1000));
  await transfer.applyAcks([pkg.packageId]);

  // 8日前にackされたことにする
  const stored = await store.getSession(session.id);
  await db.put('sessions', { ...stored, ackedAt: iso(-8 * 86400000) });

  const deleted = await transfer.purgeExpired();
  equal(deleted, 1);
  assert(!(await store.getSession(session.id)), '消えていません');
});

await test('復習結果は編集判定なしで取り込み済みになる', async () => {
  await reset();
  await store.putReviewResult({
    id: store.newId(),
    mistakeId: '7d000001-0000-4000-8000-000000000001',
    result: 'ok',
    reviewedAt: clock.nowIso(),
  });
  const pkg = await transfer.buildUpPackage();
  await pretendSent(pkg, iso(-60 * 1000));
  const acked = await transfer.applyAcks([pkg.packageId]);
  equal(acked, 1);
});

await test('ノルマが空になっても達成状況は残る', async () => {
  await reset();
  await transfer.receiveDown(await example('down-01-full-valid.json'));
  await store.setQuotaStatus('9c000005-0000-4000-8000-000000000005', 'partial');
  await transfer.receiveDown(await example('down-03-acks-valid.json')); // quotas: []

  const pending = await store.allPending();
  equal(pending.quotaStatus.length, 1);
  equal(pending.quotaStatus[0].status, 'partial');
});

// --- 計測 -------------------------------------------------------------------

group('計測');

await test('経過時間は時刻の差から計算する', async () => {
  await reset();
  await timer.start({});
  const state = await timer.getState();
  const later = new Date(clock.parseIso(state.startedAt).getTime() + 90 * 1000);
  equal(timer.elapsedSeconds(state, later), 90);
});

await test('一時停止中は進まない', async () => {
  await reset();
  await timer.start({});
  const started = await timer.getState();
  const paused = { ...started, accumulatedSeconds: 60, resumedAt: null, running: false };
  const later = new Date(Date.now() + 3600 * 1000);
  equal(timer.elapsedSeconds(paused, later), 60);
});

await test('再読み込みしても続きから計算できる', async () => {
  await reset();
  await timer.start({});
  const state = await timer.getState(); // IndexedDBから読み直している
  assert(state.running, '状態が残っていません');
  assert(state.startedAt, '開始時刻がありません');
});

await test('終了すると記録になり、計測状態は消える', async () => {
  await reset();
  await timer.start({ memo: 'テスト計測' });
  const state = await timer.getState();
  const endedAt = clock.toIso(new Date(clock.parseIso(state.startedAt).getTime() + 1800 * 1000));
  const session = await timer.finish({ endedAt, activeSeconds: 1800 });
  equal(session.activeSeconds, 1800);
  equal(session.entryMode, 'timer');
  assert(!(await timer.getState()), '計測状態が残っています');
});

await test('終了時刻を早めると勉強時間もその長さに収まる', async () => {
  await reset();
  await timer.start({});
  const state = await timer.getState();
  const endedAt = clock.toIso(new Date(clock.parseIso(state.startedAt).getTime() + 600 * 1000));
  const session = await timer.finish({ endedAt, activeSeconds: 99999 });
  equal(session.activeSeconds, 600);
});

// --- 集計 -------------------------------------------------------------------

group('集計');

await test('今週は母艦の値に未ackの分を足す（未送信ではない）', async () => {
  await reset();
  await transfer.receiveDown(await example('down-01-full-valid.json')); // weekTotalSeconds = 43200
  const session = await makeSession({ activeSeconds: 1800 });

  let week = await store.weekSeconds();
  equal(week.total, 43200 + 1800);

  // 送っただけ（未ack）では、まだ足したまま
  const pkg = await transfer.buildUpPackage();
  await pretendSent(pkg, iso(1000));
  week = await store.weekSeconds();
  equal(week.total, 43200 + 1800);

  // ackされたら母艦の値だけになる
  await transfer.applyAcks([pkg.packageId]);
  week = await store.weekSeconds();
  equal(week.total, 43200);
  assert(session.id, '');
});

await test('取り消した記録は時間に数えない', async () => {
  await reset();
  const session = await makeSession({ activeSeconds: 1800 });
  await pretendSent({ packageId: store.newId(), includedIds: [session.id] }, iso(-1000));
  await store.removeSession(session.id);
  const week = await store.weekSeconds();
  equal(week.local, 0);
});

await test('参照用データが無ければ未分類のみ', async () => {
  await reset();
  const options = await store.classificationOptions();
  equal(options.hasMasters, false);
  equal(options.exams.length, 0);
});

// --- 結果の表示 -------------------------------------------------------------

const passed = results.filter((item) => item.ok).length;
const failed = results.length - passed;
const summary = document.getElementById('summary');
summary.textContent = `${results.length}件中 ${passed}件成功 / ${failed}件失敗`;
summary.style.color = failed ? 'var(--danger)' : 'var(--ok)';

const container = document.getElementById('results');
let lastGroup = '';
for (const item of results) {
  if (item.group !== lastGroup) {
    lastGroup = item.group;
    const heading = document.createElement('div');
    heading.className = 'group';
    heading.textContent = item.group;
    container.append(heading);
  }
  const node = document.createElement('div');
  node.className = `case ${item.ok ? 'pass' : 'fail'}`;
  node.textContent = `${item.ok ? 'OK' : 'NG'}　${item.name}${item.message ? ` — ${item.message}` : ''}`;
  container.append(node);
}

await db.wipe();
window.__testResults = { total: results.length, passed, failed, results };
