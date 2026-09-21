// 日時の扱い。母艦と同じ規則で「学習日」と週を決める。
// 画面ロック中はJSが止まるので、経過時間は必ず時刻の差から計算すること。

export const DEFAULT_SETTINGS = { dayChangeHour: 4, weekStartsOn: 1 };

const pad = (value, length = 2) => String(value).padStart(length, '0');

/** ローカル時刻のISO 8601（オフセット付き）。転送にはこの形で書き出す。 */
export function toIso(date = new Date()) {
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  const abs = Math.abs(offset);
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  );
}

export function nowIso() {
  return toIso(new Date());
}

/** タイムゾーン付きのISO 8601だけを受け付ける。 */
export function parseIso(text) {
  if (typeof text !== 'string') throw new Error('日時が文字列ではありません');
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)$/.test(text)) {
    throw new Error(`日時の書式が違います: ${text}`);
  }
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) throw new Error(`日時として読めません: ${text}`);
  return date;
}

export function isIsoDateTime(text) {
  try {
    parseIso(text);
    return true;
  } catch {
    return false;
  }
}

export function isIsoDate(text) {
  return typeof text === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(text)
    && !Number.isNaN(new Date(`${text}T00:00:00`).getTime());
}

export function ymd(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** 日付変更時刻を考慮した学習日（2:00 の記録は dayChangeHour=4 なら前日）。 */
export function studyDate(date, dayChangeHour = DEFAULT_SETTINGS.dayChangeHour) {
  const shifted = new Date(date.getTime() - dayChangeHour * 3600 * 1000);
  return ymd(shifted);
}

export function todayStudyDate(dayChangeHour = DEFAULT_SETTINGS.dayChangeHour) {
  return studyDate(new Date(), dayChangeHour);
}

/** ISO-8601の曜日（1=月曜 … 7=日曜）。 */
export function isoWeekday(ymdText) {
  const day = new Date(`${ymdText}T00:00:00`).getDay();
  return day === 0 ? 7 : day;
}

export function weekStart(ymdText, weekStartsOn = DEFAULT_SETTINGS.weekStartsOn) {
  const delta = (isoWeekday(ymdText) - weekStartsOn + 7) % 7;
  const date = new Date(`${ymdText}T00:00:00`);
  date.setDate(date.getDate() - delta);
  return ymd(date);
}

export function addDays(ymdText, days) {
  const date = new Date(`${ymdText}T00:00:00`);
  date.setDate(date.getDate() + days);
  return ymd(date);
}

export function daysBetween(fromYmd, toYmd) {
  const from = new Date(`${fromYmd}T00:00:00`);
  const to = new Date(`${toYmd}T00:00:00`);
  return Math.round((to - from) / 86400000);
}

// --- 表示 -------------------------------------------------------------------

export function formatHm(seconds) {
  const value = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(value / 3600)}:${pad(Math.floor((value % 3600) / 60))}`;
}

export function formatHms(seconds) {
  const value = Math.max(0, Math.floor(seconds || 0));
  return [Math.floor(value / 3600), Math.floor((value % 3600) / 60), value % 60]
    .map((part) => pad(part))
    .join(':');
}

export function formatClock(isoText) {
  const date = parseIso(isoText);
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatDateTime(isoText) {
  const date = parseIso(isoText);
  return `${ymd(date)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 「3日前」のような相対表示。送信を促すときに使う。 */
export function daysAgo(isoText) {
  const date = parseIso(isoText);
  return Math.floor((Date.now() - date.getTime()) / 86400000);
}
