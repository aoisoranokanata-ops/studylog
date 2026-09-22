# 同梱ライブラリ

| ファイル | 内容 | ライセンス |
|---|---|---|
| `jsQR.js` | [jsQR](https://github.com/cozmo/jsQR) v1.4.0（UMD版・未改変） | Apache License 2.0, (c) Cozmo |

- 外部CDNを使わない方針のため、ここに同梱している。
- iOS の Safari は `BarcodeDetector` に対応していないため、QRコードの読み取りに jsQR を使う。
- 読み込みはQR読み取り画面を開いたときだけ（`js/views/qr-scan.js`）。初回表示を重くしないため。
- JSの容量の目安（100KB）には含めない（子機の指示書による）。
