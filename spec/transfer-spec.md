# StudyLog 転送仕様書 v1.1（母艦EXE ⇄ ブラウザ子機）

この文書は、母艦（PC用EXE）と子機（ブラウザアプリ）の両方が従う唯一の取り決めである。実装が本書と食い違う場合は、本書を正とする。仕様を変更するときは、先に本書と `schemaVersion` を更新すること。

`schemaVersion` は **1** のまま（v1.1 は実装着手前の明確化であり、v1 の実装は存在しないため版を上げない）。

## 0. Claude Codeへの指示（本書を渡されたとき）
- `spec/schemas/down.schema.json` と `spec/schemas/up.schema.json` を JSON Schema（draft 2020-12）で作成すること
- 正常例と異常例のサンプルJSONを `spec/examples/` に作成すること（取り込み済み通知による削除、再送、未分類記録、スキーマ違反の各ケースを含める）
- 本書に曖昧な点や矛盾があれば、スキーマを作る前に指摘すること

## 1. 基本原則
1. **母艦が唯一の正本**である。子機のデータはすべて一時的なもの。
2. データの流れは2本だけ。
   - **下り（母艦→子機）**：ノルマ、参照用データ、取り込み済み通知。子機は受け取った内容で丸ごと置き換える。
   - **上り（子機→母艦）**：勉強記録、誤答、復習結果、ノルマの達成状況。母艦は追記・更新する。
3. 子機は、**取り込み済み通知を受けていない記録を毎回すべて送る**（累積送信）。母艦はIDを基準に取り込むため、同じファイルを何度取り込んでも重複しない（冪等性）。ファイルを1つ紛失しても、次の送信で回復できる。
4. 子機での削除は、**取り込み済み通知を受けたもの**に限る。未取り込みの記録は、何日経っても自動では削除しない。
5. 受信側は、知らない項目があっても無視して処理を続ける（前方互換）。必須項目の欠落や型の違反があれば、そのパッケージ全体を拒否する。
   - この原則により、**スキーマに `additionalProperties: false` を書いてはならない**。

## 2. 共通の約束
- ID：UUID v4 の文字列（照合は大文字小文字を区別しない。生成は小文字）
- 日時：タイムゾーン付きの ISO 8601（例：`2026-09-20T14:30:00+09:00`。`Z` も可）
- 日付：`YYYY-MM-DD`。「学習日」は日付変更時刻（下りの `settings.dayChangeHour`）で区切る
- 時間：秒単位の整数（0以上）
- 曜日：`settings.weekStartsOn` は ISO-8601 準拠で **1=月曜 … 7=日曜**（既定 1）
- 文字コード：UTF-8
- パッケージ共通のヘッダー：
```json
{
  "format": "studylog-transfer",
  "kind": "down" | "up",
  "schemaVersion": 1,
  "packageId": "uuid",
  "createdAt": "ISO8601"
}
```
- 受信側の `schemaVersion` より新しいパッケージは拒否し、「アプリの更新が必要」と表示する。古いパッケージは、定義された変換で読めるなら受け入れる。
  - **検証の順序**：①JSONとして読めるか ②`format`・`kind` の一致 ③`schemaVersion` の比較（新しければ「更新が必要」と表示して終了）④スキーマ検証。スキーマ側は `schemaVersion` を `const: 1` とするため、③を先に行わないと利用者に適切な案内ができない。

