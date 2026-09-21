// 転送パッケージの検証（転送仕様書 第2〜4章）。
//
// 母艦は jsonschema を使うが、子機はビルド工程なし・JS 100KB以下という制約があるため、
// 必須項目・型・列挙・書式を手書きで確かめる。必須の欠落や型違反があればパッケージ全体を拒否する。
// 知らない項目は無視する（前方互換）。

import { isIsoDate, isIsoDateTime } from './clock.js';
import { SCHEMA_VERSION } from './codec.js';

export class NeedsUpdateError extends Error {}

const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/;
const COLOR = /^#[0-9a-fA-F]{6}$/;
const RANGE_UNITS = ['page', 'question'];
const MATERIAL_TYPES = ['text', 'drill', 'past', 'lecture', 'other'];

const isObject = (value) => typeof value === 'object' && value !== null && !Array.isArray(value);
const isUuid = (value) => typeof value === 'string' && UUID.test(value);
const isInt = (value) => Number.isInteger(value);
const isText = (value) => typeof value === 'string' && value.trim() !== '';
const isNullable = (value, check) => value === null || value === undefined || check(value);

class Checker {
  constructor() {
    this.errors = [];
  }

  add(path, message) {
    this.errors.push(`${path}: ${message}`);
  }

  require(object, path, key, check, description) {
    const value = object?.[key];
    if (value === undefined) {
      this.add(`${path}${key}`, '必須の項目がありません');
      return false;
    }
    if (!check(value)) {
      this.add(`${path}${key}`, description);
      return false;
    }
    return true;
  }

  optional(object, path, key, check, description) {
    const value = object?.[key];
    if (value === undefined || value === null) return true;
    if (!check(value)) {
      this.add(`${path}${key}`, description);
      return false;
    }
    return true;
  }
}

/** 形式・種類・バージョンを先に確かめる（新しすぎるものは更新を促す）。 */
export function checkHeader(pkg, kind) {
  if (!isObject(pkg)) throw new Error('JSONの形が違います（オブジェクトではありません）');
  if (pkg.format !== 'studylog-transfer') throw new Error('StudyLogの転送ファイルではありません');
  if (pkg.kind !== kind) throw new Error(`種類が違います（${kind} を期待しましたが ${pkg.kind} でした）`);
  if (!isInt(pkg.schemaVersion)) throw new Error('schemaVersion がありません');
  if (pkg.schemaVersion > SCHEMA_VERSION) {
    throw new NeedsUpdateError(
      `このファイルは新しい形式です（schemaVersion ${pkg.schemaVersion}）。アプリの更新が必要です。`,
    );
  }
}

function checkRange(checker, path, range) {
  if (range === undefined || range === null) return;
  if (!isObject(range)) {
    checker.add(path, 'range はオブジェクトです');
    return;
  }
  checker.require(range, `${path}.`, 'unit', (v) => RANGE_UNITS.includes(v), 'page か question です');
  checker.require(range, `${path}.`, 'from', isInt, '整数です');
  checker.require(range, `${path}.`, 'to', isInt, '整数です');
  if (isInt(range.from) && isInt(range.to) && range.from > range.to) {
    checker.add(path, `範囲の開始(${range.from})が終了(${range.to})より後です`);
  }
}

function checkLabels(checker, path, labels) {
  if (!isObject(labels)) {
    checker.add(`${path}labels`, '必須の項目がありません');
    return;
  }
  checker.require(labels, `${path}labels.`, 'exam', isText, '表示名が空です');
  checker.optional(labels, `${path}labels.`, 'material', (v) => typeof v === 'string', '文字列です');
  checker.optional(labels, `${path}labels.`, 'subject', (v) => typeof v === 'string', '文字列です');
}

