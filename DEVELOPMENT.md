# CapCutBatchProcessor 開発ドキュメント

## 1. プロジェクト概要

**CapCutBatchProcessor** は、CapCutのプロジェクトファイルに対して一括処理を行うためのデスクトップアプリケーションです。
ライセンス認証機能を持ち、正規のユーザーのみが利用できるように制御されています。

**主要機能:**

*   指定されたフォルダ内の CapCut プロジェクトファイルに対する一括処理（具体的な処理内容は別途定義）
*   オンラインおよびオフラインキャッシュによるライセンス認証
*   設定管理（API URL、秘密鍵、キャッシュパスなど）

## 2. 技術スタック

*   **プログラミング言語:** Python 3.12
*   **GUIフレームワーク:** PySide6 (Qt for Python)
*   **ビルドツール:** Nuitka
*   **依存関係管理:** Setuptools (`pyproject.toml`)
*   **ライセンス認証バックエンド:** Google Apps Script (GAS)
*   **主要ライブラリ:**
    *   `requests`: HTTPリクエスト (ライセンス認証API通信)
    *   `cryptography`: 暗号化 (Fernetによるキャッシュ暗号化)
    *   `python-dotenv`: 環境変数管理 (`.env` ファイルの読み込み)
    *   `PySide6`: GUIフレームワーク (LGPLv3 ライセンスに注意)
    *   `platformdirs`: プラットフォーム依存のディレクトリパス取得 (設定/キャッシュ保存用)
*   **Linter/Formatter:** Ruff
*   **テストフレームワーク:** Pytest
*   **CI/CD (Windowsビルド):** GitHub Actions

## 3. ディレクトリ構造

主要なディレクトリ構成は以下の通りです。（詳細は `@directorystructure.mdc` を参照）

```
. (Project Root)
├── .github/workflows/      # GitHub Actions ワークフロー
├── .venv/                  # Python 仮想環境 (Git管理外)
├── assets/                 # アイコン、画像、ffmpegなどの静的リソース
│   ├── icons/
│   └── ...
├── ccbp/                   # メインのソースコードパッケージ
│   ├── controllers/        # アプリケーションロジック、イベント処理
│   ├── models/             # データ構造、ビジネスロジック (LicenseManager, ConfigManager)
│   ├── views/              # UIコンポーネント、レイアウト
│   ├── utils/              # ユーティリティ (Logging, Constants)
│   ├── resources/          # アプリケーションリソース (例: 設定ファイルテンプレート)
│   ├── core/               # コア機能 (PathMappingEngine, CapcutHandler)
│   │   ├── path_mapping_engine/
│   │   └── ...
│   ├── __init__.py
│   └── ...
├── doc/                    # ドキュメント
├── gas/                    # Google Apps Script (ライセンス認証API)
│   └── license_api.gs
├── nuitka_dist/            # Nuitkaビルド出力 (ローカルmacOS, Git管理外)
├── nuitka_dist_windows/    # Nuitkaビルド出力 (GitHub Actions Windows, Git管理外)
├── scripts/                # 補助スクリプト (ビルド準備など)
│   └── prepare_build.py
├── tests/                  # テストコード
├── .env.example            # 環境変数設定のテンプレート
├── .gitignore              # Git管理対象外ファイル/ディレクトリ指定
├── CapCutBatchProcessor.spec # (旧)PyInstaller設定ファイル (現在は利用していない)
├── config.json             # ビルド時に生成される設定ファイル (Nuitkaに同梱)
├── main.py                 # アプリケーションエントリーポイント
├── pyproject.toml          # プロジェクト設定、依存関係定義
├── README.md               # プロジェクトの基本的な説明
└── ...
```

## 4. セットアップ手順

1.  **リポジトリのクローン:**
    ```bash
    git clone <repository_url>
    cd CCBP
    ```
2.  **Python 仮想環境の作成と有効化:**
    ```bash
    python3 -m venv .venv
    # macOS/Linux
    source .venv/bin/activate
    # Windows (Command Prompt)
    # .\.venv\Scripts\activate.bat
    # Windows (PowerShell)
    # .\.venv\Scripts\Activate.ps1
    ```
3.  **依存関係のインストール:**
    ```bash
    # pip を最新化
    python -m pip install --upgrade pip
    # プロジェクトと開発依存をインストール
    python -m pip install -e .[dev]
    ```
4.  **.env ファイルの設定:**
    `.env.example` をコピーして `.env` ファイルを作成し、以下の環境変数を設定します。
    *   `LICENSE_API_URL`: ライセンス認証API (GAS) のデプロイメントURL
    *   `LICENSE_FERNET_KEY`: キャッシュファイル暗号化用のFernetキー (Base64エンコードされた32バイト)
    *   **Fernetキーの生成:** `.env` に設定するキーがない場合、以下のスクリプトで生成できます。
        ```python
        # generate_fernet_key.py
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        print(key.decode())
        ```
        ```bash
        python generate_fernet_key.py
        ```
    *   `.env` ファイルは **絶対にGit管理しないでください**。

