// QRコードの読み取り。カメラの映像を jsQR に通し、`SL1:` で始まるものを見つけたら返す。
// jsQR は大きいので、この画面を開いたときにだけ読み込む。

import { el, toast } from './components.js';

let jsqrPromise = null;

export function loadJsQr() {
  if (window.jsQR) return Promise.resolve(window.jsQR);
  if (!jsqrPromise) {
    jsqrPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = new URL('../../vendor/jsQR.js', import.meta.url).href;
      script.onload = () => (window.jsQR ? resolve(window.jsQR) : reject(new Error('jsQR を読み込めませんでした')));
      script.onerror = () => {
        jsqrPromise = null;
        reject(new Error('jsQR を読み込めませんでした'));
      };
      document.head.append(script);
    });
  }
  return jsqrPromise;
}

const MAX_SIDE = 900; // 大きすぎる映像は縮めてから読む（速度のため）

/** 画像（映像の1コマやファイル）から QR の文字列を読む。見つからなければ null。 */
export function decodeImage(jsQR, source, width, height, canvas) {
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  const w = Math.max(1, Math.round(width * scale));
  const h = Math.max(1, Math.round(height * scale));
  canvas.width = w;
  canvas.height = h;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  context.drawImage(source, 0, 0, w, h);
  const image = context.getImageData(0, 0, w, h);
  const found = jsQR(image.data, w, h, { inversionAttempts: 'attemptBoth' });
  return found ? found.data : null;
}

async function decodeFile(file) {
  const jsQR = await loadJsQr();
  const bitmap = await createImageBitmap(file);
  try {
    return decodeImage(jsQR, bitmap, bitmap.width, bitmap.height, document.createElement('canvas'));
  } finally {
    bitmap.close?.();
  }
}

/**
 * 読み取り画面を開く。読めた文字列（`SL…:`）を返す。閉じたら null。
 */
export function scanQr() {
  return new Promise((resolve) => {
    const root = document.getElementById('sheet-root');
    const video = el('video', { playsinline: true, muted: true, autoplay: true, class: 'scan-video' });
    video.setAttribute('playsinline', ''); // iOS でインライン再生させるため
    const status = el('p', { class: 'dim small', text: 'カメラを準備しています…' });
    const canvas = document.createElement('canvas');
    let stream = null;
    let running = true;
    let busy = false;

    const finish = (value) => {
      if (!running) return;
      running = false;
      stream?.getTracks().forEach((track) => track.stop());
      backdrop.remove();
      resolve(value);
    };

    const accept = (text) => {
      if (!text) return false;
      if (!/^\s*SL\d+:/.test(text)) {
        status.textContent = 'StudyLog のQRコードではありません（母艦の「QRコードを表示」を読んでください）';
        return false;
      }
      navigator.vibrate?.(60);
      finish(text.trim());
      return true;
    };

    const fileInput = el('input', {
      type: 'file',
      accept: 'image/*',
      hidden: true,
      onChange: async (event) => {
        const file = event.target.files?.[0];
        event.target.value = '';
        if (!file) return;
        try {
          const text = await decodeFile(file);
          if (!accept(text)) toast(text ? 'StudyLog のQRコードではありません' : '画像からQRコードを見つけられませんでした', { error: true });
        } catch (error) {
          toast(error.message, { error: true });
        }
      },
    });

    const sheet = el('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true' }, [
      el('div', { class: 'sheet-title', text: 'QRコードを読み取る' }),
      el('div', { class: 'scan-frame' }, [video, el('div', { class: 'scan-guide' })]),
      status,
      fileInput,
      el('div', { class: 'btn-row' }, [
        el('button', { type: 'button', class: 'btn', text: '画像から読む', onClick: () => fileInput.click() }),
        el('button', { type: 'button', class: 'btn', text: '閉じる', onClick: () => finish(null) }),
      ]),
    ]);
    const backdrop = el('div', { class: 'sheet-backdrop' }, [sheet]);
    root.append(backdrop);

    const tick = (jsQR) => {
      if (!running) return;
      if (!busy && video.readyState >= 2 && video.videoWidth) {
        busy = true;
        try {
          const text = decodeImage(jsQR, video, video.videoWidth, video.videoHeight, canvas);
          if (text && accept(text)) return;
        } catch {
          /* 読めないコマは飛ばす */
        } finally {
          busy = false;
        }
      }
      requestAnimationFrame(() => tick(jsQR));
    };

    (async () => {
      let jsQR;
      try {
        jsQR = await loadJsQr();
      } catch (error) {
        status.textContent = error.message;
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        status.textContent = 'この端末ではカメラを使えません。「画像から読む」か、文字列の貼り付けを使ってください。';
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
      } catch (error) {
        status.textContent =
          error?.name === 'NotAllowedError'
            ? 'カメラの使用が許可されていません。端末の設定で許可するか、「画像から読む」を使ってください。'
            : 'カメラを起動できませんでした。「画像から読む」か、文字列の貼り付けを使ってください。';
        return;
      }
      if (!running) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      video.srcObject = stream;
      try {
        await video.play();
      } catch {
        /* 自動再生が止められても、フレームが来れば読める */
      }
      status.textContent = '母艦に表示したQRコードを枠に入れてください';
      tick(jsQR);
    })();
  });
}
