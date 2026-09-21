# StudyLog 子機（ブラウザアプリ）

外出先で使う薄い子機。母艦から「今日のノルマ」を受け取り、勉強時間と記録を持ち帰る。
データは一時的なもので、母艦に取り込まれたら7日後に消える。

転送に関わる仕様は `../spec/transfer-spec.md` が正。

## 動かす

ビルド工程はない。`studylog/` をルートにして静的配信し、`/web/` を開く。

```bash
python -m http.server 8652 --directory studylog
```

- アプリ: http://localhost:8652/web/
- テスト: http://localhost:8652/web/dev/test.html

テストは仕様書のサンプル（`spec/examples/`）を読むため、`studylog/` をルートにする必要がある。
**テストを実行するとアプリのデータ（IndexedDB）は消える。**

## 公開（GitHub Pages）

`.github/workflows/deploy-web.yml` が `web/` を Pages に配る。`dev/` は公開物から除外する。
リポジトリ作成とPagesの有効化はまだ行っていない。

## 構成

| 場所 | 役割 |
|---|---|
| `js/db.js` | IndexedDBの薄いラッパー（自作） |
| `js/store.js` | レコードの読み書きと `pending` / `acked` の状態 |
| `js/clock.js` | 学習日・週・経過時間（母艦と同じ規則） |
| `js/codec.js` | `SL1:` の展開（`DecompressionStream('deflate-raw')`） |
| `js/validate.js` | 転送パッケージの検証（手書き） |
| `js/transfer.js` | 受け取り・上りの作成・acks処理・7日削除 |
| `js/timer.js` | 計測（時刻の差分だけで計算） |
| `js/views/` | 画面（今日／計測／記録／転送／設定）と共通部品 |
| `dev/` | ブラウザで走らせるテスト。公開物には含めない |

## IndexedDB（DB名 `studylog` / version 1）

| ストア | キー | 内容 |
|---|---|---|
| `inbound` | `'current'` | 最後に受け取った下り（settings, masters, quotas, reviews, summary, packageId） |
| `sessions` / `mistakes` / `reviewResults` / `quotaStatus` | `id` | 上りに載せる記録。`state`（`pending` / `acked`）と `ackedAt` を持つ |
| `outbox` | `packageId` | 送った `includedIds` と送信時刻 |
| `timer` | `'current'` | 計測中の状態 |
| `device` | `'current'` | deviceId・表示名・初回案内の既読 |
| `meta` | `key` | 前回使った分類、Wake Lockの設定など |

## 決めごと

- **検証は手書き**：JSON Schemaのライブラリは持ち込まない（ビルド工程なし・JS 100KB以下のため）。
  必須項目・型・列挙・書式を順に見て、1つでも違反があればパッケージ全体を拒否する
- **経過時間は時刻の差から計算**：画面ロック中はJSが止まるため、カウンタを回さない
- **今週の時間は「未ack」を足す**（「未送信」ではない。仕様書 A-5）
- **`quotaStatus` は下りを受け取っても消さない**（仕様書 A-3）
- **`masters` 未所持なら「未分類」のみ**（仕様書 A-4）
- **テーマだけ localStorage**：起動時の一瞬のちらつきを避けるため。記録データは入れない
- 外部への通信は一切しない。CDNも使わない

## iOSでの注意

- **ホーム画面に追加してから使う**こと。Safariのまま使うと保存領域が別になる（初回に案内を出す）
- 画面ロック中はJSが止まる → 経過時間は時刻の差から計算している
- `DecompressionStream` 非対応の古い端末では、文字列（`SL1:`）の受け取りができない。
  その場合はファイルで受け取る（画面にも表示する）

## いまの状態（フェーズ1）

できていること：PWA（オフライン動作・更新通知）、下りの受け取り（ファイル・文字列）、今日の画面、
計測と確認シート、手動記録、履歴、上りの送信、acks処理と7日削除、設定、警告バナー。

フェーズ2以降：QRコードの読み取り（jsQR を `vendor/` に同梱）、誤答の簡易登録、復習。
