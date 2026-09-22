// 復習。母艦から受け取った復習対象を1件ずつ出し、「できた／できなかった」を記録する。
// メモは答えのヒントになるので、最初は隠しておき、タップで開く。

import { daysBetween, todayStudyDate } from '../clock.js';
import * as store from '../store.js';
import { card, el, toast } from './components.js';

// 「あとで」にした問題（この画面を開いている間だけ覚える）
const skipped = new Set();
// 直前の回答（押し間違いの取り消し用）
let lastAnswer = null;

const RESULT_LABEL = { ok: 'できた', ng: 'できなかった' };

export async function render(root, app) {
  const [reviews, settings, allReviews] = await Promise.all([
    store.visibleReviews(),
    store.getSettings(),
    store.getReviews(),
  ]);
  const today = todayStudyDate(settings.dayChangeHour);
  const remaining = reviews.filter((review) => !skipped.has(review.mistakeId));
  const answeredCount = allReviews.length - reviews.length;

  if (lastAnswer) root.append(undoBanner(app));

  root.append(
    el('div', { class: 'row-between' }, [
      el('span', { class: 'dim', text: `今日の復習 ${allReviews.length}件` }),
      el('span', { class: 'strong', text: `済み ${answeredCount}／残り ${reviews.length}` }),
    ]),
    el('div', { class: 'bar' }, [
      el('span', {
        style: `width:${allReviews.length ? Math.round((answeredCount / allReviews.length) * 100) : 0}%`,
      }),
    ]),
  );

  if (!allReviews.length) {
    root.append(
      card('復習', [
        el('p', { class: 'empty', text: '今日の復習対象はありません。' }),
        el('button', { type: 'button', class: 'btn btn-block', text: '今日へ戻る', onClick: () => app.go('home') }),
      ]),
    );
    return;
  }

  if (!remaining.length) {
    root.append(
      card(reviews.length ? '「あとで」にした問題が残っています' : 'おつかれさまでした', [
        el('p', {
          class: 'dim',
          text: reviews.length
            ? `${reviews.length}件を「あとで」にしました。`
            : '今日の復習はすべて終わりました。結果は次に母艦へ送るときに一緒に届きます。',
        }),
        reviews.length
          ? el('button', {
              type: 'button',
              class: 'btn btn-primary btn-block',
              text: 'あとでにした問題をもう一度',
              onClick: () => {
                skipped.clear();
                app.refresh();
              },
            })
          : null,
        el('button', { type: 'button', class: 'btn btn-block', text: '今日へ戻る', onClick: () => app.go('home') }),
      ]),
    );
    return;
  }

  const review = remaining[0];
  const late = daysBetween(review.dueDate, today);
  const where = [review.labels?.exam, review.labels?.material, review.labels?.subject].filter(Boolean).join('　');

  const memo = el('div', { class: 'review-memo', hidden: true, text: review.memo || '（メモはありません）' });
  const reveal = el('button', {
    type: 'button',
    class: 'btn btn-small',
    text: 'メモを見る',
    onClick: () => {
      memo.hidden = false;
      reveal.remove();
    },
  });

  root.append(
    el('section', { class: 'card review-card' }, [
      el('div', { class: 'row-between' }, [
        el('span', { class: 'dim small truncate grow', text: where }),
        late > 0
          ? el('span', { class: 'badge badge-pending', text: `${late}日遅れ` })
          : el('span', { class: 'badge', text: '今日' }),
      ]),
      el('div', { class: 'review-question', text: review.questionRef }),
      reveal,
      memo,
    ]),
    el('div', { class: 'btn-row review-buttons' }, [
      el('button', {
        type: 'button',
        class: 'btn btn-ng',
        text: 'できなかった',
        onClick: () => answer(app, review, 'ng'),
      }),
      el('button', {
        type: 'button',
        class: 'btn btn-ok',
        text: 'できた',
        onClick: () => answer(app, review, 'ok'),
      }),
    ]),
    el('button', {
      type: 'button',
      class: 'btn btn-small btn-block',
      text: 'あとで',
      onClick: () => {
        skipped.add(review.mistakeId);
        lastAnswer = null;
        app.refresh();
      },
    }),
  );
}

async function answer(app, review, result) {
  const record = await store.recordReview(review.mistakeId, result);
  lastAnswer = { id: record.id, questionRef: review.questionRef, result };
  navigator.vibrate?.(result === 'ok' ? 30 : [30, 60, 30]);
  app.refresh();
}

function undoBanner(app) {
  const answer = lastAnswer;
  return el('div', { class: 'banner banner-info' }, [
    el('span', { class: 'small', text: `「${answer.questionRef}」を「${RESULT_LABEL[answer.result]}」で記録` }),
    el('button', {
      type: 'button',
      class: 'btn btn-small',
      text: '取り消す',
      onClick: async () => {
        const outcome = await store.removeReviewResult(answer.id);
        lastAnswer = null;
        if (outcome === 'sent') toast('送信済みの結果は取り消せません', { error: true });
        else toast('取り消しました');
        app.refresh();
      },
    }),
  ]);
}

/** 画面を離れたら「あとで」と取り消し候補を忘れる。 */
export function reset() {
  skipped.clear();
  lastAnswer = null;
}
