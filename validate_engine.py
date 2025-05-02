import json
import os
import importlib.util
import sys
from pathlib import Path
import filecmp
import copy  # deepcopy を使うため
import csv  # CSV読み込み用
import logging

# --- ロギング設定 ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 定数設定 (絶対パスを使用) ---
TEMPLATE_A_DIR = Path("/Users/mbp/Movies/CapCut/User Data/Projects/com.lveditor.draft/TemplateA") # ユーザー指定
OLD_HANDLER_PATH = Path().cwd() / "capcut_handler_old.py" # 旧ハンドラはワークスペース内と仮定
NEW_HANDLER_MODULE = "ccbp.core.capcut_handler"
CSV_DATA_PATH = Path("/Users/mbp/Movies/CapCut/sample_batch_sheet.csv") # ユーザー指定
OUTPUT_DIR = Path().cwd() / "validation_output" # 一時的な出力先 (ワークスペース内)
OUTPUT_DIR.mkdir(exist_ok=True)

# --- 検証用設定 (ユーザー指定の値を使用) ---
TEMPLATE_MATERIAL_BASE = "/Users/mbp/Movies/CapCut/CCBP_WorkSpace/TemplateMaterial/TemplateA" # ユーザー指定
CHANGE_MATERIAL_BASE = "/Users/mbp/Movies/CapCut/CCBP_WorkSpace/ChangeMaterial" # ユーザー指定

# --- ヘルパー関数: モジュールをパスから読み込む ---
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for module {module_name} from {file_path}")
    module = importlib.util.module_from_spec(spec)
    # sys.modules[module_name] = module # グローバルに登録しない方が安全な場合も
    spec.loader.exec_module(module)
    return module

# --- ヘルパー関数: CSVから指定IDの行を取得 ---
def get_csv_row_by_id(csv_path, target_id):
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f: # utf-8-sig でBOM対応
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('id') == str(target_id):
                    # 数値に変換できるものは変換してみる（オプション）
                    # for key, value in row.items():
                    #     try:
                    #         row[key] = int(value)
                    #     except (ValueError, TypeError):
                    #         try:
                    #             row[key] = float(value)
                    #         except (ValueError, TypeError):
                    #             pass # Keep as string
                    return row
    except FileNotFoundError:
        logger.error(f"CSVファイルが見つかりません: {csv_path}")
    except Exception as e:
        logger.error(f"CSV読み込みエラー: {e}", exc_info=True)
    return None