## 5. 主要コンポーネント

*   **`main.py`**: アプリケーションのエントリーポイント。`AppController` を初期化し、アプリケーションを開始します。
*   **`ccbp/controllers/app_controller.py`**: アプリケーション全体のライフサイクル、ビューとモデル間の調整、メインウィンドウの管理を行います。
*   **`ccbp/views/`**: PySide6 を使用したUIコンポーネント（ウィンドウ、ダイアログ、カスタムウィジェットなど）が含まれます。
*   **`ccbp/controllers/`**: 各機能（ライセンス認証、設定、バッチ処理など）の具体的なロジックやUIイベントハンドリングを担当します。
    *   `license_controller.py`: ライセンス認証UIのイベント処理、`LicenseManager` の呼び出し。
    *   `settings_controller.py`: 設定画面の制御、`ConfigManager` へのアクセス。
    *   `batch_controller.py`: バッチ処理画面の制御（未実装部分含む）。
*   **`ccbp/models/`**: データ構造やコアなビジネスロジックを実装します。
    *   `license_manager.py`: オンライン/オフラインでのライセンス認証、キャッシュ管理、署名検証、有効期限チェック。
    *   `config_manager.py`: 設定ファイル (`config.json`) の読み込み、書き込み、デフォルト値の管理、シークレットの暗号化/復号（現在はビルド時暗号化は未使用）。
*   **`ccbp/utils/`**: プロジェクト全体で利用される共通機能を提供します。
    *   `logging_config.py`: アプリケーションのログ設定。
    *   `constants.py`: 定数定義。
*   **`gas/license_api.gs`**: Google Apps Script で実装されたライセンス認証API。ライセンスキーの検証、署名生成、有効期限管理などを行います。

## 6. 設定管理 (`config.json`)

*   アプリケーションの設定はビルド時に `.env` から自動生成される `config.json` で管理されます。
*   **ビルド時の同梱:**
    *   **macOS:** `build_macos.sh` 実行時に `.env` から `config.json` が自動生成され、バンドルに同梱されます。
    *   **Windows:** GitHub ActionsでSecretsから `config.json` が自動生成され、バンドルに同梱されます。
*   **手動で `config.json` を編集・管理する必要はありません。**

## 7. ライセンス認証

*   **認証フロー:** アプリケーション起動時およびユーザーによる認証操作時に実行されます。
    1.  まずオンライン認証を試行 (`LicenseManager._check_online`)。
        *   GAS API (`LICENSE_API_URL`) にライセンスキーを送信。
        *   APIはキーを検証し、有効期限、ステータス、タイムスタンプ、応答署名、永続署名を返す。
        *   Python側で応答タイムスタンプ、応答署名、永続署名を検証 (`LICENSE_SECRET_KEY` を使用)。
    2.  オンライン認証成功時:
        *   取得したライセンス情報 (キー、有効期限、最終チェック時刻など) をキャッシュファイル (`license_cache.dat`) に暗号化して保存 (`LicenseManager._save_cache`)。
        *   認証成功をユーザーに通知。
    3.  オンライン認証失敗時 (ネットワークエラーなど): オフライン認証を試行 (`LicenseManager._check_offline`)。
        *   キャッシュファイル (`license_cache.dat`) を復号して読み込み (`LicenseManager._load_cache`)。
        *   キャッシュ内のライセンスキー、有効期限、最終チェック時刻からの経過日数 (オフライン許容期間) を検証。
        *   検証成功ならオフライン認証成功。
*   **キャッシュ:**
    *   ファイル名: `license_cache.dat`
    *   保存場所: `config.json` 内の `cache_path` で指定されたディレクトリ。
    *   暗号化: Fernet (`cryptography` ライブラリ) を使用。暗号化/復号キーは `config.json` 内の `fernet_key`。
*   **署名:**
    *   HMAC-SHA256 を使用。
    *   秘密鍵は `config.json` 内の `license_secret_key`。
    *   GAS API 側と Python 側で同じデータと秘密鍵を使って署名を計算し、比較検証。
*   **Secrets:** GitHub Actions でのビルド時には、以下の Secrets が必要です。
    *   `LICENSE_API_URL`
    *   `LICENSE_FERNET_KEY`

## 8. ビルド

アプリケーションの配布には Nuitka を使用します。

*   **macOS (ローカルビルド):**
    1. `.env` を用意し、必要な環境変数を記載
    2. `bash build_macos.sh` を実行（.envからconfig.jsonが自動生成され、バンドルに同梱）
    3. `nuitka_dist_macos/CCBP.app` を起動
    - App Bundle形式のみ対応。`--onepackage`/`--onefile`は未サポート。