## 3. 下りパッケージ（母艦→子機）
```json
{
  "...共通ヘッダー": "",
  "kind": "down",
  "hubId": "母艦の識別ID",
  "targetDate": "2026-09-20",
  "variant": "full" | "lite",
  "settings": { "dayChangeHour": 4, "weekStartsOn": 1 },
  "masters": {
    "exams":     [{ "id": "", "name": "", "color": "#RRGGBB", "examDate": "YYYY-MM-DD|null", "archived": false }],
    "materials": [{ "id": "", "examId": "", "name": "", "type": "text|drill|past|lecture|other", "unitLabel": "ページ|問", "total": 0, "current": 0, "archived": false }],
    "subjects":  [{ "id": "", "examId": "", "parentId": "uuid|null", "name": "", "order": 0, "archived": false }]
  },
  "quotas": [{
    "id": "", "date": "YYYY-MM-DD", "order": 0,
    "examId": "", "materialId": "uuid|null", "subjectId": "uuid|null",
    "labels": { "exam": "表示名", "material": "表示名|null", "subject": "表示名|null" },
    "title": "例：民法総則 問題集 p.40-65",
    "targetSeconds": 5400,
    "range": { "unit": "page|question", "from": 40, "to": 65 },
    "note": ""
  }],
  "reviews": [{
    "mistakeId": "", "examId": "uuid|null", "materialId": "uuid|null", "subjectId": "uuid|null",
    "labels": { "exam": "表示名", "material": "表示名|null", "subject": "表示名|null" },
    "questionRef": "例：p.52 問3", "memo": "", "dueDate": "YYYY-MM-DD"
  }],
  "summary": {
    "weekStart": "YYYY-MM-DD", "weekTotalSeconds": 0, "weekGoalSeconds": 0,
    "countdowns": [{ "examId": "", "name": "", "examDate": "YYYY-MM-DD", "daysLeft": 0 }]
  },
  "acks": ["取り込み済みの上りpackageId", "..."]
}
```
- `variant: "full"`：`masters` を含む。ファイルで転送する。
- `variant: "lite"`：`masters` を省略する。QRコードで転送する。ノルマや復習対象の表示は `labels` で行う（子機が参照用データを持っていなくても表示できるように）。
- `range`、`reviews`、`summary` は省略できる。
- **省略と明示的な空の区別**（B-1）：`reviews`・`summary` は、**キー自体が無ければ前回の内容を維持**し、**`[]` または `null` を明示したときだけクリア**する。`quotas` と `settings` は常に必須で、常に丸ごと置き換える（`quotas: []` は「今日のノルマなし」を意味する）。
- `acks`：母艦が取り込み済みの上り `packageId` のうち、**取り込み日時から30日以内**のもの（B-8）。子機は自分が送ったものだけを照合する。
  - `acks` は状態ではなく通知であり、上の「省略と明示的な空の区別」の対象外。省略・`[]`・`null` のいずれも「今回の新しい通知は無し」を意味し、子機が既に処理済みの取り込み済み判定を取り消すことはない。
- `masters` を一度も受け取っていない子機（QRのみで開始した場合）（A-4）：子機は自由記録の分類先として「未分類」のみを提示し、ホーム画面に「一度ファイルで受け取ってください」と案内を出す。ノルマと復習は `labels` で表示できるため、この状態でも利用できる。
- `quotas[].range` は `from <= to` であること（JSON Schema では表現できないため、両側のアプリで検証する）。

### 子機が下りパッケージを受け取ったときの処理
1. 検証する（形式、`kind`、`schemaVersion`、スキーマ。第2章の検証順序に従う）
2. `full` なら `masters` を丸ごと置き換える。`lite` なら `masters` はそのまま残す
3. `quotas`、`settings` を丸ごと置き換える。`reviews`、`summary` は前項の「省略と明示的な空の区別」に従う
4. `acks` を処理する（第5章）

- **`quotaStatus` は下りパッケージでは一切削除しない**（A-3）。`quotaStatus` は上り記録（送信対象）であり、対応する `quotaId` が新しい `quotas` に無くなっても、送信対象としては残す（表示上ひもづけ先が消えるだけ）。同じ `quotaId` のノルマが再び含まれる場合は、既存の達成状況をそのまま引き継いで表示する。

## 4. 上りパッケージ（子機→母艦）
```json
{
  "...共通ヘッダー": "",
  "kind": "up",
  "deviceId": "子機ごとに生成したID", "deviceName": "例：iPhone",
  "basedOnPackageId": "最後に受け取った下りpackageId|null",
  "records": {
    "sessions": [{
      "id": "", "createdAt": "", "updatedAt": "",
      "quotaId": "uuid|null",
      "examId": "uuid|null", "materialId": "uuid|null", "subjectId": "uuid|null",
      "unclassified": false,
      "startedAt": "", "endedAt": "", "activeSeconds": 0,
      "range": { "unit": "page|question", "from": 0, "to": 0 },
      "correct": null, "attempted": null, "focus": null,
      "memo": "", "entryMode": "timer|manual",
      "deleted": false
    }],
    "mistakes": [{
      "id": "", "createdAt": "", "updatedAt": "",
      "sessionId": "uuid|null", "examId": "uuid|null", "materialId": "uuid|null", "subjectId": "uuid|null",
      "questionRef": "", "memo": "", "reason": "knowledge|misread|careless|confusion|other|null",
      "deleted": false
    }],
    "reviewResults": [{ "id": "", "mistakeId": "", "result": "ok|ng", "reviewedAt": "" }],
    "quotaStatus":   [{ "id": "", "quotaId": "", "status": "done|partial|skipped", "updatedAt": "" }]
  },
  "includedIds": ["このパッケージに含めた全レコードのID"]
}
```
- `records` の4つの配列はすべて必須（空配列可）。
- `includedIds` には、`sessions`・`mistakes`・`reviewResults`・`quotaStatus` の**全レコードの `id` を過不足なく**入れる。母艦は取り込み時にこの一致を検証し、食い違えばパッケージを拒否する。
- `quotaStatus` にも `id`（UUID）を持たせる（A-1）。`quotaId` は業務キーであり、母艦は `quotaId` 単位で採用判定を行う（第4章の処理5）。子機の取り込み済み判定（第5章）は `id` で行う。
- `unclassified: true` の記録は、資格・参考書・分野のIDが空でもよい。母艦側で分類し直す。
- **`unclassified: false` の場合は `examId` が必須**（非null）（B-2）。`unclassified: false` かつ `examId` が無い／`null` の組み合わせはスキーマ違反とする。`materialId`・`subjectId` は常に `null` 可。
- `mistakes` には `unclassified` を持たせない。`examId` が `null`、または母艦の知らないIDであれば未分類として扱う。
- 子機では新しい資格・参考書・分野を作成しない。
- `deleted: true` は、子機で「記録の取り消し」をした場合に使う（母艦側で削除扱いにする）。
- `focus`（集中度）は **1〜5の整数、または `null`**（B-3）。
- `sessions[].range` は **省略可・`null` 可**（B-4）。指定する場合は `from <= to`（アプリ側で検証）。
- `startedAt` と `endedAt` は `entryMode` によらず必須（B-5）。手動記録で所要時間だけを入力した場合は、子機が `endedAt = startedAt + activeSeconds` として補って送る。
- **日をまたぐ記録の帰属**：`startedAt` の学習日（`dayChangeHour` 適用）に集計する（B-6）。
- `reviewResults` は追記専用で、子機では編集・削除しない。そのため `updatedAt` を持たない（A-2）。

