# StudyLog 母艦（PC用アプリ）

資格試験の勉強記録を一元管理する母艦。唯一の正本（データの原本）を持ち、外出先のブラウザ子機とはファイル／QRコードでやりとりする。

転送に関わる仕様は `../spec/transfer-spec.md` が正。

## 動かす

```
python -m studylog
```

開発時は `src` にパスを通すこと（PowerShell なら `$env:PYTHONPATH="src"`）。

## テスト

```
python -m pytest -q
```

画面のテストはオフスクリーンで動かす（`QT_QPA_PLATFORM=offscreen`）。

## ビルド（配布用のEXE）

```
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

PyInstaller の onedir 方式。`dist/StudyLog/StudyLog.exe` ができる。フォルダごと移動できる。

## データの置き場所

`exe（開発時は desktop/）の隣の data/`。

```
data/
  studylog.db      SQLite本体
  backups/         起動時・終了時・取り込み前・手動のバックアップ（既定14世代）
  logs/            ログ
  sync/            子機とのやりとり
    inbox/         子機から届いた上りファイルを置く場所（自動で取り込む）
    outbox/        下りファイルの控え
    processed/     取り込みに成功したファイル
    rejected/      検証に失敗したファイル（理由は転送履歴に残る）
```

`%APPDATA%` を使わないのは、持ち運べるようにするためと、環境によってフォルダが仮想化されて
保存先が二重になる事故を避けるため。`STUDYLOG_DATA_DIR` 環境変数で差し替えられる（テスト用）。

## 構成

| 場所 | 役割 |
|---|---|
| `src/studylog/core/` | 日時と学習日の計算、ID採番 |
| `src/studylog/db/` | 接続、マイグレーション（`migrations/*.sql`）、バックアップ |
| `src/studylog/domain/` | DBにもUIにも依存しない値オブジェクトと区分値 |
| `src/studylog/repositories/` | SQLはここだけに閉じる |
| `src/studylog/services/` | 業務ロジック |
| `src/studylog/services/transfer/` | 転送（codec / validator / down_builder / up_importer / service / watcher） |
| `src/studylog/schemas/` | 転送パッケージのJSON Schema。`spec/schemas/` の複製（ズレはテストで検出する） |
| `src/studylog/ui/` | 画面。`modules/` に1フォルダ＝1機能で置く |

### 画面を増やすとき

`src/studylog/ui/modules/<名前>/__init__.py` に次を書くだけでナビに出る。

```python
from ...module_registry import FeatureModule
from .view import YourView

MODULE = FeatureModule(id="your", title="表示名", order=40, factory=YourView)
```

`factory` は `AppContext` を受け取って `QWidget` を返す。`refresh()` を持っていれば画面を開くたびに呼ばれる。

## 決めごと

- 日時はUTCで保存し、表示と転送時にローカル（+09:00）へ変換する
- 「学習日」は `settings.day_change_hour`（既定4時）で区切り、`sessions.study_date` に保存する
- 論理削除（`deleted_at`）。CHECK制約は書かず、整合は `services/` で守る
- 経過時間は必ず時刻の差から計算する（アプリが落ちても正しい）

## 開発メモ（つまずいた点）

- PyInstallerの入口 `__main__.py` は**絶対import**にすること。相対importだと凍結後に
  `attempted relative import with no known parent package` で落ちる
- `ui/modules/` は動的に読み込むので、specで `collect_submodules` を使う。
  その際 `src` を `sys.path` に入れておかないと空になり、実行時に `ModuleNotFoundError` になる
- `QT_QPA_PLATFORM=offscreen` で描画すると日本語が豆腐になる。見た目の確認は通常の描画で行う

## 転送（子機とのやりとり）

「転送」画面に3つのタブがある。

- **送る**：その日のノルマを作り（追加・編集・並べ替え、予定からの生成、前日からのコピー）、
  子機へ渡す。`QRコードを表示`（lite・1,800バイトまで）、`ファイルに保存`（full・outbox と任意の場所）、
  `文字列をコピー`（`SL1:...`）。上限を超えるとQRは止めて、ファイルで渡すよう案内する
- **受け取る**：`inbox/` を常時監視して自動で取り込む（QFileSystemWatcher＋30秒ごとのポーリング）。
  手動の取り込み、ドラッグ＆ドロップも可。取り込み結果と子機の最終受信日時を表示する
- **履歴**：送受信の記録（件数・結果・拒否の理由）

取り込みは**冪等**で、同じファイルを何度取り込んでも結果は変わらない。母艦で編集した記録は、
古い `updatedAt` の上りデータでは上書きされない。未知のマスタIDを参照する記録は拒否せず、
**未分類**として受け入れて「未分類」画面でまとめて割り当てる。

スキーマは `spec/schemas/` が正で、EXEに同梱するために `src/studylog/schemas/` へ複製している。
`spec/` を直したらこちらにもコピーすること（ズレていると `test_packaged_schemas_match_spec` が落ちる）。

## 可視化（フェーズ3）

| 画面 | 中身 |
|---|---|
| ダッシュボード（起動時に最初に開く） | 今日・今週（週目標の達成率）・連続学習・未分類の件数、直近14日のグラフ、試験日までの日数と「1日あたり必要な時間」、今日のノルマ・復習・期限が近い課題、子機の最終受信 |
| 集計 | 日・週・月ごとの勉強時間（グラフと表）、資格・参考書・分野別の内訳、学習日数・連続学習・ノルマ達成率、分野別の正答率、参考書の進み具合 |
| 目標 | 週目標（全体・資格別）、直近8週の実績と目標、資格ごとの総勉強時間の目標 |

- **週目標は、設定しなかった週は前の週の値を引き継ぐ**。子機に送る週目標（`summary.weekGoalSeconds`）も同じ規則
- 計測中に起動したときは、ダッシュボードではなく計測画面から開く
- 数えるのは SQL（`repositories/`）、期間の区切りは `services/stats_service.py`、目標は `services/goal_service.py`

### グラフの決めごと（`ui/widgets/charts.py`）

- 色は1色（青 `#2a78d6`）。推移も内訳も「量の比較」なので色で区別しない（検証済みの既定パレットで、明るい背景に対して全チェック合格）
- 内訳は円グラフにせず、値の大きい順の横棒。10件を超えたら「その他」にまとめる
- 棒グラフは**自前で描く**。QtCharts の分類軸は項目が多いとラベルを「8/…」のように省略してしまい、
  間引いても直らなかったため。目盛りは 1・2・2.5・5 ×10ⁿ、横軸ラベルは重ならないよう間引き、
  マウスを重ねると期間と値（と目標）が出る。数字は「表」タブでも見られる
- 部品を作り直すときは `clear_layout()` で古い部品を**すぐ隠す**（`deleteLater` だけだと一瞬重なって見える）
