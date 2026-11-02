# ED GALACTIC MEMOIR

> **Your Flight Log, Your Legacy.**
> 
> *「FSSだけして過ぎ去ったあの星系は、どんな星系だっただろう？ いつ訪れただろう？」*
> 
> FSSの奥に置き忘れてきた星々を、もう一度手のひらに。
> かつて駆け抜けた宙域の記録を呼び覚ます、あなたの航路日誌です。
> ジャーナルの奥底に眠っていた旅のログを掘り起こし、過去の探査履歴や観測データを鮮明に可視化します。

[![Version](https://img.shields.io/badge/version-v0.9.0-orange.svg)](https://github.com/SuzuneYonaki/ED_GALACTIC_MEMOIR/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

[日本語](#日本語) | [English](#english)

---

<a name="日本語"></a>
## 概要 (日本語)

**ED GALACTIC MEMOIR** は、宇宙シミュレーションゲーム『Elite Dangerous』のフライトジャーナルログ（`Journal.*.log`）をリアルタイムに自動解析・監視し、星系構造の可視化、探査価値の精密算出、Exobiology（生体スキャン）予測、採掘支援、天体物理レア度スコア、銀河極値到達記録、天体ブックマーク・メモ機能を提供する**ローカルファースト型デスクトップGUIアプリケーション**です。

---

### ⚠️ アップデート・データ移行と安全性に関するお知らせ

- **旧実行ファイル（`ED_Journal_Analyzer.exe`）の扱い**:
  - 本バージョンより実行ファイル名が **`ED_GALACTIC_MEMOIR.exe`** に変更されました。
  - 以前の実行ファイル（`ED_Journal_Analyzer.exe`）は削除して問題ありません。
- **データフォルダ（`data/`）の扱いとデータベース再構築**:
  - `data/` フォルダ（SQLiteデータベース `elite_journal.db` 等）は、**削除しても構いません**。
  - `data/` を削除した場合でも、次回起動時にゲームのJournalフォルダからフライトログを再解析してデータベースを自動的に再生成します（※独自に登録した天体ブックマークや個人メモを引き継ぎたい場合は、そのまま残しておくことを推奨します）。
- **フライトジャーナルに対する完全な読み取り専用（Read-Only）安全設計**:
  - 本アプリケーションは、Elite Dangerous本体の `Journal` フォルダ（フライトログファイル群）を**完全な読み取り専用（Read-Only）**としてのみ参照します。
  - **ゲーム本体が生成した元のJournalファイルに対して、変更・書き込み・削除などの操作を行うことは一切ありません**。安心してお使いいただけます。

---

### 🛡️ 設計思想：ローカルファースト & コミュニティ連携

- **完全ローカル完結・プライバシー保護**:
  フライトジャーナルログ、CMDRの航跡、所持金・搭乗船データ、天体メモ、ブックマーク等は、すべて**あなたのPC上のローカルSQLiteデータベースのみ**に保存されます。常時通信や強制アップロード、アカウント登録等は一切不要です。
- **コミュニティ知見のオンデマンド照会**:
  必要に応じて、EDSMやSpanshから天体物理データや環ホットスポット（Hotspots）、惑星採掘地点（PML）をオンデマンド照会・補完できます。未訪問星系には誤スキャン混入防止のための安全保護画面を完備しています。
- **多彩な探査データ共有 (CMDR Data Share)**:
  自力で探査・観測した成果は、スタンドアロンHTML、観測データを内包したComfyUI方式PNGカード、Twitch/SNS向けテキスト短評として自由に外部へ共有・復元できます。
- **アドオンによる機能の取捨選択**:
  EDSM/Spansh連携、TTS音声読み上げ、探査データ共有、天体物理レア度スコア、生体種予測は独立したアドオンとして設計されており、設定画面の「🧩 アドオン」タブから必要な機能だけを個別に有効化できます。

---

### 🚀 主な機能 (Core Features)

1. **リアルタイム・フライトログ解析 & 航行トラッキング**:
   - ジャンプイン、Honk（FSS）、DSS、着陸、生体スキャンを完全自動トラッキング。
   - 記録開始から現在地までの**累計ジャンプ距離（ly）**およびジャンプ回数をヘッダーに常時表示（ツールチップで初期星系からの直線距離も算出）。
   - FSSスキャン価値、DSSマッピング価値（効率ボーナス含む）、初回発見ボーナス（×2.6）、初回マッピングボーナスを精密算出。
2. **🌌 旅の到達点 (Your Galactic Reach / 旧・銀河極値)**:
   - 記録を競うのではなく、これまでの航海と思い出を振り返るための到達点ビュー。
   - Sol (0, 0, 0) を原点とした、CMDR自身が実際に探査・訪問した限界境界（**北端 +Z**、**南端 -Z**、**東端 +X**、**西端 -X**、**天頂 +Y**、**天底 -Y**、および **Sol直線最遠到達点**）をカード一覧表示。ワンクリックで当時の詳細ログへ即座にフォーカス・確認が可能です。
3. **🟢 グリーンガスジャイアント (GGG) 完全検知・保護**:
   - FSSスキャン時のCodexEntryイベントを解析し、該当星系内の真のガスジャイアント天体に正確に紐付け。
   - Systemマップでの確定GGGアイコン＆バッジ描画、ヘッダー統計での確定GGGカウント集計に対応。
4. **📡 一部DSS（部分マッピング）フィルター**:
   - 星系内の一部の天体のみDSS完了しており、未マッピングの天体が残っている星系をワンクリックで抽出する「一部DSS」検索バッジ＆カードバッジ表示。
5. **多重連星系対応 Orrery & 軌道階層ツリー**:
   - 恒星・惑星・衛星の階層親子ツリー構造、多重連星系共通重心（Barycentre）、周連星惑星（`AB 1` 等）、周回恒星（`A 1`, `B 1` 等）、特殊命名天体を正確な軌道順で描画。
   - 自由な拡大縮小（0.12x〜40x）・ドラッグ操作に対応したインタラクティブ星系儀（Orrery）。
6. **Exobiology（植物・菌類）解析 & 報酬予測**:
   - 大気組成・表面温度・重力・天体種別から生息可能性のある植物/菌類候補と通常報酬＋初回採取5倍ボーナス額を自動算出。規定の必要コロニー離隔距離（m）やサンプリング進行状況も常時表示。
7. **多段階カウント対応の高度な星系フィルター & 柔軟なUIレイアウト**:
   - 天体数・恒星数による多段階下限指定フィルター、GGG、一部DSS、重力フィルターを網羅。
   - 左右ペインの開閉・ドラッグ幅調整・折りたたみ、2段カラム時の検索＆ソート格納に対応。
8. **天体ブックマーク・エイリアス（別名）・Markdownメモ帳**:
   - 天体単位でのブックマーク登録、ユーザー定義通称（エイリアス）、リアルタイムプレビュー対応のMarkdownメモ（独立アコーディオン表示、永続化対応）。

---

### 📖 画面の見方・指標ガイド (Reading System Cards & Indicators)

星系カードや詳細画面ヘッダーに表示される各種天体物理指標の見方です：

- **⚖️ 質量表示（M☉: 太陽質量）**:
  - 表示例: `⚖️ 1.05 / 1.42 M☉`（主星質量: 1.05 M☉ / 星系総質量: 1.42 M☉）
  - **`M☉`（ソーラーマス / 太陽質量）** とは、太陽1個分の質量（約 $1.989 \times 10^{30}$ kg）を `1.0 M☉` とする天文学の標準単位です。
  - 「太陽何個分の重さ（質量）がある星系か」を直感的に把握できます（主星質量に加え、星系内に存在する全恒星およびガス惑星等の質量が合算されます）。
- **⏳ 星系年齢（Stellar Age）**:
  - 表示例: `45億年`、`9.96億年`、`4,500万年`（英語UIでは天文学の標準単位 `Myr` = Million Years / 百万年）。
  - 主星（中心星）の観測データに基づく、星系誕生からの推定経過年数です。
- **🌌 ボクセル平均星系年齢 & サンプル数（Voxel Avg System Age & Sample Size）**:
  - 表示例: `ボクセル平均星系年齢: 45億年 (n=21星系)`
  - **空間ボクセル（100光年立方）**: Elite Dangerous の星系命名規則（PGアルゴリズム）における空間単位グリッド（100光年四方）です。
  - **平均星系年齢**: その空間ボクセル内でこれまでにCMDR自身が観測・記録した近隣星系の平均年齢です。
  - **`n=...`（サンプル数）**: この平均値の集計母数となった観測星系のサンプル数を表します（例: `n=21星系` は21星系の観測データに基づく平均値）。



<a name="english"></a>
## Overview (English)

**ED GALACTIC MEMOIR** is a local-first desktop GUI application for *Elite Dangerous* that automatically monitors and analyzes your flight journal logs (`Journal.*.log`) in real time. It visualizes star system architecture, accurately calculates exploration values, predicts Exobiology payouts, assists planetary mining, scores astrophysical rarity, tracks galactic boundary records, and manages celestial bookmarks and notes.

> **Your Flight Log, Your Legacy.**
> 
> *Retrieve forgotten stars beyond the FSS back into your hands. Awaken the memory of every sector you once traversed.*

---

### ⚠️ Important Notice on Update, Data Migration & Journal Safety

- **Old Executable (`ED_Journal_Analyzer.exe`)**:
  - The executable has been officially renamed to **`ED_GALACTIC_MEMOIR.exe`**.
  - You can safely delete the old executable (`ED_Journal_Analyzer.exe`).
- **Data Directory (`data/`) & Automatic DB Reconstruction**:
  - You **can safely delete the `data/` directory** if desired.
  - If deleted, the app will automatically rebuild the entire local database from your game Journal logs on the next launch (Note: Keep `data/` if you wish to preserve custom celestial bookmarks and personal Markdown notes).
- **Zero-Modification Read-Only Safety Architecture**:
  - The application accesses Elite Dangerous's `Journal` directory in **strict Read-Only mode**.
  - **It will NEVER modify, overwrite, append to, or delete any of your original game journal files.**

---

### 🚀 Key Features

1. **Real-time Journal Tracking & Jump Distance**:
   - Automatic tracking of jumps, Honks, DSS mapping, touchdowns, and bio scans.
   - Cumulative jump distance (ly) and jump count displayed in header with origin straight-line distance tooltip.
2. **🌌 Your Galactic Reach (Journey Boundaries)**:
   - Designed to cherish memories of your personal journey rather than a sterile leaderboard.
   - Highlights the furthest boundary systems reached relative to Sol (0, 0, 0): **North (+Z)**, **South (-Z)**, **East (+X)**, **West (-X)**, **Zenith (+Y)**, **Nadir (-Y)**, and **Farthest Euclidean Distance**, with instant focus and inspection.
3. **🟢 Confirmed Green Gas Giant (GGG) Detection**:
   - Flawlessly resolves FSS CodexEntry events to genuine gas giant bodies. Badges confirmed GGGs in the System Map and tallies cumulative counts in header statistics.
4. **📡 Partial DSS Filter**:
   - Instantly filter systems where only a portion of bodies have been mapped, leaving unmapped targets behind.
5. **Hierarchical System Map & Interactive Orrery**:
   - Accurate orbital hierarchy, barycentres, circumbinary planets, and custom-named celestial bodies with smooth zoom and pan controls.
6. **Exobiology Predictions & High-Value Alerts**:
   - Calculates species candidates, base value, and First Discovery 5x bonus.

---

### 📖 Reading System Cards & Indicators

- **⚖️ Mass Badges (`M☉`: Solar Mass)**:
  - Example: `⚖️ 1.05 / 1.42 M☉` (Main Star Mass: 1.05 M☉ / System Total Mass: 1.42 M☉)
  - **`M☉` (Solar Mass)** is the standard astronomical unit of mass, equal to the mass of our Sun (approx. $1.989 \times 10^{30}$ kg). It lets you immediately grasp the gravitational weight of a system compared to our own Sun.
- **⏳ Stellar Age**:
  - Formatted in `Myr` (Million Years) in English, and in `億年` / `万年` in Japanese. Indicates the estimated age elapsed since the main star's formation.
- **🌌 Voxel Average System Age & Sample Size (`n=...`)**:
  - Example: `Voxel Avg System Age: 4,500 Myr (n=21 systems)`
  - **Spatial Voxel**: The 100-light-year cubic grid defined by Elite Dangerous's procedural star naming system.
  - **Average System Age**: The mean stellar age calculated from neighboring systems logged in your local journal within that 100 ly voxel.
  - **`n=...` (Sample Count)**: The number of logged systems used to compute the average (e.g. `n=21 systems` means an average across 21 observed systems).



## 🛠️ インストール & 実行方法 (Installation & Usage)

### 方式 1: 配布バイナリ（推奨・インストール不要）
1. [GitHub Releases](https://github.com/SuzuneYonaki/ED_GALACTIC_MEMOIR/releases) より最新の `ED_GALACTIC_MEMOIR.exe` をダウンロード。
2. 任意のフォルダに配置してダブルクリックで起動します。
   - ※ 以前のバージョンをお使いの方は、従来のフォルダ内に `ED_GALACTIC_MEMOIR.exe` を配置してください（旧 `ED_Journal_Analyzer.exe` は削除可。`data/` は削除しても再構築されますが、個人メモ等を残したい場合は保持推奨）。

### 方式 2: Python ソースコードからの実行
```bash
git clone https://github.com/SuzuneYonaki/ED_GALACTIC_MEMOIR.git
cd ED_GALACTIC_MEMOIR
pip install -r requirements.txt
python run.py
```

---

## 📄 License
This project is licensed under the [GNU General Public License v3.0 (GPLv3)](https://www.gnu.org/licenses/gpl-3.0).
