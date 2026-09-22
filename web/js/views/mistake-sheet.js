// 誤答の簡易登録。必須は「問題の識別」と「一言メモ」だけ。続けて何件でも登録できる。
// 分類（資格・参考書・分野）は直前の記録から引き継ぐ。

import { nowIso } from '../clock.js';
import * as store from '../store.js';
import { el, field, openSheet, toast } from './components.js';

export const REASONS = {
  knowledge: '知識不足',
  misread: '読み違い',
  careless: 'ケアレスミス',
  confusion: '混同',
  other: 'その他',
};

/** 誤答を1件保存する（新規と編集の両方）。 */
export async function saveMistake({ base, mistake, questionRef, memo, reason }) {
  return store.putMistake({
    id: mistake?.id || store.newId(),
    createdAt: mistake?.createdAt || nowIso(),
    sessionId: mistake ? mistake.sessionId : base.sessionId || null,
    examId: mistake ? mistake.examId : base.examId || null,
    materialId: mistake ? mistake.materialId : base.materialId || null,
    subjectId: mistake ? mistake.subjectId : base.subjectId || null,
    questionRef: questionRef.trim(),
    memo: memo.trim(),
    reason: reason || null,
  });
}

/** 直前の記録（なければ計測中の選択）から分類を引き継ぐ。 */
export async function lastClassification() {
  const sessions = (await store.listRecords('sessions'))
    .filter((session) => !session.deleted)
    .sort((a, b) => (a.startedAt < b.startedAt ? 1 : -1));
  const last = sessions[0];
  if (!last) return { sessionId: null, examId: null, materialId: null, subjectId: null };
  return {
    sessionId: last.id,
    examId: last.examId,
    materialId: last.materialId,
    subjectId: last.subjectId,
  };
}

/**
 * 誤答の登録シート。base は引き継ぐ分類（sessionId を含む）。
 * 登録した件数を返す。
 */
export async function openMistakeSheet({ base = null, mistake = null } = {}) {
  const inherited = base || (mistake ? null : await lastClassification());
  const labels = await store.labelsFor(mistake || inherited || {});
  const where = [labels.exam, labels.material, labels.subject].filter(Boolean).join('　') || '未分類';

  const questionRef = el('input', {
    type: 'text',
    placeholder: '例：p.52 問3',
    value: mistake?.questionRef || '',
    autocomplete: 'off',
  });
  const memo = el('input', {
    type: 'text',
    placeholder: '例：取得時効の起算点を取り違えた',
    value: mistake?.memo || '',
    autocomplete: 'off',
  });
  const reasonButtons = el('div', { class: 'chips' });
  let reason = mistake?.reason || null;
  const paintReasons = () => {
    for (const button of reasonButtons.children) {
      button.setAttribute('aria-pressed', String(button.dataset.value === reason));
    }
  };
  for (const [value, label] of Object.entries(REASONS)) {
    reasonButtons.append(
      el('button', {
        type: 'button',
        class: 'chip',
        text: label,
        dataset: { value },
        onClick: () => {
          reason = reason === value ? null : value;
          paintReasons();
        },
      }),
    );
  }
  paintReasons();

  const counter = el('p', { class: 'dim small' });
  let saved = 0;
  const updateCounter = () => {
    counter.textContent = saved ? `この画面で${saved}件登録しました` : '';
  };

  const validate = () => {
    if (!questionRef.value.trim()) {
      toast('問題の識別を入れてください', { error: true });
      questionRef.focus();
      return false;
    }
    if (!memo.value.trim()) {
      toast('一言メモを入れてください', { error: true });
      memo.focus();
      return false;
    }
    return true;
  };

  const save = async () => {
    await saveMistake({
      base: inherited,
      mistake,
      questionRef: questionRef.value,
      memo: memo.value,
      reason,
    });
    saved += 1;
  };

  const actions = mistake
    ? [
        { label: 'やめる', value: 0 },
        {
          label: '保存',
          primary: true,
          onClick: async () => {
            if (!validate()) return false;
            await save();
            return saved;
          },
        },
      ]
    : [
        {
          label: '続けて登録',
          onClick: async () => {
            if (!validate()) return false;
            await save();
            toast(`${questionRef.value.trim()} を登録しました`);
            questionRef.value = '';
            memo.value = '';
            reason = null;
            paintReasons();
            updateCounter();
            questionRef.focus();
            return false; // シートは閉じない
          },
        },
        {
          label: '登録して閉じる',
          primary: true,
          onClick: async () => {
            const empty = !questionRef.value.trim() && !memo.value.trim();
            if (empty && saved) return saved; // 続けて登録した後の空欄はそのまま閉じる
            if (!validate()) return false;
            await save();
            return saved;
          },
        },
      ];

  const result = await openSheet({
    title: mistake ? '誤答を編集' : '誤答を登録',
    body: [
      el('div', { class: 'dim small', text: `分類：${where}` }),
      field('問題の識別（必須）', questionRef),
      field('一言メモ（必須）', memo),
      el('div', { class: 'field' }, [el('label', { text: '誤答の理由（任意）' }), reasonButtons]),
      counter,
      mistake ? null : el('button', {
        type: 'button',
        class: 'btn btn-small',
        text: '閉じる',
        onClick: () => document.querySelector('.sheet-backdrop')?.click(),
      }),
    ],
    actions,
  });
  return typeof result === 'number' ? result : saved;
}
