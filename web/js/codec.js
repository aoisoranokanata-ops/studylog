// QR・貼り付け文字列の展開（転送仕様書 第6章）。
// JSON → deflate-raw → base64url → 先頭に `SL1:`。子機は読む側だけ必要。

export const SCHEMA_VERSION = 1;

export class CodecError extends Error {}

export function looksLikePackageText(text) {
  return typeof text === 'string' && /^\s*SL\d+:/.test(text);
}

export function supportsDecompression() {
  return typeof DecompressionStream === 'function';
}

function base64UrlToBytes(text) {
  const padded = text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (text.length % 4)) % 4);
  let binary;
  try {
    binary = atob(padded);
  } catch {
    throw new CodecError('文字列が壊れています（base64として読めません）');
  }
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function inflateRaw(bytes) {
  if (!supportsDecompression()) {
    throw new CodecError('このブラウザは圧縮の展開に対応していません。ファイルで受け取ってください。');
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  return new Response(stream).text();
}

/** `SL1:...` をパッケージ（オブジェクト）に戻す。 */
export async function decode(text) {
  const value = String(text || '').trim();
  const match = /^SL(\d+):([\s\S]+)$/.exec(value);
  if (!match) throw new CodecError('`SL1:` で始まる文字列ではありません');

  const version = Number(match[1]);
  if (version > SCHEMA_VERSION) {
    throw new CodecError(`このアプリが対応していない形式です（SL${version}）。アプリの更新が必要です。`);
  }

  let json;
  try {
    json = await inflateRaw(base64UrlToBytes(match[2].replace(/\s+/g, '')));
  } catch (error) {
    if (error instanceof CodecError) throw error;
    throw new CodecError('読み取れませんでした（途中で切れている可能性があります）');
  }
  try {
    return JSON.parse(json);
  } catch {
    throw new CodecError('中身がJSONとして読めません');
  }
}