function checkMasters(checker, masters) {
  if (!isObject(masters)) {
    checker.add('masters', 'variant が full のときは masters が必要です');
    return;
  }
  for (const key of ['exams', 'materials', 'subjects']) {
    if (!Array.isArray(masters[key])) checker.add(`masters.${key}`, '配列が必要です');
  }

  (masters.exams || []).forEach((exam, index) => {
    const path = `masters.exams[${index}].`;
    checker.require(exam, path, 'id', isUuid, 'UUIDではありません');
    checker.require(exam, path, 'name', isText, '名称が空です');
    checker.optional(exam, path, 'color', (v) => COLOR.test(v), '#RRGGBB の形ではありません');
    checker.optional(exam, path, 'examDate', isIsoDate, 'YYYY-MM-DD ではありません');
  });

  (masters.materials || []).forEach((material, index) => {
    const path = `masters.materials[${index}].`;
    checker.require(material, path, 'id', isUuid, 'UUIDではありません');
    checker.require(material, path, 'examId', isUuid, 'UUIDではありません');
    checker.require(material, path, 'name', isText, '名称が空です');
    checker.optional(material, path, 'type', (v) => MATERIAL_TYPES.includes(v), '種別が不正です');
    checker.optional(material, path, 'total', isInt, '整数です');
    checker.optional(material, path, 'current', isInt, '整数です');
  });

  (masters.subjects || []).forEach((subject, index) => {
    const path = `masters.subjects[${index}].`;
    checker.require(subject, path, 'id', isUuid, 'UUIDではありません');
    checker.require(subject, path, 'examId', isUuid, 'UUIDではありません');
    checker.require(subject, path, 'name', isText, '名称が空です');
    checker.optional(subject, path, 'parentId', isUuid, 'UUIDではありません');
    checker.optional(subject, path, 'order', isInt, '整数です');
  });
}

