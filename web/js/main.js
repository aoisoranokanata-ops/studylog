// 起動と画面の切り替え。

import { requestPersistence } from './db.js';
import * as store from './store.js';
import * as timer from './timer.js';
import { clear, el, openSheet, toast } from './views/components.js';
import * as homeView from './views/home.js';
import * as measureView from './views/measure.js';
import * as recordsView from './views/records.js';
import * as reviewView from './views/review.js';
import * as settingsView from './views/settings.js';
import * as transferView from './views/transfer.js';

const VIEWS = {
  home: { title: '今日', render: homeView.render },
  measure: { title: '計測', render: measureView.render },
  records: { title: '記録', render: recordsView.render },
  transfer: { title: '転送', render: transferView.render },
  settings: { title: '設定', render: settingsView.render },
  // タブを持たない画面。tab は下のタブバーでどれを光らせるか
  review: { title: '復習', render: reviewView.render, tab: 'home' },
};

const app = {
  current: 'home',
  wakeLockSentinel: null,

  async go(name) {
    if (!VIEWS[name]) return;
    if (this.current === 'review' && name !== 'review') reviewView.reset();
    this.current = name;
    const tabName = VIEWS[name].tab || name;
    for (const tab of document.querySelectorAll('.tab')) {
      if (tab.dataset.view === tabName) tab.setAttribute('aria-current', 'page');
      else tab.removeAttribute('aria-current');
    }
    await this.refresh();
    window.scrollTo({ top: 0 });
  },

  async refresh() {
    const view = VIEWS[this.current];
    document.getElementById('view-title').textContent = view.title;
    const root = clear(document.getElementById('view'));
    measureView.stopTicking();
    try {
      await view.render(root, this);
    } catch (error) {
      console.error(error);
      root.append(el('p', { class: 'banner banner-warn', text: `画面を作れませんでした: ${error.message}` }));
    }
    await this.updateBadge();
  },

  async updateBadge() {
    const state = await timer.getState();
    const extra = document.getElementById('appbar-extra');
    extra.textContent = state ? (state.running ? '● 計測中' : '⏸ 一時停止中') : '';
  },

  /** ホーム画面のノルマをタップしたら、そのノルマで計測を始める。 */
  async startQuota(quota) {
    const state = await timer.getState();
    if (state) {
      toast('すでに計測中です');
      await this.go('measure');
      return;
    }
    await timer.start({
      quotaId: quota.id,
      examId: quota.examId || null,
      materialId: quota.materialId || null,
      subjectId: quota.subjectId || null,
      memo: '',
    });
    await this.go('measure');
  },

  async requestWakeLock() {
    if (this.wakeLockSentinel || !('wakeLock' in navigator)) return;
    try {
      this.wakeLockSentinel = await navigator.wakeLock.request('screen');
      this.wakeLockSentinel.addEventListener('release', () => {
        this.wakeLockSentinel = null;
      });
    } catch {
      this.wakeLockSentinel = null; // 拒否されても計測は続ける
    }
  },

  releaseWakeLock() {
    this.wakeLockSentinel?.release?.().catch(() => {});
    this.wakeLockSentinel = null;
  },
};

// --- 初回の案内（iOSはホーム画面に追加しないと保存領域が別になる） ----------

async function showOnboardingIfNeeded() {
  const device = await store.getDevice();
  if (device.onboarded) return;

  const isStandalone =
    window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  const isIos = /iP(hone|ad|od)/.test(navigator.userAgent);

  await openSheet({
    title: 'StudyLog 子機へようこそ',
    body: [
      el('p', { class: 'small', text: '母艦から「今日のノルマ」を受け取り、勉強時間と記録を持ち帰るためのアプリです。' }),
      isIos && !isStandalone
        ? el('p', {
            class: 'banner banner-warn',
            text: '先に「共有」→「ホーム画面に追加」してから使ってください。Safariのまま使うと、記録の保存場所が別になります。',
          })
        : null,
      el('p', { class: 'small', text: '記録は母艦に送るまでこの端末にだけ残ります。外部への通信はしません。' }),
    ],
    actions: [{ label: 'はじめる', value: true, primary: true }],
  });
  await store.updateDevice({ onboarded: true });
}

// --- Service Worker ---------------------------------------------------------

function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  // 初回インストールでは「更新」ではないので、バナーも再読み込みも要らない
  const hadController = Boolean(navigator.serviceWorker.controller);
  navigator.serviceWorker
    .register('sw.js')
    .then((registration) => {
      const notify = (worker) => {
        if (!worker) return;
        worker.addEventListener('statechange', () => {
          if (worker.state === 'installed' && hadController) {
            showUpdateBanner(worker);
          }
        });
      };
      // すでに新しい版が待機している場合もある（前回の訪問で入れ替わった直後など）
      if (registration.waiting && hadController) {
        showUpdateBanner(registration.waiting);
      }
      notify(registration.installing);
      registration.addEventListener('updatefound', () => notify(registration.installing));
    })
    .catch((error) => console.warn('Service Workerを登録できませんでした', error));

  let reloading = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (reloading || !hadController) return;
    reloading = true;
    window.location.reload();
  });
}

function showUpdateBanner(worker) {
  const banner = document.getElementById('update-banner');
  banner.hidden = false;
  document.getElementById('update-reload').onclick = () => {
    worker.postMessage({ type: 'SKIP_WAITING' });
  };
}

// --- 起動 -------------------------------------------------------------------

async function boot() {
  settingsView.applyTheme(settingsView.currentTheme());

  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => app.go(tab.dataset.view));
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) app.refresh();
  });

  registerServiceWorker();
  await requestPersistence();
  await store.getDevice();

  const state = await timer.getState();
  await app.go(state ? 'measure' : 'home');
  await showOnboardingIfNeeded();
}

boot().catch((error) => {
  console.error(error);
  document.getElementById('view').append(
    el('p', { class: 'banner banner-warn', text: `起動できませんでした: ${error.message}` }),
  );
});

window.studylog = { app, store, timer };
