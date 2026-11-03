# ED GALACTIC MEMOIR

> **Your Flight Log, Your Legacy.**
> 
> *「FSSだけして過ぎ去ったあの星系は、どんな星系だっただろう？ いつ訪れただろう？」*
> 
> FSSの奥に置き忘れてきた星々を、もう一度手のひらに。
> かつて駆け抜けた宙域の記録を呼び覚ます、あなたの航路日誌です。
> ジャーナルの奥底に眠っていた旅のログを掘り起こし、過去の探査履歴や観測データを鮮明に可視化します。

[![Version](https://img.shields.io/badge/release-v0.9.0--initial-orange.svg)](https://github.com/SuzuneYonaki/ED_GALACTIC_MEMOIR/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

[日本語説明書](#日本語) | [English Manual](#english)

---

<a name="日本語"></a>
## 概要 (日本語)

**ED GALACTIC MEMOIR** は、宇宙シミュレーションゲーム『Elite Dangerous』のフライトジャーナルログ（`Journal.*.log`）を自動解析・監視し、星系構造の階層ツリー可視化、探査価値の精密算出、Exobiology（生体スキャン）予測、採掘支援、天体物理レア度スコア、旅の到達点記録、天体ブックマーク・メモ機能を提供する**ローカルファースト型デスクトップGUIアプリケーション**です。

膨大なフライトログの中に埋もれていた「あの日の旅」を、直感的かつ美しいグラフィックで呼び覚まします。

---

### 🛡️ 3大安心設計（ローカル・安全・復元性）

1. **完全ローカル完結・プライバシー保護**:
   - フライトジャーナルログ、CMDRの航行履歴、所持金、搭乗船、天体メモ、ブックマーク等は、すべて**あなたのPC上のローカルSQLiteデータベースのみ**に保存されます。
   - 外部サーバーへの常時通信、アカウント登録、強制アップロード等は一切行いません。
2. **フライトジャーナルに対する完全な読み取り専用（Read-Only）安全設計**:
   - 本アプリケーションは、Elite Dangerous本体の `Journal` フォルダ（ログファイル群）を**完全な読み取り専用（Read-Only）**としてのみ参照します。
   - **ゲーム本体が生成したオリジナルのログファイルに対して、変更・上書き・追記・削除を行うことは一切ありません**。いつでも安心してお使いいただけます。
3. **安全で自由なデータベース自動再構築**:
   - `data/` フォルダ（SQLiteデータベース `elite_journal.db` 等）は、いつでも削除して再生成させることができます。
   - 初回起動時やリセット時でも、ゲームのJournalフォルダからフライトログを全自動で再解析し、データベースを自動復元します（※独自に登録した天体ブックマークや個人メモを引き継ぎたい場合は、`data/` フォルダをそのまま保持してください）。

---

### 🚀 主要機能 (Core Features)

1. **リアルタイム・フライトログ自動解析 & 航海トラッキング**:
   - ジャンプイン、Honk（FSS）、DSSマッピング、惑星着陸、生体スキャンを完全自動リアルタイム解析。
   - **累計ジャンプ距離（ly）** と総ジャンプ回数をヘッダーに常時表示（クリックで単位切替可能）。
   - FSSスキャン価値、DSSマッピング価値（効率ボーナス対応）、初回発見ボーナス（×2.6）、初回マッピングボーナスを精密算出。
2. **🌌 旅の到達点 (Your Galactic Reach)**:
   - 誰かと記録を競うのではなく、**「自分自身がどこまで遠く、高く、深く旅をしてきたか」** という航海の思い出を振り返るための到達点ビュー。
   - Sol (0, 0, 0) を原点とした、CMDR自身が訪れた銀河の最遠境界（**銀盤北端 +Z**、**銀盤南端 -Z**、**銀盤東端 +X**、**銀盤西端 -X**、**銀盤天頂 +Y**、**銀盤天底 -Y**、および **Sol直線最遠到達点**）をカード一覧表示。カードをクリックすると対象星系の詳細ログへ即座にフォーカスします。
3. **🟢 グリーンガスジャイアント (GGG) 完全検知・保護**:
   - FSSスキャン時のCodexEntryイベントを解析し、星系内の真のガスジャイアント天体に正確に紐付け。
   - 星系マップでの確定GGGアイコン＆バッジ描画、ヘッダー統計での確定GGGカウント集計に対応。
4. **📡 一部DSS（部分マッピング）抽出フィルター**:
   - 星系内の一部の高価値天体のみDSS完了しており、未マッピング天体が残されている星系をワンクリックで抽出する「一部DSS」フィルター＆バッジ表示。
5. **多重連星系対応 Orrery（星系儀）& 軌道階層ツリー**:
   - 恒星・惑星・衛星の階層親子ツリー構造、多重連星系共通重心（Barycentre）、周連星惑星（`AB 1` 等）、周回恒星（`A 1`, `B 1` 等）、特殊命名天体を正確な軌道順で忠実に描画。
   - 自由な拡大縮小（0.12x〜40x）・スムーズなパン操作に対応したインタラクティブOrrery。
6. **🌱 Exobiology（植物・菌類）解析 & 報酬予測**:
   - 大気組成・表面温度・重力・天体種別から生息可能性のある植物/菌類候補と通常報酬＋初回採取5倍ボーナス額を自動算出。
   - 規定の必要コロニー離隔距離（m）やサンプリング進行状況もリアルタイム表示。
7. **柔軟なレスポンシブUI & 多段階フィルター**:
   - ウィンドウ幅やペイン幅に応じて星系カードが美しく引き伸ばされるレスポンシブ設計（1カラム・2カラム表示対応）。
   - 2カラムモード時、閲覧エリアを最大化するための「検索・絞り込み」および「並び替え」コントロールの折りたたみトグルボタンを完備。
   - 天体数・恒星数による多段階下限指定フィルター、重力フィルター、訪問日時範囲指定（今年・昨年・指定期間）に対応。
8. **天体ブックマーク・エイリアス（別名）・Markdownメモ帳**:
   - 天体単位でのブックマーク登録、ユーザー定義通称（エイリアス）、リアルタイムプレビュー対応のMarkdownメモ（独立アコーディオン表示、自動永続化）。
9. **多彩な探査データ共有 (CMDR Data Share)**:
   - 自力で探査・観測した成果を、スタンドアロンHTMLファイル、観測データを画像内に内包したComfyUI方式PNGカード（本アプリにドラッグ＆ドロップで復元可能）、Twitch/SNS向けテキスト短評として出力可能。

---

### 📖 画面の見方・指標ガイド (Reading System Cards & Indicators)

星系カードや詳細画面ヘッダーに表示される各種指標・数値の見方です：

#### 1. ⚖️ 質量表示（M☉: 太陽質量）
- **表示例**: `⚖️ 1.05 / 1.42 M☉`（主星質量: 1.05 M☉ / 星系総質量: 1.42 M☉）
- **意味**:
  - **`M☉`（ソーラーマス / 太陽質量）** とは、天文学で恒星や星系の重さを表す世界標準の質量単位です。太陽1個分の質量（約 $1.989 	imes 10^{30}$ kg）を `1.0 M☉` と定義しています。
  - 「太陽何個分の質量があるか」を直感的に把握できます（主星質量に加え、星系内に存在する全恒星およびガス惑星等の質量が合算されます）。
  - マスバッジにマウスカーソルを合わせると、詳細な内訳ツールチップが表示されます。

#### 2. ⏳ 星系年齢（Stellar Age）
- **表示例**: `45億年`、`9.96億年`、`4,500万年`（英語UIでは天文学の標準単位 `Myr` = Million Years / 百万年）
- **意味**:
  - 主星（中心恒星）の観測データに基づく、星系誕生からの推定経過年数です。
  - 日本語環境では、天文学用語に不慣れな方でも直感的に理解できるよう「億年」「万年」単位に自動換算して表示されます。

#### 3. 🌌 ボクセル平均星系年齢 & サンプル数
- **表示例**: `ボクセル平均星系年齢: 45億年 (n=21星系)`
- **意味**:
  - **空間ボクセル（100光年立方）**: Elite Dangerous の星系命名規則（PGアルゴリズムのセクターおよびマスコード構造）に基づく、空間の100光年立方グリッドです。
  - **平均星系年齢**: その同一空間ボクセル内でこれまでにCMDR自身が観測・記録した近隣星系の平均年齢です。近隣の恒星形成時期や星団の傾向を把握する目安になります。
  - **`n=...`（サンプル数）**: 平均値の算出母数となった観測星系のサンプル数を表します（例: `n=21星系` は、あなたが過去に訪れて記録された21星系の観測データに基づく平均値です。統計的な信頼性を持たせるため、2星系以上の記録がある場合にのみ表示されます）。

#### 4. 📏 累計ジャンプ距離（Total Jump Distance）のクリック単位切替
- **表示例**: `Total Jumps: 1,248 (285.4 kly)`
- **操作**:
  - ヘッダーのジャンプ距離部分をクリックするたびに、表示単位が **`ly`（光年） ➔ `kly`（千光年） ➔ `Mly`（百万光年） ➔ `Gly`（十億光年）** へとサイクル切り替えされます。
  - ツールチップには、記録開始地点（初回星系）からの直線距離も同時に表示されます。

#### 5. 🌌 天体物理レア度スコア (Astrophysical Rarity Score)
- **意味**:
  - 単なる探査売却額（クレジット価値）だけでなく、超巨星、ブラックホール、中性子星、ウォルフ・ライエ星、希少大気天体、特殊軌道関係などの天体物理学的な希少性を総合スコアリング。
  - 左ペインのデフォルトソートは「🌌 天体物理レア度 (高い順)」に設定されており、これまでの旅で出会った最も神秘的な星系を即座に見つけ出せます。

#### 6. ⚡ LIVE 追従モード
- **操作**:
  - ヘッダー左上の `LIVE` ボタンをクリックして `LIVE ON`（緑点灯）にすると、ゲームプレイ中のジャーナルログ追加をリアルタイム監視し、新星系へジャンプした瞬間に自動で画面が最新星系へと追従します。
  - `LIVE ON` 中は、最新訪問順を崩さないよう安全にソート固定されます。

---

### 🧩 アドオン機能 (Addon Ecosystem)

設定画面（右上の ⚙️ アイコン）の「🧩 アドオン」タブから、必要に応じて以下の機能を個別に有効化・無効化できます：

- **EDSM 手動同期**: 星系詳細画面から、EDSMデータベースの最新情報（天体構成・BGS勢力情報）を手動でオンデマンド取得。
- **Spansh 採掘・天体同期**: Spansh API から環ホットスポット（Hotspots）や惑星採掘地点（PML）を取得。
- **TTS 音声読み上げ**: ジャンプイン時や生体スキャン時に、星系の特徴や生体種名を音声ガイダンス（VOICEVOX / Windows標準音声対応）。
- **CMDR Data Share**: 外部共有用スタンドアロンHTML、ComfyUI方式PNG画像カードの出力機能。
- **天体物理レア度 & 生体種予測**: 科学的レア度スコア算出エンジンおよび大気・温度による生体候補推論エンジン。

---

### 🛠️ インストール & 実行方法 (Installation & Usage)

#### 方式 1: 配布バイナリ（推奨・インストール不要）

1. [GitHub Releases](https://github.com/SuzuneYonaki/ED_GALACTIC_MEMOIR/releases) より配布パッケージ **`ED_GALACTIC_MEMOIR.zip`** をダウンロードします。
2. 任意のフォルダに ZIP を解凍します。
3. 展開された **`ED_GALACTIC_MEMOIR.exe`** をダブルクリックして起動します。
   - ※ インストーラーによるシステム変更やレジストリ登録は一切行いません。解凍するだけでポータブルにお使いいただけます。

#### 方式 2: Python ソースコードからの実行

Python 3.10 以上がインストールされた環境で以下を実行します：

```bash
git clone https://github.com/SuzuneYonaki/ED_GALACTIC_MEMOIR.git
cd ED_GALACTIC_MEMOIR
pip install -r requirements.txt
python run.py
```

---

<a name="english"></a>
## Overview (English)

**ED GALACTIC MEMOIR** is a local-first desktop GUI application for *Elite Dangerous* that automatically monitors and analyzes your flight journal logs (`Journal.*.log`) in real time. It visualizes star system hierarchy trees, accurately calculates exploration values, predicts Exobiology payouts, assists planetary mining, scores astrophysical rarity, tracks personal journey boundaries, and manages celestial bookmarks and notes.

> **Your Flight Log, Your Legacy.**
> 
> *Retrieve forgotten stars beyond the FSS back into your hands. Awaken the memory of every sector you once traversed.*
> Bring the exploration logs sleeping deep in your journals back to vibrant life.

---

### 🛡️ Three Safety Principles (Local, Read-Only, Resilient)

1. **100% Local-First & Privacy Protected**:
   - Flight logs, jump routes, player balance, ship data, celestial notes, and bookmarks remain **strictly inside your local SQLite database**.
   - No forced network traffic, no account registrations, and no telemetry.
2. **Strict Read-Only Access to Game Journals**:
   - The application opens Elite Dangerous `Journal` log files in **strict Read-Only mode**.
   - **It will NEVER modify, overwrite, append to, or delete your original game journal files.**
3. **Resilient Data Directory (`data/`)**:
   - The `data/` folder (local SQLite database `elite_journal.db`) can be safely deleted and reconstructed at any time.
   - On first launch or after a reset, the app automatically re-parses your game journal logs and reconstructs the complete database (Note: Keep `data/` if you wish to preserve custom bookmarks and markdown notes).

---

### 🚀 Key Features

1. **Real-time Journal Tracking & Exploration Values**:
   - Automatic live tracking of jump-ins, Honks, DSS mapping, planet touchdowns, and bio scans.
   - Cumulative jump distance (with interactive unit switching) and jump count displayed in header.
   - Accurate computation of FSS base value, DSS mapping efficiency bonuses, First Discovery bonus (×2.6), and First Mapped bonus.
2. **🌌 Your Galactic Reach (Journey Boundaries)**:
   - Designed to cherish the memories and milestones of your personal journey rather than a sterile leaderboard.
   - Highlights the furthest boundary systems reached relative to Sol (0, 0, 0): **North (+Z)**, **South (-Z)**, **East (+X)**, **West (-X)**, **Zenith (+Y)**, **Nadir (-Y)**, and **Farthest Euclidean Distance**, with instant one-click focus and inspection.
3. **🟢 Confirmed Green Gas Giant (GGG) Detection**:
   - Flawlessly resolves FSS CodexEntry events to genuine gas giant bodies. Badges confirmed GGGs in the System Map and tallies cumulative counts in header statistics.
4. **📡 Partial DSS Filter**:
   - Instantly filter systems where only a portion of high-value bodies have been mapped, leaving unmapped targets behind.
5. **Hierarchical System Map & Interactive Orrery**:
   - Accurate orbital hierarchy, barycentres, circumbinary planets, and custom-named celestial bodies with smooth zoom (0.12x to 40x) and pan controls.
6. **🌱 Exobiology Predictions & High-Value Alerts**:
   - Calculates species candidates from atmosphere, surface temperature, gravity, and planet class.
   - Shows base payout and First Discovery 5x bonus, plus colony distance tracking (m).
7. **Responsive UI & Collapsible Multi-Stage Filters**:
   - Automatically stretches system cards responsively to fit 1-column or 2-column viewports.
   - Collapsible search and sort controls in 2-column mode to maximize viewing area.
   - Multi-tier body and star count filters, gravity filters, and date range presets (All Time, This Year, Last Year, Custom).
8. **Celestial Bookmarks & Markdown Notebook**:
   - Per-body bookmarking, custom aliases, and Markdown notes with live preview and persistent storage.
9. **CMDR Data Share**:
   - Export standalone Web Share HTML files, ComfyUI-style embedded PNG image cards (drag-and-drop to restore in app), and stream/social text snippets.

---

### 📖 Reading System Cards & Indicators

- **⚖️ Mass Badges (`M☉`: Solar Mass)**:
  - Example: `⚖️ 1.05 / 1.42 M☉` (Main Star Mass: 1.05 M☉ / System Total Mass: 1.42 M☉)
  - **`M☉` (Solar Mass)** is the standard astronomical unit of mass, equal to the mass of the Sun (approx. $1.989 \times 10^{30}$ kg). It lets you immediately grasp the gravitational scale of a system compared to our own Sun.
  - Hovering over the mass badge displays a detailed breakdown tooltip.
- **⏳ Stellar Age**:
  - Formatted in `Myr` (Million Years) in English, and in `億年` / `万年` in Japanese. Indicates the estimated age elapsed since the main star's formation.
- **🌌 Voxel Average System Age & Sample Count (`n=...`)**:
  - Example: `Voxel Avg System Age: 4,500 Myr (n=21 systems)`
  - **Spatial Voxel**: The 100-light-year cubic grid defined by Elite Dangerous's procedural star naming system.
  - **Average System Age**: The mean stellar age calculated from neighboring systems logged in your local journal within that 100 ly voxel.
  - **`n=...` (Sample Count)**: The number of logged systems used to compute the average (e.g. `n=21 systems` means an average across 21 observed systems).
- **📏 Cumulative Jump Distance (Interactive Unit Cycling)**:
  - Click the jump distance badge in the header to cycle units between **`ly` ➔ `kly` ➔ `Mly` ➔ `Gly`**.
  - The tooltip displays the straight-line Euclidean distance from your journey's origin system.
- **🌌 Astrophysical Rarity Score**:
  - Evaluates astrophysical rarity (supergiants, black holes, neutron stars, Wolf-Rayet stars, exotic atmospheres, unique orbital configurations) beyond mere credit values.
  - The left pane defaults to primary sorting by "🌌 Astrophysical Rarity (Desc)".
- **⚡ LIVE Tracking Mode**:
  - Toggle `LIVE ON` in the header to automatically monitor your journal during gameplay and follow new systems as you jump in.

---

### 🛠️ Installation & Usage

#### Method 1: Pre-built Binary (Recommended, No Installation Required)

1. Download the release package **`ED_GALACTIC_MEMOIR.zip`** from [GitHub Releases](https://github.com/SuzuneYonaki/ED_GALACTIC_MEMOIR/releases).
2. Extract the ZIP archive to any folder.
3. Double-click **`ED_GALACTIC_MEMOIR.exe`** to launch.
   - Completely portable with zero system modifications.

#### Method 2: Running from Python Source

Requires Python 3.10+:

```bash
git clone https://github.com/SuzuneYonaki/ED_GALACTIC_MEMOIR.git
cd ED_GALACTIC_MEMOIR
pip install -r requirements.txt
python run.py
```

---

## 📄 License
This project is licensed under the [GNU General Public License v3.0 (GPLv3)](https://www.gnu.org/licenses/gpl-3.0).
