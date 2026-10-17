import os
import tempfile
import logging
import fitz# PyMuPDF (previously imported as fitz)
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def allowed_file(filename):
    """
    Check if filename has an allowed extension.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_pdf(file_storage):
    """
    Validate that an uploaded file is a valid PDF within size limits.
    Returns {"valid": True} or {"valid": False, "error": "message"}.
    """
    if not file_storage:
        return {"valid": False, "error": "No file was uploaded."}

    filename = getattr(file_storage, 'filename', '')
    if not filename or not filename.strip():
        return {"valid": False, "error": "No file selected for upload."}

    if not allowed_file(filename):
        return {
            "valid": False,
            "error": "Invalid file format. Only PDF (.pdf) files are supported."
        }

    # Verify size using seek and tell
    try:
        file_storage.seek(0, os.SEEK_END)
        size = file_storage.tell()
        file_storage.seek(0)

        if size <= 0:
            return {"valid": False, "error": "Uploaded file is empty (0 bytes)."}

        if size > MAX_FILE_SIZE:
            size_mb = size / (1024 * 1024)
            return {
                "valid": False,
                "error": f"File size ({size_mb:.1f} MB) exceeds maximum allowed limit of 10 MB."
            }
        return {"valid": True, "size": size}
    except Exception as e:
        logger.error(f"Error checking file size: {e}")
        try:
            file_storage.seek(0)
        except Exception:
            pass
        return {"valid": False, "error": f"Failed to read file: {str(e)}"}


def extract_text_from_pdf(file_storage):
    """
    Save to a temporary file, extract text using PyMuPDF (fitz), and cleanup.
    Handles encrypted, corrupted, empty, and scanned PDFs.

    Returns:
        dict: {"success": True, "text": ..., "pages": ..., "filename": ..., "file_size": ...}
              or {"success": False, "error": ...}
    """
    validation = validate_pdf(file_storage)
    if not validation.get("valid"):
        return {"success": False, "error": validation.get("error", "Invalid file.")}

    orig_filename = getattr(file_storage, 'filename', 'document.pdf')
    safe_filename = secure_filename(orig_filename) or "document.pdf"

    temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
    try:
        os.close(temp_fd)  # Close the file descriptor so file_storage can write cleanly
        file_storage.seek(0)
        file_storage.save(temp_path)
        actual_size = os.path.getsize(temp_path)

        # Open and inspect with PyMuPDF
        try:
            doc = fitz.open(temp_path)
        except Exception as open_err:
            logger.error(f"Error opening PDF with PyMuPDF: {open_err}")
            return {
                "success": False,
                "error": "The uploaded file is corrupted or is not a valid PDF document."
            }

        if doc.is_encrypted:
            doc.close()
            return {
                "success": False,
                "error": "The PDF is password protected or encrypted. Please remove encryption and try again."
            }

        page_count = len(doc)
        if page_count == 0:
            doc.close()
            return {
                "success": False,
                "error": "The uploaded PDF document has no pages."
            }

        extracted_text_blocks = []
        for page_num in range(page_count):
            try:
                page = doc.load_page(page_num)
                page_text = page.get_text("text")
                if page_text and page_text.strip():
                    extracted_text_blocks.append(page_text.strip())
            except Exception as pe:
                logger.warning(f"Could not extract text from page {page_num + 1}: {pe}")

        doc.close()

        full_text = "\n\n".join(extracted_text_blocks).strip()

        # Check for empty text or scanned PDF
        if not full_text:
            return {
                "success": False,
                "error": "No readable text found in the PDF. The file may contain only scanned images or photos that require OCR."
            }

        # Check if text is suspiciously short compared to page count
        warning = None
        if len(full_text) < 30 * page_count:
            warning = "The document text is very short for its page count; some pages may contain scanned images without selectable text."

        response = {
            "success": True,
            "text": full_text,
            "pages": page_count,
            "filename": safe_filename,
            "file_size": actual_size
        }
        if warning:
            response["warning"] = warning

        return response

    except Exception as e:
        logger.error(f"Unexpected error during PDF text extraction: {e}")
        return {
            "success": False,
            "error": f"An error occurred while processing the PDF: {str(e)}"
        }
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as ce:
                logger.warning(f"Could not remove temporary file {temp_path}: {ce}")