### 母艦が上りパッケージを受け取ったときの処理（冪等）
1. 検証する。同じ `packageId` を処理済みでも、エラーにせず再処理してよい（結果は変わらない）
2. レコードごとに、IDで照合して追加または更新する。**更新は、受信した `updatedAt` が母艦側の記録より新しい場合だけ**行う。母艦で編集済みの記録は上書きしない
3. `reviewResults` は、IDで重複を除いて追記し、復習スケジュールを再計算する。未知の `mistakeId` を参照する結果（子機で作られた誤答に対する復習など）も保留せず受け入れる
4. `quotaStatus` は、`quotaId` ごとに `updatedAt` が新しい方を採用する
5. 未知のマスタIDを参照している記録は、未分類として受け入れる（拒否しない）
6. 処理した `packageId` と取り込み日時を記録し、次に作る下りパッケージの `acks` に含める
7. 取り込み結果（追加・更新・スキップの件数、未分類の件数）を表示する

## 5. 子機のデータ保持と削除
- 子機は、各上りパッケージについて `packageId` → `includedIds` の対応と、送った時刻を保持する
- `acks` に含まれる `packageId` の `includedIds` に該当するレコードは「取り込み済み」とする。ただし、**そのレコードの `updatedAt` が送信時刻より後なら、未取り込みのまま**にする（送信後に編集されたため）
  - 同じレコードが複数のパッケージに含まれている場合は、**ackされたいずれかのパッケージについて `updatedAt <= 送信時刻` が成り立てば取り込み済み**とする
  - `reviewResults` は `updatedAt` を持たないため、この編集判定を行わず、ackされた時点で無条件に取り込み済みとする（A-2）
- 取り込み済みのレコードは、閲覧専用の履歴として、**取り込み済みになった時刻から7日間**表示し、その後に物理削除する（B-7）
- 未取り込みのレコードは自動では削除しない。最古の未取り込みレコードが3日を超えたら、ホーム画面で送信を促す
- **今週の勉強時間の表示**（A-5）：子機は「母艦から受け取った `summary.weekTotalSeconds`」＋「**未ack**の `sessions` の `activeSeconds`（`deleted: true` を除く）」で表示する。「未送信」ではなく「未ack」を基準にすること。母艦の集計に入った記録は同じ下りパッケージでackされるため、二重計上にならない。

## 6. 転送手段
| 方向 | 手段 | 内容 |
|---|---|---|
| 下り | QRコード | `lite`。JSON → deflate-raw圧縮 → base64url → 先頭に `SL1:` を付ける。**`SL1:` を含む最終文字列のバイト数（UTF-8）が1,800を超える場合はQRを使わず**、ファイルでの転送を案内する。QRの誤り訂正レベルは M 固定 |
| 下り | ファイル | `full`。ファイル名は `studylog-down-YYYYMMDD-HHmm-{packageId先頭8桁}.json`。母艦は同期フォルダの `outbox/` にも保存する |
| 下り | テキスト貼り付け | QR用の文字列（`SL1:...`）をコピー＆ペーストする。予備の手段。この経路にはバイト数上限を課さない |
| 上り | ファイル | ファイル名は `studylog-up-{deviceName}-YYYYMMDD-HHmm-{packageId先頭8桁}.json`。子機は共有シートでGoogleドライブの `StudyLog/inbox/` に保存する。母艦はそのフォルダを監視して自動で取り込み、取り込み後は `processed/` に移動する（検証に失敗したものは `rejected/`） |

