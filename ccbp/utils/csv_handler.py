import csv
import os
import logging # Use standard logging

# Assuming logging is configured elsewhere
logger = logging.getLogger(__name__)

class CsvHandler:
    """Handles reading and basic validation of the input CSV file."""

    # Define required columns for the batch process
    REQUIRED_COLUMNS = ["id", "ProjectName"] 
    # Add other columns if your CapCut template replacement logic needs them, e.g.,
    # REQUIRED_COLUMNS = ["id", "ProjectName", "Text1", "Image1", "Video1"] 

    def __init__(self, csv_path: str):
        """Initializes the CsvHandler and loads data immediately.

        Args:
            csv_path: The path to the CSV file.

        Raises:
            FileNotFoundError: If the csv_path does not exist.
            ValueError: If the CSV is invalid (e.g., empty, missing required columns, read errors).
        """
        if not os.path.exists(csv_path):
            logger.error(f"CSV file not found at specified path: {csv_path}")
            raise FileNotFoundError(f"CSVファイルが見つかりません: {csv_path}")
            
        self.csv_path = csv_path
        self.header = []
        self.data = []
        # Load and validate immediately upon instantiation
        self._load_and_validate()

    def _detect_encoding(self) -> str | None:
        """Detects CSV encoding by trying common UTF formats (UTF-8-SIG first)."""
        encodings_to_try = ["utf-8-sig", "utf-8", "shift-jis", "cp932"] # Added Japanese encodings
        for enc in encodings_to_try:
            try:
                # Try opening and reading a small chunk
                with open(self.csv_path, "r", encoding=enc) as f:
                    f.read(1024) 
                logger.info(f"Detected CSV encoding: {enc}")
                return enc
            except (UnicodeDecodeError, LookupError): # Catch decoding and unknown encoding errors
                logger.debug(f"Failed to decode CSV with encoding: {enc}")
            except Exception as e:
                logger.warning(f"Unexpected error detecting encoding {enc} for {self.csv_path}: {e}")
                
        logger.warning("Could not detect common encodings (UTF-8-SIG, UTF-8, Shift-JIS, CP932). Falling back to system default.")
        return None # Let open() use the system default if detection fails

    def _load_and_validate(self):
        """Loads the CSV data and performs validation (header, required columns)."""
        logger.info(f"Loading CSV file: {self.csv_path}")
        detected_encoding = self._detect_encoding()
        
        try:
            with open(self.csv_path, "r", newline="", encoding=detected_encoding) as f:
                reader = csv.reader(f)
                try:
                    # Read the header row
                    self.header = next(reader)
                    # Strip leading/trailing whitespace from headers
                    self.header = [h.strip() for h in self.header]
                    # Check for BOM in the first header again after stripping
                    if self.header and self.header[0].startswith('\ufeff'):
                        self.header[0] = self.header[0][1:]
                        
                    logger.debug(f"CSV Header: {self.header}")
                except StopIteration:
                    raise ValueError("CSVファイルが空か、ヘッダー行が存在しません。")

                # --- Validate required columns --- 
                missing_cols = [
                    col for col in self.REQUIRED_COLUMNS if col not in self.header
                ]
                if missing_cols:
                    missing_cols_str = ", ".join(missing_cols)
                    logger.error(f"CSV file {self.csv_path} is missing required columns: {missing_cols_str}")
                    raise ValueError(f"CSVファイルに必要なカラムがありません: {missing_cols_str}")
                # ----------------------------------

                # --- Load data as list of dictionaries --- 
                self.data = []
                for row_num, row in enumerate(reader, start=2): # Start row count from 2 (after header)
                    if len(row) != len(self.header):
                        logger.warning(f"CSV row {row_num}: Number of columns ({len(row)}) does not match header ({len(self.header)}). Skipping row: {row}")
                        continue # Skip rows with mismatched column count
                    row_dict = dict(zip(self.header, row))
                    self.data.append(row_dict)
                # ---------------------------------------
                    
                if not self.data:
                     logger.warning(f"CSV file {self.csv_path} loaded successfully, but contains no data rows.")
                else: 
                     logger.info(f"Successfully loaded {len(self.data)} data rows from CSV: {self.csv_path}")

        except FileNotFoundError: # Should be caught in __init__ but handle defensively
            logger.error(f"CSV file not found during load: {self.csv_path}")
            raise
        except ValueError as ve: # Catch validation errors
            logger.error(f"CSV validation failed for {self.csv_path}: {ve}")
            raise
        except Exception as e: # Catch other potential errors (permissions, decode, etc.)
            logger.exception(f"Failed to read or parse CSV file {self.csv_path}: {e}")
            raise ValueError(f"CSVファイルの読み込みまたは解析に失敗しました: {e}") from e

    def get_header(self) -> list:
        """Returns the header row of the CSV."""
        return self.header

    def get_data(self) -> list[dict]:
        """Returns the data rows as a list of dictionaries."""
        return self.data

    def get_row_count(self) -> int:
        """Returns the number of data rows (excluding the header)."""
        return len(self.data)

# Example usage (for testing if run directly)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG) 
    # Create a dummy CSV for testing
    dummy_csv_path = "dummy_test.csv"
    dummy_data = [
        ["id", "ProjectName", "Text1", "Image1"], 
        ["1", "Project_A", "Hello A", "imageA.jpg"], 
        ["2", "Project_B", "Hello B", "imageB.png"],
        ["3", "Project_C", "", ""] # Empty data row
    ]
    try:
        with open(dummy_csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(dummy_data)
        print(f"Created dummy CSV: {dummy_csv_path}")

        try:
            csv_handler = CsvHandler(dummy_csv_path)
            print("Header:", csv_handler.get_header())
            print("Data:", csv_handler.get_data())
            print("Row Count:", csv_handler.get_row_count())
        except (FileNotFoundError, ValueError) as e:
            print(f"Error processing CSV: {e}")
            
        # Test missing required column
        dummy_invalid_csv_path = "dummy_invalid.csv"
        dummy_invalid_data = [["id", "Text1"], ["1", "Hello"]]
        with open(dummy_invalid_csv_path, 'w', newline='', encoding='utf-8-sig') as f:
             writer = csv.writer(f)
             writer.writerows(dummy_invalid_data)
        print(f"\nCreated invalid dummy CSV: {dummy_invalid_csv_path}")
        try:
             csv_handler_invalid = CsvHandler(dummy_invalid_csv_path)
        except ValueError as e:
             print(f"Successfully caught validation error: {e}")
             
    finally:
        # Clean up dummy files
        if os.path.exists(dummy_csv_path):
            os.remove(dummy_csv_path)
            print(f"Removed dummy CSV: {dummy_csv_path}")
        if os.path.exists(dummy_invalid_csv_path):
            os.remove(dummy_invalid_csv_path)
            print(f"Removed invalid dummy CSV: {dummy_invalid_csv_path}") 