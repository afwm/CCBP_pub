from .config_manager import (
    ConfigManager,
    KEY_LICENSE_KEY, 
    KEY_LICENSE_STATUS,
    KEY_LICENSE_EXPIRES,
    KEY_LICENSE_VALIDATED_AT,
    KEY_LICENSE_LAST_MESSAGE,
    # --- Trial Period Keys ---
    KEY_INSTALL_DATE,
    KEY_LAST_VALID_DATE,
    KEY_DAILY_BATCH_COUNT,
    KEY_BATCH_COUNT_DATE
    # --- End Trial Period Keys ---
)
import logging
import os
from dotenv import load_dotenv # To load potential secret key from .env
import requests # Import requests library for API calls
from datetime import datetime, date, timezone # Import datetime and date for calculations
import json # Import json for logging

# Load environment variables if using .env for secret key and API details
load_dotenv()

class LicenseManager:
    """Handles license key validation, masking, and status updates via API."""

    def __init__(self, config_manager: ConfigManager):
        self.logger = logging.getLogger(__name__)
        self.config_manager = config_manager
        self.api_url = os.getenv("LICENSE_API_URL")
        self.api_key = os.getenv("LICENSE_SECRET_KEY") # Use LICENSE_SECRET_KEY for the API key

        if not self.api_url:
            self.logger.warning("LICENSE_API_URL environment variable not set. License validation via API will fail.")
        else:
            self.logger.info(f"License validation API URL configured: {self.api_url}")

        if self.api_key:
            self.logger.info("LICENSE_SECRET_KEY found and will be used for validation requests.")
        else:
             self.logger.info("LICENSE_SECRET_KEY not found. Requests will be made without an API key.")

        # Remove Fernet example if not used
        self.logger.info("LicenseManager initialized.")

    def _validate_license_api(self, license_key: str) -> dict | None:
        """
        Internal helper to call the validation API and return the data dict on success.
        Returns the response data dictionary if successful and valid format, otherwise None.
        """
        if not self.api_url:
            self.logger.error("License validation API URL (LICENSE_API_URL) is not configured. Cannot validate key.")
            return None

        params = {'action': 'verify', 'key': license_key}
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}' # Example: Bearer token
            self.logger.debug("API Key added to request headers.")
        else:
            self.logger.debug("No API Key found, sending request without authentication header.")

        try:
            self.logger.debug("Sending license validation request:")
            self.logger.debug(f"  URL: {self.api_url}")
            self.logger.debug("  Method: GET")
            self.logger.debug(f"  Headers: {headers}")
            self.logger.debug(f"  Params: {params}")
            response = requests.get(self.api_url, headers=headers, params=params, timeout=10)
            self.logger.debug(f"API Response Status Code: {response.status_code}")
            self.logger.debug(f"API Response Headers: {response.headers}")
            try:
                response_body_log = response.json()
            except json.JSONDecodeError:
                response_body_log = response.text[:500] + ("..." if len(response.text) > 500 else "")
            self.logger.debug(f"API Response Body: {response_body_log}")
            
            response.raise_for_status()

            if 'application/json' not in response.headers.get('Content-Type', ''):
                 self.logger.error(f"API response was not JSON. Content-Type: {response.headers.get('Content-Type')}")
                 self.logger.error(f"Response text (start): {response.text[:200]}...")
                 return None

            data = response.json()

            if 'error' in data:
                self.logger.warning(f"API returned error for key '{license_key[:8]}...': {data['error']}")
                # --- Update cache on API error --- 
                self._update_license_cache(license_key, None, error_message=data['error'])
                # --- End update --- 
                return None

            if 'status' not in data:
                self.logger.error(f"API response JSON is missing the 'status' key. Data: {data}")
                # --- Update cache on structure error --- 
                self._update_license_cache(license_key, None, error_message="API応答形式エラー")
                # --- End update --- 
                return None

            # --- Update cache on successful validation --- 
            self._update_license_cache(license_key, data)
            # --- End update --- 
            return data

        except requests.exceptions.Timeout as e:
            self.logger.error(f"API call timed out: {e}")
            self._update_license_cache(license_key, None, error_message="APIタイムアウト")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API call failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                 self.logger.error(f"API Response Status: {e.response.status_code}, Body: {e.response.text[:200]}...")
            self._update_license_cache(license_key, None, error_message="API通信エラー")
            return None
        except ValueError as e: # Catch JSON decoding errors
            self.logger.error(f"Failed to decode JSON response: {e}")
            self.logger.error(f"Response text (start): {response.text[:200]}...")
            self._update_license_cache(license_key, None, error_message="API応答解析エラー")
            return None
        except Exception as e:
            self.logger.exception(f"Unexpected error during API validation: {e}")
            self._update_license_cache(license_key, None, error_message="不明なAPIエラー")
            return None

    def _update_license_cache(self, license_key: str, validation_data: dict | None, error_message: str | None = None):
        """Updates the license cache in ConfigManager based on validation result or error."""
        if not self.config_manager:
             return
        
        now_iso = datetime.now(timezone.utc).isoformat()
        status_msg = "エラー"
        status_val = None
        expires_val = None
        
        if validation_data:
            status_val = validation_data.get('status')
            expires_val = validation_data.get('expires')
            status_msg, _ = self.get_status_message_from_data(validation_data) # Use helper to get msg
        elif error_message:
             status_msg = f"確認失敗: {error_message}"
             status_val = 'error' # Indicate error state
        else: # Default case if called unexpectedly
             status_msg = "不明な状態"
             status_val = 'unknown'

        try:
            self.config_manager.set(KEY_LICENSE_KEY, license_key) # Ensure key is saved
            self.config_manager.set(KEY_LICENSE_STATUS, status_val)
            self.config_manager.set(KEY_LICENSE_EXPIRES, expires_val)
            self.config_manager.set(KEY_LICENSE_VALIDATED_AT, now_iso)
            self.config_manager.set(KEY_LICENSE_LAST_MESSAGE, status_msg)
            self.config_manager.save() # Save immediately after update
            self.logger.info(f"License cache updated: Key={license_key[:5]}..., Status={status_val}, Expires={expires_val}, ValidatedAt={now_iso}, Message={status_msg}")
        except Exception as e:
             self.logger.exception(f"Failed to update license cache: {e}")

    def get_cached_status_message(self) -> tuple[str, bool | None, str | None]:
        """
        Retrieves the license status message and validity from the cache.
        Returns: tuple[str, bool | None, str | None]: 
                 Message, Validity (True/False/None), Validated Timestamp (ISO str) or None
        """
        if not self.config_manager:
             return "キャッシュ利用不可", None, None

        license_key = self.config_manager.get(KEY_LICENSE_KEY)
        if not license_key:
            return "未入力", None, None
            
        status = self.config_manager.get(KEY_LICENSE_STATUS)
        # expires = self.config_manager.get(KEY_LICENSE_EXPIRES) # Can be used if needed
        validated_at = self.config_manager.get(KEY_LICENSE_VALIDATED_AT)
        last_message = self.config_manager.get(KEY_LICENSE_LAST_MESSAGE, "未確認")
        
        is_valid = status == 'active'
        
        # Append timestamp to message if available
        if validated_at:
            try:
                # Make timestamp more readable
                dt = datetime.fromisoformat(validated_at).astimezone(None) # Convert to local time
                ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                message = f"{last_message} (@{ts_str})"
            except ValueError:
                message = f"{last_message} (確認日時不明)"
        else:
             message = last_message
             
        return message, is_valid, validated_at

    def get_status_message_from_data(self, validated_data: dict) -> tuple[str, bool]:
        """Helper to generate status message and validity from validated API data."""
        if not validated_data:
             return "確認失敗", False
             
        api_status = validated_data.get('status')
        expires_str = validated_data.get('expires')
        license_key = validated_data.get('license_key', '') # Get key if available

        if api_status == 'active':
            if expires_str == '0000-00-00':
                return "有効 (無期限ライセンス)", True
            else:
                try:
                    expiry_date = datetime.strptime(expires_str, '%Y-%m-%d').date()
                    today = date.today()
                    remaining_days = (expiry_date - today).days
                    if remaining_days < 0:
                        return f"期限切れ ({abs(remaining_days)}日経過)", False # Treat expired as False
                    else:
                        return f"有効 (残り {remaining_days} 日)", True
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid expires date format '{expires_str}' from API for key '{license_key[:8]}...'", exc_info=True)
                    return "有効 (期限情報不正)", True
        else:
            return f"無効 ({api_status if api_status else '不明'})", False

    def get_status_message(self, license_key: str) -> tuple[str, bool | None]:
        """(Online Check) Determines status message and validity by calling API."""
        if not license_key:
            return "未入力", None

        validated_data = self._validate_license_api(license_key)
        # _validate_license_api now handles caching internally
        
        # Use the helper to generate message from potentially updated cache/API data
        message, is_valid = self.get_status_message_from_data(validated_data)
        return message, is_valid

    def is_valid(self, license_key: str) -> bool:
        """
        Checks if the license key is currently considered valid (status == 'active').
        Calls the internal API helper.
        """
        if not license_key:
            return False
        
        validated_data = self._validate_license_api(license_key)
        
        return validated_data is not None and validated_data.get('status') == 'active'

    def get_masked_key(self, license_key: str) -> str:
        """
        Returns a masked version of the license key for display.
        Shows first 4 and last 4 characters.
        """
        if not license_key or len(license_key) < 8:
            return "********" # Or return empty string or original key if short
        
        masked = f"{license_key[:4]}********{license_key[-4:]}"
        return masked 

    # --- Trial and Limitation Methods ---

    def initialize_trial_if_needed(self) -> bool:
        """初回起動時にトライアル開始日を設定。設定された場合はTrueを返す。"""
        install_date = self.config_manager.get(KEY_INSTALL_DATE)
        if not install_date:
            now_iso = datetime.now(timezone.utc).isoformat()
            self.config_manager.set(KEY_INSTALL_DATE, now_iso)
            self.config_manager.set(KEY_LAST_VALID_DATE, now_iso) # 初期値も設定
            self.config_manager.save()
            self.logger.info(f"新規インストール日を記録: {now_iso}")
            return True
        return False

    def get_trial_status(self) -> dict:
        """
        トライアル状態を取得する。
        日付改ざん検出ロジックを含む。
        Returns:
            dict: {
                'in_trial': bool,     # トライアル期間内か
                'days_left': int,     # 残り日数 (マイナスは経過日数)
                'install_date': str | None, # インストール日 (ISO形式)
                'restricted': bool,   # 制限モードか (トライアル外かつライセンス無効)
                'tampered': bool      # 日付改ざんが疑われるか
            }
        """
        install_date_str = self.config_manager.get(KEY_INSTALL_DATE)
        if not install_date_str:
            # まだ初期化されていない場合（通常は発生しないはず）
            return {'in_trial': True, 'days_left': 14, 'install_date': None, 'restricted': False, 'tampered': False}

        try:
            install_date = datetime.fromisoformat(install_date_str)
            now = datetime.now(timezone.utc)
            tampered = False

            # 日付改ざん検出
            last_date_str = self.config_manager.get(KEY_LAST_VALID_DATE)
            if last_date_str:
                last_date = datetime.fromisoformat(last_date_str)
                if now < last_date:
                    self.logger.warning(
                        f"日付改ざんの疑い: 現在時刻 ({now.isoformat()}) が "
                        f"最終確認時刻 ({last_date.isoformat()}) より過去です。"
                    )
                    # 改ざん時は最終確認時刻を現在時刻として扱う
                    now = last_date
                    tampered = True
                else:
                    # 正常ケース - 現在日付を最終有効日として更新
                    self.config_manager.set(KEY_LAST_VALID_DATE, now.isoformat())
                    self.config_manager.save()
            else:
                # last_valid_date がない場合は現在時刻で初期化
                self.config_manager.set(KEY_LAST_VALID_DATE, now.isoformat())
                self.config_manager.save()

            # トライアル期間の計算
            days_passed = (now - install_date).days
            in_trial = days_passed < 14
            days_left = 14 - days_passed # トライアル終了後はマイナスになる

            # ライセンス状態の確認 (キャッシュを使用)
            _, license_valid, _ = self.get_cached_status_message()

            restricted = not in_trial and not license_valid

            return {
                'in_trial': in_trial,
                'days_left': days_left,
                'install_date': install_date_str,
                'restricted': restricted,
                'tampered': tampered
            }
        except (ValueError, TypeError) as e:
            self.logger.error(f"トライアル期間の計算エラー: {e}. 安全のため制限モードとします。", exc_info=True)
            # エラーの場合は制限モードで動作
            return {'in_trial': False, 'days_left': -1, 'install_date': install_date_str, 'restricted': True, 'tampered': False}

    def can_process_batch(self) -> tuple[bool, str]:
        """
        バッチ処理が可能かどうかを判定する。
        Returns:
            tuple[bool, str]: (処理可能かどうか, メッセージ)
        """
        # 1. ライセンスが有効か確認 (APIチェックは is_valid で行われる)
        license_key = self.config_manager.get(KEY_LICENSE_KEY)
        if license_key and self.is_valid(license_key): # is_valid calls API and updates cache
             _, license_valid, _ = self.get_cached_status_message() # Read updated cache
             if license_valid:
                 return True, "ライセンス有効"

        # 2. トライアル状態を確認
        trial_status = self.get_trial_status()
        if trial_status['in_trial']:
            return True, f"トライアル期間内（残り{max(0, trial_status['days_left'])}日）"

        # 3. 制限モード - 1日5件まで
        today_str = date.today().isoformat()
        count_date = self.config_manager.get(KEY_BATCH_COUNT_DATE)
        daily_count = 0

        if count_date != today_str:
            # 日付が変わったのでリセット
            self.config_manager.set(KEY_BATCH_COUNT_DATE, today_str)
            self.config_manager.set(KEY_DAILY_BATCH_COUNT, 0)
            self.config_manager.save()
            self.logger.info(f"バッチ処理カウントをリセットしました ({today_str})")
        else:
            daily_count = int(self.config_manager.get(KEY_DAILY_BATCH_COUNT, 0))

        if daily_count >= 5:
            return False, "本日のバッチ処理上限（5件）に達しました。ライセンスをご購入いただくか、翌日までお待ちください。"
        else:
            remaining = 5 - daily_count
            return True, f"制限モード: 本日残り{remaining}件処理可能"

    def increment_batch_count(self) -> bool:
        """
        バッチ処理のカウントを1増やす。
        トライアル期間外、かつライセンス無効の場合のみカウントする。
        Returns:
            bool: カウントが増加された場合はTrue、それ以外はFalse
        """
        # ライセンス有効またはトライアル期間中はカウント不要
        _, license_valid, _ = self.get_cached_status_message() # Use cached status
        trial_status = self.get_trial_status()
        if license_valid or trial_status['in_trial']:
            return False

        # 制限モードでのカウント処理
        today_str = date.today().isoformat()
        count_date = self.config_manager.get(KEY_BATCH_COUNT_DATE)
        daily_count = 0

        if count_date != today_str:
            # 日付が変わった場合、カウントを1に設定
            self.config_manager.set(KEY_BATCH_COUNT_DATE, today_str)
            self.config_manager.set(KEY_DAILY_BATCH_COUNT, 1)
            daily_count = 1
            self.logger.info(f"バッチ処理カウントをリセットし、1に設定しました ({today_str})")
        else:
            # 同じ日付の場合、カウントを増やす
            current_count = int(self.config_manager.get(KEY_DAILY_BATCH_COUNT, 0))
            if current_count < 5: # 上限チェック
                daily_count = current_count + 1
                self.config_manager.set(KEY_DAILY_BATCH_COUNT, daily_count)
                self.logger.info(f"バッチ処理カウントをインクリメント: {daily_count}/5 ({today_str})")
            else:
                 # 理論上ここには来ないはず (can_process_batchで弾かれるため)
                 daily_count = current_count
                 self.logger.warning(f"バッチカウント増加試行が上限を超えています: {daily_count}/5")

        self.config_manager.save()
        return True

    def can_use_crop(self) -> tuple[bool, str]:
        """
        クロップ処理が可能かどうかを判定する。
        Returns:
            tuple[bool, str]: (処理可能かどうか, メッセージ)
        """
        # 1. ライセンスが有効か確認
        license_key = self.config_manager.get(KEY_LICENSE_KEY)
        if license_key and self.is_valid(license_key):
            _, license_valid, _ = self.get_cached_status_message()
            if license_valid:
                return True, "ライセンス有効"

        # 2. トライアル期間内か確認
        trial_status = self.get_trial_status()
        if trial_status['in_trial']:
            return True, f"トライアル期間内（残り{max(0, trial_status['days_left'])}日）"

        # 3. 制限モード - クロップ処理不可
        return False, "クロップ処理はトライアル期間終了後は使用できません。ライセンスをご購入ください。"

    # --- End Trial and Limitation Methods ---

    # --- Helper Methods (Consider moving if class grows too large) ---
    # (No helpers added in this step)
    # --- End Helper Methods --- 