/** 下りパッケージ。戻り値 {ok, errors}。バージョン違いは例外。 */
export function validateDown(pkg) {
  checkHeader(pkg, 'down');
  const checker = new Checker();

  checker.require(pkg, '', 'packageId', isUuid, 'UUIDではありません');
  checker.require(pkg, '', 'createdAt', isIsoDateTime, 'タイムゾーン付きのISO 8601ではありません');
  checker.require(pkg, '', 'hubId', isUuid, 'UUIDではありません');
  checker.require(pkg, '', 'targetDate', isIsoDate, 'YYYY-MM-DD ではありません');
  checker.require(pkg, '', 'variant', (v) => v === 'full' || v === 'lite', 'full か lite です');

  if (checker.require(pkg, '', 'settings', isObject, 'オブジェクトです')) {
    checker.require(
      pkg.settings, 'settings.', 'dayChangeHour',
      (v) => isInt(v) && v >= 0 && v <= 23, '0〜23の整数です',
    );
    checker.require(
      pkg.settings, 'settings.', 'weekStartsOn',
      (v) => isInt(v) && v >= 1 && v <= 7, '1〜7の整数です（1=月曜）',
    );
  }

  if (pkg.variant === 'full') checkMasters(checker, pkg.masters);
  else if (pkg.masters !== undefined) checker.add('masters', 'lite なのに masters が入っています');

  if (!Array.isArray(pkg.quotas)) {
    checker.add('quotas', '配列が必要です');
  } else {
    pkg.quotas.forEach((quota, index) => {
      const path = `quotas[${index}].`;
      checker.require(quota, path, 'id', isUuid, 'UUIDではありません');
      checker.require(quota, path, 'date', isIsoDate, 'YYYY-MM-DD ではありません');
      checker.require(quota, path, 'order', isInt, '整数です');
      checker.require(quota, path, 'examId', isUuid, 'UUIDではありません');
      checker.require(quota, path, 'title', isText, '内容が空です');
      checker.require(quota, path, 'targetSeconds', (v) => isInt(v) && v >= 0, '0以上の整数です');
      checker.optional(quota, path, 'materialId', isUuid, 'UUIDではありません');
      checker.optional(quota, path, 'subjectId', isUuid, 'UUIDではありません');
      checkLabels(checker, path, quota.labels);
      checkRange(checker, `quotas[${index}].range`, quota.range);
    });
  }

  if (pkg.reviews !== undefined && pkg.reviews !== null) {
    if (!Array.isArray(pkg.reviews)) {
      checker.add('reviews', '配列が必要です');
    } else {
      pkg.reviews.forEach((review, index) => {
        const path = `reviews[${index}].`;
        checker.require(review, path, 'mistakeId', isUuid, 'UUIDではありません');
        checker.require(review, path, 'questionRef', isText, '問題の指定が空です');
        checker.require(review, path, 'dueDate', isIsoDate, 'YYYY-MM-DD ではありません');
        checker.optional(review, path, 'examId', isUuid, 'UUIDではありません');
        checkLabels(checker, path, review.labels);
      });
    }
  }

  if (pkg.summary !== undefined && pkg.summary !== null) {
    if (!isObject(pkg.summary)) {
      checker.add('summary', 'オブジェクトです');
    } else {
      checker.require(pkg.summary, 'summary.', 'weekStart', isIsoDate, 'YYYY-MM-DD ではありません');
      checker.require(pkg.summary, 'summary.', 'weekTotalSeconds', isInt, '整数です');
      checker.require(pkg.summary, 'summary.', 'weekGoalSeconds', isInt, '整数です');
      (pkg.summary.countdowns || []).forEach((countdown, index) => {
        const path = `summary.countdowns[${index}].`;
        checker.require(countdown, path, 'examId', isUuid, 'UUIDではありません');
        checker.require(countdown, path, 'name', isText, '名称が空です');
        checker.require(countdown, path, 'examDate', isIsoDate, 'YYYY-MM-DD ではありません');
        checker.require(countdown, path, 'daysLeft', isInt, '整数です');
      });
    }
  }

  if (pkg.acks !== undefined && pkg.acks !== null) {
    if (!Array.isArray(pkg.acks)) checker.add('acks', '配列が必要です');
    else pkg.acks.forEach((ack, index) => {
      if (!isUuid(ack)) checker.add(`acks[${index}]`, 'UUIDではありません');
    });
  }

  return { ok: checker.errors.length === 0, errors: checker.errors };
}