- プレフィックスの数字は `schemaVersion` と連動する（`schemaVersion: 2` なら `SL2:`）（B-9）
- **ファイル名の規則**（B-10）：`{deviceName}` は、英数字・ひらがな・カタカナ・漢字・ハイフン・アンダースコアのみを残し、それ以外（`/ \ : * ? " < > |` や空白を含む）を `_` に置換し、20文字までに切り詰める。空になった場合は `device` とする。末尾の `{packageId先頭8桁}` により、同じ分内に複数回送信しても衝突しない
- 受信側はファイル名に依存せず、必ず中身の `kind`・`packageId` で判断する

## 7. 変更の管理
- 項目の追加で、既存の受信側が無視しても安全なもの：`schemaVersion` は据え置き、本書に追記する
- 意味や必須項目の変更：`schemaVersion` を上げ、変換規則を本書に書く
- 変更履歴を本書の末尾に記録する

## 付録A. v1.1 での裁定一覧
実装着手前に検出した矛盾・曖昧点と、その裁定。

| 番号 | 論点 | 裁定 | 反映先 |
|---|---|---|---|
| A-1 | `quotaStatus` にIDが無いのに `includedIds` はID必須 | `quotaStatus` に `id` を追加。ack判定は `id`、母艦の採用判定は `quotaId` | 第4章 |
| A-2 | `reviewResults` に `updatedAt` が無いのに第5章が要求 | 追記専用と割り切り、編集判定を行わない | 第4章・第5章 |
| A-3 | 下りの `quotaStatus` 引き継ぎと「未取り込みは消さない」の衝突 | `quotaStatus` は下りでは削除しない | 第3章 |
| A-4 | QRのみだと `masters` を一度も持てない | 未所持時は「未分類」のみ選択可＋ファイル受信を案内 | 第3章 |
| A-5 | 今週の勉強時間の二重計上／過少計上 | 「未送信」ではなく「未ack」を加算 | 第5章 |
| B-1 | 省略された配列の扱い | キー無し＝維持、`[]`/`null`＝クリア（`acks` は対象外） | 第3章 |
| B-2 | `unclassified: false` のときのID必須性 | `examId` 必須（非null） | 第4章 |
| B-3 | `focus` の値域 | 1〜5の整数または `null` | 第4章 |
| B-4 | 上り `sessions[].range` の省略可否 | 省略可・`null` 可 | 第4章 |
| B-5 | 手動記録の `startedAt`/`endedAt` | 両方必須。子機が補完して送る | 第4章 |
| B-6 | 日をまたぐ記録の帰属 | `startedAt` の学習日 | 第4章 |
| B-7 | 「7日間表示」の起点 | 取り込み済みになった時刻 | 第5章 |
| B-8 | `acks` の「直近30日」の基準 | 母艦が取り込んだ日時から30日 | 第3章 |
| B-9 | QRの1,800バイトの数え方 | `SL1:` 込みの最終文字列のUTF-8バイト数。誤り訂正レベルM | 第6章 |
| B-10 | ファイル名の衝突と不正文字 | deviceName をサニタイズ、末尾に packageId 先頭8桁 | 第6章 |
| B-11 | 復習の重複回答 | 未ackの `reviewResults` がある `mistakeId` は子機で非表示 | 付録B |
| B-12 | `reviews[].labels` の型ゆれ | `material`・`subject` は `null` 可に統一 | 第3章 |

## 付録B. JSON Schema で表現できない制約（両側のアプリで検証すること）
1. `range.from <= range.to`
2. `includedIds` と `records` 内の全 `id` の集合が一致すること
3. `startedAt <= endedAt`、`activeSeconds <= (endedAt - startedAt)`
4. `correct <= attempted`（どちらも非nullのとき）
5. `subjects[].parentId` は2階層まで（親の親を持たない）
6. `schemaVersion` が受信側より新しい場合の「更新が必要」案内（スキーマ上は `const: 1`）
7. 子機は、未ackの `reviewResults` がある `mistakeId` を復習一覧に表示しない（B-11）
8. QR用文字列のバイト数上限（1,800）

## 変更履歴
- v1：初版
- v1.1（2026-09-20）：実装着手前の明確化。付録Aの裁定17件を反映。`quotaStatus` に `id` を追加、`records` の4配列を必須化、`includedIds` の一致検証を追加、ファイル名に packageId 先頭8桁を追加。`schemaVersion` は 1 のまま。