# --- メイン処理 ---
def run_validation():
    logger.info("検証を開始します...")

    # --- CSVデータ取得 ---
    target_row_id = 1 # まずは1行目で検証
    logger.info(f"CSVファイル '{CSV_DATA_PATH}' から ID={target_row_id} のデータを読み込みます。")
    csv_row_data = get_csv_row_by_id(CSV_DATA_PATH, target_row_id)
    if not csv_row_data:
        logger.error(f"ID={target_row_id} のCSVデータが見つかりませんでした。検証を中止します。")
        return
    logger.info(f"使用するCSVデータ: {csv_row_data}")

    # --- 元のプロジェクトデータ読み込み ---
    logger.info(f"元のプロジェクトデータを読み込み中: {TEMPLATE_A_DIR}")
    try:
        with open(TEMPLATE_A_DIR / "draft_meta_info.json", 'r', encoding='utf-8') as f:
            meta_data_orig = json.load(f)
        with open(TEMPLATE_A_DIR / "draft_info.json", 'r', encoding='utf-8') as f:
            draft_data_orig = json.load(f)
    except Exception as e:
        logger.error(f"プロジェクトデータ読み込みエラー: {e}", exc_info=True)
        return

    # 新しいプロジェクト名を取得 (CSVから)
    new_project_name = csv_row_data.get("ProjectName", TEMPLATE_A_DIR.name + "_validated")

    # --- 元のロジック実行 ---
    logger.info(f"\n--- 元のロジック ({OLD_HANDLER_PATH.name}) を実行 ---")
    old_meta_path = OUTPUT_DIR / f"output_old_meta_{target_row_id}.json"
    old_draft_path = OUTPUT_DIR / f"output_old_draft_{target_row_id}.json"
    try:
        # 元の CapcutHandler を動的に読み込む
        OldHandlerModule = load_module_from_path("capcut_handler_old", OLD_HANDLER_PATH)

        # 元のデータで処理 (コピーを渡す)
        meta_data_old = copy.deepcopy(meta_data_orig)
        draft_data_old = copy.deepcopy(draft_data_orig)

        # 古いハンドラの初期化 (引数をユーザー指定に合わせる)
        old_handler = OldHandlerModule.CapcutHandler(
            project_path=str(TEMPLATE_A_DIR), # この検証では元のパスでOK
            template_material_base=TEMPLATE_MATERIAL_BASE,
            change_material_base=CHANGE_MATERIAL_BASE
        )
        # データをハンドラにセット (古い実装によっては不要かも)
        old_handler.meta_data = meta_data_old
        old_handler.draft_data = draft_data_old

        # 古いハンドラの処理メソッドを呼び出す
        old_handler.update_project_name(new_project_name)
        old_handler.update_material_paths(csv_row_data) # パス更新
        old_handler.replace_text_placeholders(csv_row_data) # テキスト置換

        # 結果を取得して保存
        processed_meta_old = old_handler.meta_data
        processed_draft_old = old_handler.draft_data
        with open(old_meta_path, 'w', encoding='utf-8') as f:
            json.dump(processed_meta_old, f, ensure_ascii=False, indent=4)
        with open(old_draft_path, 'w', encoding='utf-8') as f:
            json.dump(processed_draft_old, f, ensure_ascii=False, indent=4)
        logger.info(f"元のロジックの結果を保存しました:\n  {old_meta_path}\n  {old_draft_path}")

    except Exception as e:
        logger.error(f"元のロジック実行中にエラーが発生しました: {e}", exc_info=True)
        # エラーが発生しても新しいロジックの検証は試みる

    # --- 新しいロジック実行 ---
    logger.info(f"\n--- 新しいロジック ({NEW_HANDLER_MODULE}) を実行 ---")
    new_meta_path = OUTPUT_DIR / f"output_new_meta_{target_row_id}.json"
    new_draft_path = OUTPUT_DIR / f"output_new_draft_{target_row_id}.json"
    try:
        # 新しい CapcutHandler をインポート
        NewHandlerModule = importlib.import_module(NEW_HANDLER_MODULE)

        # 元のデータで処理 (コピーを渡す)
        meta_data_new = copy.deepcopy(meta_data_orig)
        draft_data_new = copy.deepcopy(draft_data_orig)

        # 新しいハンドラの初期化 (デフォルトのルール設定を使う)
        # mapping_config_path はデフォルトを使用
        new_handler = NewHandlerModule.CapcutHandler(project_path=str(TEMPLATE_A_DIR))
        # データをハンドラにセット
        new_handler.meta_data = meta_data_new
        new_handler.draft_data = draft_data_new

        # 新しいハンドラの処理メソッドを呼び出す
        new_handler.update_project_name(new_project_name)
        new_handler.update_material_paths(
             csv_row_data,
             template_material_base=TEMPLATE_MATERIAL_BASE,
             change_material_base=CHANGE_MATERIAL_BASE
        ) # パス更新とテキスト置換を同時に行う

        # 結果を取得して保存
        processed_meta_new = new_handler.meta_data
        processed_draft_new = new_handler.draft_data
        with open(new_meta_path, 'w', encoding='utf-8') as f:
            json.dump(processed_meta_new, f, ensure_ascii=False, indent=4)
        with open(new_draft_path, 'w', encoding='utf-8') as f:
            json.dump(processed_draft_new, f, ensure_ascii=False, indent=4)
        logger.info(f"新しいロジックの結果を保存しました:\n  {new_meta_path}\n  {new_draft_path}")

    except Exception as e:
        logger.error(f"新しいロジック実行中にエラーが発生しました: {e}", exc_info=True)
        return # 新しいロジックが失敗したら比較はできない

    # --- 結果比較 ---
    logger.info("\n--- 結果の比較 ---")
    try:
        meta_match = filecmp.cmp(old_meta_path, new_meta_path, shallow=False)
        draft_match = filecmp.cmp(old_draft_path, new_draft_path, shallow=False)

        logger.info(f"draft_meta_info.json の比較結果: {'一致' if meta_match else '不一致'}")
        logger.info(f"draft_info.json の比較結果: {'一致' if draft_match else '不一致'}")

        if not meta_match or not draft_match:
            logger.warning("差分が見つかりました。以下のファイルを確認してください:")
            if not meta_match:
                logger.warning(f"  - {old_meta_path}")
                logger.warning(f"  - {new_meta_path}")
            if not draft_match:
                logger.warning(f"  - {old_draft_path}")
                logger.warning(f"  - {new_draft_path}")
            # ここで diff コマンドを実行するなどの詳細比較も可能
            # try:
            #     if not meta_match:
            #         os.system(f"diff -u {old_meta_path} {new_meta_path}")
            #     if not draft_match:
            #         os.system(f"diff -u {old_draft_path} {new_draft_path}")
            # except Exception as diff_e:
            #     logger.error(f"diffコマンドの実行に失敗: {diff_e}")
        else:
            logger.info("両方のファイルが一致しました。基本的な互換性は保たれています。")

    except FileNotFoundError:
        logger.error("比較対象のファイルが見つかりません。両方のロジックが正常に完了したか確認してください。")
    except Exception as e:
        logger.error(f"結果比較中にエラーが発生しました: {e}", exc_info=True)

    logger.info("\n検証が完了しました。")

if __name__ == "__main__":
    logger.info("="*20 + " 検証スクリプト開始 " + "="*20)
    # --- 実行前に確認 (ユーザー指定のパスを確認) ---
    if not OLD_HANDLER_PATH.exists():
        logger.error(f"エラー: 元のハンドラファイルが見つかりません: {OLD_HANDLER_PATH}")
    elif not TEMPLATE_A_DIR.exists():
        logger.error(f"エラー: テンプレートディレクトリが見つかりません: {TEMPLATE_A_DIR}")
    elif not Path(CHANGE_MATERIAL_BASE).exists(): # ChangeMaterial も確認
        logger.error(f"エラー: 差し替え素材ベースディレクトリが見つかりません: {CHANGE_MATERIAL_BASE}")
    elif not Path(TEMPLATE_MATERIAL_BASE).exists(): # TemplateMaterial も確認
        logger.error(f"エラー: テンプレート素材ベースディレクトリが見つかりません: {TEMPLATE_MATERIAL_BASE}")
    elif not CSV_DATA_PATH.exists():
        logger.error(f"エラー: CSVファイルが見つかりません: {CSV_DATA_PATH}")
    else:
        run_validation()
    logger.info("="*20 + " 検証スクリプト終了 " + "="*20) 