*   **Windows (GitHub Actions):**
    *   Workflowファイル: `.github/workflows/windows_build.yml`
    *   Secretsから `config.json` を自動生成し、バンドルに同梱
    *   Nuitkaでビルドし、成果物をArtifactとしてアップロード
    *   `nuitka_dist_windows/main.dist/` 以下の実行ファイル一式が成果物
    - 手動ビルドは推奨されません。CI経由で成果物をダウンロードしてください。

## 9. コーディングルールと Git ガイドライン

*   **コーディングルール:** Python の標準的な慣習 (PEP 8) に従います。詳細は `@codingrules.mdc` を参照してください。Linter/Formatter として Ruff を使用しています。
*   **Git ガイドライン:** コミットメッセージは日本語で記述します。ブランチ運用やコミット手順については `@gitrules.mdc` を参照してください。

## 10. テスト

*   テストフレームワークとして Pytest を使用しています。
*   テストコードは `tests/` ディレクトリに配置します。
*   テスト実行:
    ```bash
    # 仮想環境を有効化
    source .venv/bin/activate
    # テスト実行
    pytest
    ```
*   (注: 現在のテストカバレッジやテストケースの詳細は、`tests/` ディレクトリの内容を確認してください。)

## 11. 注意点

*   **Secrets の管理:** APIキーやFernetキーは機密情報です。`.env` ファイルやSecretsは**絶対にGitリポジトリにコミットしないでください**。
*   **`LICENSE_SECRET_KEY` は不要になりました。**
*   **エラーハンドリング:** ファイルIO、ネットワーク通信、ライセンス検証関連のエラーは、ユーザー体験向上のために継続的に改善が必要です。
*   **GAS API のデプロイ:** `gas/license_api.gs` を変更した場合、Google Apps Script エディタで新しいバージョンをデプロイする必要があります。
*   **ビルド成果物:**
    - macOS: `nuitka_dist_macos/CCBP.app`
    - Windows: `nuitka_dist_windows/main.dist/` 以下の実行ファイル一式
*   **ビルド方式:**
    - macOSはApp Bundle形式のみ。`--onepackage`/`--onefile`は未サポート。
    - Windowsはstandalone形式でビルドされます。

## 12. 内部実装の詳細

*   **パス・テキスト置換エンジンのリファクタリング:** 以前は `capcut_handler.py` 内に直接記述されていた素材パスやテキストプレースホルダの置換ロジックを、設定ファイル駆動型の `PathMappingEngine` (`ccbp/core/path_mapping_engine/`) として分離・再実装しました。
    *   これにより、置換ルール (`path_rules`, `text_rules`) を `ccbp/config/path_mapping_rules.json` (ビルド時に同梱) で柔軟に設定・拡張できるようになりました。
    *   ルール適用の優先度や対象キー (`target_keys`) の指定などが可能です。
    *   デフォルトのテキストルールは、`##キー##` 形式 (material_map 由来) と `{{キー}}` 形式 (CSV 由来) をサポートします。
*   **パフォーマンス改善:**
    *   バッチ処理開始ボタン押下から実際の処理開始までのタイムラグを調査し、CSV 読み込み前に UI フィードバックを表示するように改善しました。
    *   CapCut プロジェクトファイル (`draft_info.json`) 内の `content` キー（内部に JSON 文字列を含む）の処理がボトルネックとなっていたため、ルール設定 (`json_content_keys`) を調整し、`content` キーの内容を再帰的に解析しないように変更することで、特に要素数の多いプロジェクトでの処理速度を大幅に改善しました。
*   **UI応答性の改善 (バッチ処理開始時):**
    *   バッチ処理ボタンクリック直後のUIフリーズを解消するため、`BatchController.run_batch_processing` の役割を、即時のUIフィードバック（ボタン無効化、ステータス更新）と `QTimer.singleShot(0, self._start_worker_thread)` の呼び出しのみに限定しました。
    *   従来 `run_batch_processing` 内で行っていた処理（パス取得、`LicenseManager` や `BatchWorker` のインスタンス化、シグナル接続、スレッド開始など）は、新設した `_start_worker_thread` メソッドに移動しました。これにより、時間のかかる可能性のある処理がUIスレッドをブロックする時間を最小限に抑えています。
    *   ライセンスチェックやパス検証など、従来UIスレッドの一部で行われていた処理も `BatchWorker` の `run` メソッドの先頭に移動し、完全にバックグラウンドスレッドで実行されるようにしました。
    *   *(注: `json_content_keys` による `content` キーの再帰解析抑制に関する記述は、現状の `path_mapping_rules.json` と異なる可能性があるため削除しました。必要に応じて再検証してください。)*

---

*このドキュメントは {YYYY-MM-DD} 時点の情報に基づいています。プロジェクトの進捗に合わせて適宜更新してください。* 

## .envファイル例

```
LICENSE_API_URL=https://script.google.com/macros/s/xxx/exec
LICENSE_FERNET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx==
``` 