/** 自分が作った上りパッケージの自己点検（テストと送信前の確認に使う）。 */
export function validateUp(pkg) {
  checkHeader(pkg, 'up');
  const checker = new Checker();

  checker.require(pkg, '', 'packageId', isUuid, 'UUIDではありません');
  checker.require(pkg, '', 'createdAt', isIsoDateTime, 'タイムゾーン付きのISO 8601ではありません');
  checker.require(pkg, '', 'deviceId', isUuid, 'UUIDではありません');
  checker.require(pkg, '', 'deviceName', isText, '端末名が空です');
  if (!isNullable(pkg.basedOnPackageId, isUuid)) checker.add('basedOnPackageId', 'UUIDかnullです');
  if (pkg.basedOnPackageId === undefined) checker.add('basedOnPackageId', '必須の項目がありません');

  const records = pkg.records;
  if (!isObject(records)) {
    checker.add('records', '必須の項目がありません');
    return { ok: false, errors: checker.errors };
  }

  const ids = [];
  for (const name of ['sessions', 'mistakes', 'reviewResults', 'quotaStatus']) {
    if (!Array.isArray(records[name])) checker.add(`records.${name}`, '配列が必要です');
    else records[name].forEach((record) => { if (isUuid(record?.id)) ids.push(record.id); });
  }

  (records.sessions || []).forEach((session, index) => {
    const path = `records.sessions[${index}].`;
    checker.require(session, path, 'id', isUuid, 'UUIDではありません');
    checker.require(session, path, 'createdAt', isIsoDateTime, '日時の書式が違います');
    checker.require(session, path, 'updatedAt', isIsoDateTime, '日時の書式が違います');
    checker.require(session, path, 'startedAt', isIsoDateTime, '日時の書式が違います');
    checker.require(session, path, 'endedAt', isIsoDateTime, '日時の書式が違います');
    checker.require(session, path, 'activeSeconds', (v) => isInt(v) && v >= 0, '0以上の整数です');
    checker.require(session, path, 'unclassified', (v) => typeof v === 'boolean', '真偽値です');
    checker.require(session, path, 'entryMode', (v) => v === 'timer' || v === 'manual', 'timer か manual です');
    checker.require(session, path, 'deleted', (v) => typeof v === 'boolean', '真偽値です');
    checker.optional(session, path, 'focus', (v) => isInt(v) && v >= 1 && v <= 5, '1〜5の整数です');
    checkRange(checker, `records.sessions[${index}].range`, session.range);
    if (session.unclassified === false && !isUuid(session.examId)) {
      checker.add(`${path}examId`, 'unclassified が false のときは資格が必要です');
    }
    if (isInt(session.correct) && isInt(session.attempted) && session.correct > session.attempted) {
      checker.add(path, '正答数が解答数を超えています');
    }
    if (isIsoDateTime(session.startedAt) && isIsoDateTime(session.endedAt)) {
      const span = (new Date(session.endedAt) - new Date(session.startedAt)) / 1000;
      if (span < 0) checker.add(path, '終了時刻が開始時刻より前です');
      else if (isInt(session.activeSeconds) && session.activeSeconds > span) {
        checker.add(path, '勉強時間が開始〜終了の長さを超えています');
      }
    }
  });

  (records.mistakes || []).forEach((mistake, index) => {
    const path = `records.mistakes[${index}].`;
    checker.require(mistake, path, 'id', isUuid, 'UUIDではありません');
    checker.require(mistake, path, 'createdAt', isIsoDateTime, '日時の書式が違います');
    checker.require(mistake, path, 'updatedAt', isIsoDateTime, '日時の書式が違います');
    checker.require(mistake, path, 'questionRef', isText, '問題の指定が空です');
    checker.require(mistake, path, 'deleted', (v) => typeof v === 'boolean', '真偽値です');
  });

  (records.reviewResults || []).forEach((result, index) => {
    const path = `records.reviewResults[${index}].`;
    checker.require(result, path, 'id', isUuid, 'UUIDではありません');
    checker.require(result, path, 'mistakeId', isUuid, 'UUIDではありません');
    checker.require(result, path, 'result', (v) => v === 'ok' || v === 'ng', 'ok か ng です');
    checker.require(result, path, 'reviewedAt', isIsoDateTime, '日時の書式が違います');
  });

  (records.quotaStatus || []).forEach((status, index) => {
    const path = `records.quotaStatus[${index}].`;
    checker.require(status, path, 'id', isUuid, 'UUIDではありません');
    checker.require(status, path, 'quotaId', isUuid, 'UUIDではありません');
    checker.require(
      status, path, 'status',
      (v) => ['done', 'partial', 'skipped'].includes(v), 'done/partial/skipped です',
    );
    checker.require(status, path, 'updatedAt', isIsoDateTime, '日時の書式が違います');
  });

  const included = new Set(Array.isArray(pkg.includedIds) ? pkg.includedIds : []);
  if (!Array.isArray(pkg.includedIds)) {
    checker.add('includedIds', '配列が必要です');
  } else {
    const missing = ids.filter((id) => !included.has(id));
    const extra = [...included].filter((id) => !ids.includes(id));
    if (missing.length) checker.add('includedIds', `足りないID: ${missing.slice(0, 3).join(', ')}`);
    if (extra.length) checker.add('includedIds', `余分なID: ${extra.slice(0, 3).join(', ')}`);
  }

  return { ok: checker.errors.length === 0, errors: checker.errors };
}
