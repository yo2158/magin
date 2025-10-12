# MAGIN - Multi-AI Governance Interfaces Node

**3つのAIに同時に意見を聞ける意思決定支援ツール**

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

---

## 🎬 デモ

![MAGIN Demo](img/demo.gif)

## 📖 何ができるか

MAGINは、**3つのAIに同時に質問**し、それぞれの判断を比較できるWebアプリケーションです。

### 主な特徴

- **3AI並列判定**: 異なる3つのAIが独立して判断
- **ペルソナシステム**: 定義済みの複数種類のペルソナから各AIの個性を選択可能
- **意見の可視化**: 各AIの判定結果、重大度スコア、懸念点を表示
- **判定履歴の保存**: 過去の判定をデータベースに保存、後から確認可能
- **複数エンジン設定**: Gemini API、Claude CodeなどのCLIエージェント、OpenRouter、Ollama対応

### 判定の仕組み

MAGINは、各AIが 4つの観点（妥当性・実現可能性・リスク・情報確実性）とペルソナ毎の判断基準、重大度に応じた判定テーブルで最終結果を決定します。

**判定フロー**:
1. 各AIが4観点スコアリングとペルソナごとの基準に応じて判断
2. ハードフラグチェック（コンプライアンス・セキュリティ・プライバシー）
3. 重大度別判定テーブル適用
4. 最終判定（承認/条件付き承認/否決）

> 📘 **詳細な判定ロジック**: [判定ロジック解説](docs/judgment-logic.md)をご覧ください

### 使用例

- 「ワークライフバランスのため週休3日制を導入すべき」
- 「IT企業では従業員の満足度向上や労働環境改善のため全社的にリモートワークを導入すべき」
- 「経営者は物価高に対応して、賃金を十分に上げるべきである」

---

## ⚠️ 前提条件

このツールを動かすには以下いずれかが必要です。

- **Gemini APIキー**利用可能（無料～）
- **Gemini CLI**利用可能（無料～）
- **Claude Code**利用可能プラン契約済み（月額$20～）
- **ChatGPT Plus**以上でCodex CLI利用可能（月額$20〜）
- **OpenRouter APIキー**利用可の(有料、モデルは一部無料あり)
- **Ollamaサーバ**利用可能(対応モデルダウンロード必要)

これらを準備できる方は多くないことは理解しています。
実験的なプロジェクトとして楽しんでいただければ幸いです。

## 🚀 セットアップ

### 動作確認済み環境

- **OS**: Ubuntu 24.04 LTS
   - Windows 11(WSL)、MacOSは動作未確認です（動く可能性はあります）
- **Python**: 3.10以上（開発環境: Python 3.13.5）
- **ブラウザ**: Chrome, Edge (最新版推奨)

**その他の要件**:
- Git インストール済み
- Python 3.10以上

### ⚡ クイックスタート

#### 前提条件
- **Git** インストール済み
- **Python 3.9以上** インストール済み

#### 1. APIキー取得
1. https://aistudio.google.com/apikey にアクセス
2. 「Create API Key」をクリック
3. APIキーをコピー（後で使います）

#### 2. セットアップ
```bash
# リポジトリをクローン
git clone https://github.com/yo2158/magin.git
cd magin

# 仮想環境作成（推奨）
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存パッケージをインストール
pip install -r requirements.txt

# サーバー起動
python -m backend.app
```

#### 3. ブラウザでアクセス

http://localhost:8000 を開く

#### 4. APIキー設定

1. 画面右上の 「API SETTING」 をクリック
2. Gemini API Key に先ほどコピーしたキーを貼り付け
3. SAVE をクリック

#### 5. 接続テスト

1. 「TEST」 ボタンをクリック
2. 全て ✅ SUCCESS になることを確認

#### 6. 実行

1. 議題を入力（例: 「リモートワークを全社導入すべきか？」）
2. 「START JUDGMENT」 をクリック
3. 3つのAIの判定結果を確認

---

## 🎭 ペルソナシステム

MAGINでは、各AIに定義済みの複数種類のペルソナから個性を選択できます。

### ペルソナの例

- **neutral_ai（中立的なAI）**: バランスの取れた視点で客観的に判断
- **researcher（研究者）**: 論理的・慎重・データ重視
- **mother（母親）**: 保守的・安全性重視・家族優先
- **woman（女性）**: バランス重視・共感的

...など

> ペルソナの種類は [全ペルソナ一覧](docs/personas.md)をご覧ください

### ペルソナの設定方法

1. ヘッダーの「CONFIG」ボタンをクリック
2. 各AIのドロップダウンからペルソナを選択
3. 「SAVE」で設定を保存（設定はセッション間（ブラウザ閉じるまで）保持されます）

ペルソナによって判定結果が大きく変わることがあります。

---

## ⚠️ 注意事項

### AI判定の精度について

- 3つのAIが生成する判定は自動生成されます
- 判定結果はあくまで参考情報としてご利用ください

### コストについて

