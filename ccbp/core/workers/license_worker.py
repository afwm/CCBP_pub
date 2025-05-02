from PySide6.QtCore import QObject, Signal, Slot
from ccbp.core.license_manager import LicenseManager
import logging

class LicenseWorker(QObject):
    """Worker object to handle license validation API calls in a separate thread."""
    # --- Adjust Signals to match controller expectations ---
    # finished = Signal(dict) # Original: validation_finished
    # error = Signal(str) # Add error signal
    finished = Signal(object) # Use 'object' to allow dict or None for simplicity here
    error = Signal(str)
    # --- End Adjust Signals ---

    # --- Modify __init__ to accept license key ---
    def __init__(self, license_key: str, license_manager: LicenseManager):
        super().__init__()
        self.license_manager = license_manager
        self.logger = logging.getLogger(__name__)
        self._license_key_to_validate = license_key # Store key from init
    # --- End Modify __init__ ---

    # --- Remove unused set_license_key slot --- 
    # @Slot(str)
    # def set_license_key(self, key: str):
    #    self._license_key_to_validate = key
    # --- End Remove ---

    # --- Rename run_validation to run and add error handling ---
    @Slot()
    def run(self):
        """Runs the validation process and emits finished or error signal."""
        self.logger.debug(f"[START] LicenseWorker.run for key: '{self._license_key_to_validate[:5]}...'")
        if not self._license_key_to_validate:
            self.logger.warning("LicenseWorker: No license key provided during init.")
            self.error.emit("内部エラー: ライセンスキーが設定されていません。") # Emit error
            return

        try:
            self.logger.info(f"LicenseWorker: Starting validation for key '{self._license_key_to_validate[:5]}...'")
            # No need for started signal from worker itself, controller handles UI start

            # --- Call API via LicenseManager --- 
            # _validate_license_api now handles caching and returns dict or None
            # We need to handle potential exceptions raised by _validate_license_api itself
            # based on how LicenseManager is implemented (it might return None or raise)
            
            # For now, assume _validate_license_api returns dict on success, None on specific API/network errors
            # and potentially raises other exceptions.
            
            result_data = self.license_manager._validate_license_api(self._license_key_to_validate)

            if result_data is not None:
                self.logger.info("LicenseWorker: Validation successful.") 
                self.logger.debug(f"Emitting finished signal with result: {result_data}")
                self.finished.emit(result_data) # Emit the result dict
            else:
                # API/Network error occurred, handled within _validate_license_api (which logged it)
                self.logger.warning("LicenseWorker: _validate_license_api indicated failure (returned None).")
                # Retrieve the cached error message to emit
                cached_msg, _, _ = self.license_manager.get_cached_status_message()
                error_msg_to_emit = cached_msg if cached_msg else "APIまたはネットワークエラーが発生しました。"
                self.error.emit(error_msg_to_emit) # Emit cached error message
                
        # --- Catch specific exceptions if needed, or a general one --- 
        # Example: Catching requests exceptions explicitly if _validate_license_api didn't handle them
        # except requests.exceptions.RequestException as req_e:
        #     self.logger.error(f"LicenseWorker: Network error during validation: {req_e}")
        #     self.error.emit(f"ネットワークエラー: {req_e}")
        except Exception as e:
            # Catch any unexpected error during the process
            self.logger.exception(f"LicenseWorker: Unexpected error during run: {e}")
            self.error.emit(f"予期せぬ内部エラーが発生しました: {e}")
            
        self.logger.debug("[END] LicenseWorker.run") 
    # --- End Rename and Error Handling --- 