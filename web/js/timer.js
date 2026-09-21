// 計測。経過時間は必ず時刻の差から計算する（画面ロック中はJSが止まるため）。

import * as db from './db.js';
import { nowIso, parseIso } from './clock.js';
import * as store from './store.js';

const CURRENT = 'current';
export const LONG_SESSION_SECONDS = 5 * 3600;

export async function getState() {
  return (await db.get('timer', CURRENT)) || null;
}

async function save(state) {
  await db.put('timer', { ...state, id: CURRENT });
  return state;
}

export function elapsedSeconds(state, now = new Date()) {
  if (!state) return 0;
  let total = state.accumulatedSeconds || 0;
  if (state.running && state.resumedAt) {
    total += Math.max(0, Math.floor((now.getTime() - parseIso(state.resumedAt).getTime()) / 1000));
  }
  return total;
}

export function isLong(state, now = new Date()) {
  return elapsedSeconds(state, now) >= LONG_SESSION_SECONDS;
}

export async function start(selection = {}) {
  if (await getState()) throw new Error('すでに計測中です');
  const at = nowIso();
  return save({
    startedAt: at,
    resumedAt: at,
    accumulatedSeconds: 0,
    running: true,
    quotaId: selection.quotaId || null,
    examId: selection.examId || null,
    materialId: selection.materialId || null,
    subjectId: selection.subjectId || null,
    memo: selection.memo || '',
  });
}

export async function pause() {
  const state = await getState();
  if (!state || !state.running) return state;
  return save({
    ...state,
    accumulatedSeconds: elapsedSeconds(state),
    resumedAt: null,
    running: false,
  });
}

export async function resume() {
  const state = await getState();
  if (!state || state.running) return state;
  return save({ ...state, resumedAt: nowIso(), running: true });
}

export async function updateSelection(selection) {
  const state = await getState();
  if (!state) return null;
  return save({ ...state, ...selection });
}

export async function discard() {
  await db.remove('timer', CURRENT);
}

/**
 * 計測を終えて記録にする。
 * 終了時刻を手で直した場合は、その長さに収まるよう勉強時間を丸める。
 */
export async function finish(values = {}) {
  const state = await getState();
  if (!state) throw new Error('計測していません');

  const endedAt = values.endedAt || nowIso();
  const span = Math.max(
    0,
    Math.floor((parseIso(endedAt).getTime() - parseIso(state.startedAt).getTime()) / 1000),
  );
  const activeSeconds = Math.min(
    values.activeSeconds ?? elapsedSeconds(state),
    span,
  );

  const session = await store.putSession({
    id: store.newId(),
    createdAt: nowIso(),
    quotaId: state.quotaId,
    examId: values.examId !== undefined ? values.examId : state.examId,
    materialId: values.materialId !== undefined ? values.materialId : state.materialId,
    subjectId: values.subjectId !== undefined ? values.subjectId : state.subjectId,
    startedAt: state.startedAt,
    endedAt,
    activeSeconds,
    range: values.range || null,
    correct: values.correct ?? null,
    attempted: values.attempted ?? null,
    focus: values.focus ?? null,
    memo: values.memo ?? state.memo ?? '',
    entryMode: 'timer',
  });

  await discard();
  return session;
}