- Gemini API: 無償枠はあるものの設定によっては有料となる点に注意
- Claude Code: Claude Pro/Team/API課金が必要
- Gemini CLI: 個人Googleアカウントで無料利用可能（1日1000リクエストまで）
- Codex CLI: ChatGPT Plus以上が必要
- OpenRouter: 基本有料のクレジット購入でのAPIキー作成が前提

各サービスの利用規約と料金プランは公式サイトでご確認ください。

### APIキーの保存について

**重要: セキュリティに関する注意事項**

MAGINでは、API設定画面から入力されたAPIキーを、ローカル環境の `.env` ファイルに**平文（暗号化されていないテキスト）** で保存します。

**MAGINはローカル環境での個人利用を想定して設計されています。本番環境での使用は推奨しません。**

### 免責事項

このツールの判定結果について、開発者は一切の責任を負いません。

---

## 📁 プロジェクト構造

```
magin/
├── backend/           # バックエンド（FastAPI）
│   ├── app.py         # FastAPIアプリケーション
│   ├── models.py      # データモデル
│   ├── magi_orchestrator.py  # AI並列実行
│   ├── severity_judge.py      # 判定ロジック
│   ├── db_manager.py  # データベース操作
│   ├── config.py      # 設定管理
│   ├── config_manager.py  # 設定マネージャー
│   ├── ai_factory.py  # 統合AIインターフェース
│   └── personas.json  # ペルソナ定義
│
├── frontend/          # フロントエンド
│   ├── index.html     # メインUI
│   ├── script.js      # JavaScript
│   ├── style.css      # スタイル
│   ├── favicon.ico    # ファビコン
│   └── sounds/        # サウンドエフェクト
│       ├── judgement_start.mp3   # 判定開始音
│       ├── node_verdict.mp3      # AI判定完了音
│       └── final_verdict.mp3     # 最終判定音
│
├── config/            # 設定ファイル
│   ├── user_config.json.default  # デフォルト設定テンプレート
│   └── user_config.json  # ユーザー設定（Git管理対象外、初回起動時に自動作成）
│
├── data/              # データベース
│   └── judgments.db   # 判定履歴（SQLite）
│
├── docs/              # ドキュメント
│   ├── judgment-logic.md  # 判定ロジック解説
│   └── personas.md         # ペルソナ一覧
│
├── img/               # 画像
│   ├── demo.gif
│   └── judgment-flow.png
│
├── requirements.txt   # 依存パッケージ
├── LICENSE            # MITライセンス
└── README.md          # このファイル
```

---

## 🔧 技術スタック

- **Python 3.10+**: プログラミング言語
- **FastAPI**: WebフレームワークとAPI
- **SQLite**: データベース
- **Vanilla JavaScript**: フロントエンド
- **Claude Code**: Anthropic Claude
- **Gemini CLI**: Google Gemini
- **Codex CLI**: OpenAI ChatGPT

---

## 🛠️ トラブルシューティング

### Python 3.10がインストールされていない

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install python3.10 python3.10-venv python3-pip
```

**macOS (Homebrew)**:
```bash
brew install python@3.10
```

**Windows**: [Python公式サイト](https://www.python.org/downloads/)からダウンロード

### Node.js 20がインストールされていない

**nvm使用（推奨）**:
```bash
nvm install 20
nvm use 20
```

**公式サイト**: [Node.js公式](https://nodejs.org/)

### ポート8000が使用中

別のポートで起動:
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8001
```

### TESTに失敗する

#### Gemini APIの場合

**よくある原因と対処法**:

1. **APIキーが無効**
   - Google AI Studio (https://aistudio.google.com/apikey) でAPIキーを確認
   - APIキーが有効化されているか確認
   - 新しいAPIキーを作成して再設定

2. **APIキーの入力ミス**
   - コピー時に余分なスペースが入っていないか確認
   - APIキー全体が正しくコピーされているか確認（先頭・末尾の切れに注意）

3. **APIの利用制限**
   - 無料枠を使い切っている可能性があります
   - Google AI Studio でクォータ（利用制限）を確認
   - 課金設定を確認（無料枠のみの場合は制限あり）

4. **地域制限**
   - 一部の国・地域ではGemini APIが利用できません
   - VPN経由でアクセスしている場合は解除してみてください

5. **ネットワーク接続**
   - インターネット接続を確認
   - ファイアウォール設定を確認（`aistudio.google.com`への接続を許可）

**エラーメッセージ別の対処**:
- `401 Unauthorized`: APIキーが無効 → 再発行して設定し直す
- `403 Forbidden`: 地域制限またはAPIが無効化されている
- `429 Too Many Requests`: レート制限（1分待ってから再試行）
- `500 Internal Server Error`: Google側の一時的な問題（時間を置いて再試行）

#### 各エージェントCLIの場合
各CLIを単体で起動して、ブラウザログインが完了しているか確認:
```bash
claude  # Claudeログイン確認
gemini  # Geminiログイン確認
codex   # Codexログイン確認
```

---

## 📄 ライセンス

このプロジェクトはMITライセンスで公開されています。
詳細は [LICENSE](LICENSE) ファイルを参照してください。

---

## 📞 質問・不具合報告

[Issues](https://github.com/yo2158/magin/issues) まで

---
