"""
Document Processing Agent
Handles invoices, PDFs, Excel/CSV, and scanned images using Claude API tool use.
"""

import os
import json
import base64
import shutil
import smtplib
import mimetypes
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Any

import anthropic

# ── Optional dependencies (graceful import) ─────────────────────────────────
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# ── Client ───────────────────────────────────────────────────────────────────
client = anthropic.Anthropic()

# ── System prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a document processing agent. You can read, extract, split, validate, export, save, and email documents.

When extracting data from invoices or bills, always try to capture:
- vendor (supplier/company name)
- invoice_number
- date (invoice date)
- due_date
- total_amount (numeric)
- tax_amount (numeric)
- subtotal (numeric)
- line_items (list of {description, qty, unit_price, amount})
- currency
- billing_address
- payment_terms

For scanned images passed to you via vision, read all visible text carefully and extract the same fields.

When the user asks you to process a folder or file, use your tools systematically:
1. list_documents → see what's there
2. read_document → extract content
3. validate_invoice → check for errors (if it's an invoice)
4. export_data / split_pdf / save_document / send_email → as requested

Always report what you found, what was missing, and what actions you took."""

# ── Tool definitions (JSON schema) ───────────────────────────────────────────
TOOLS = [
    {
        "name": "list_documents",
        "description": "List all documents in a folder. Returns file names grouped by type (pdf, image, csv, excel).",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the folder to scan."
                }
            },
            "required": ["folder_path"]
        }
    },
    {
        "name": "read_document",
        "description": (
            "Read and extract content from a document. "
            "Supports PDF (text + tables), CSV, Excel, and images (jpg, png, tiff, bmp). "
            "For images, returns a vision marker so the agent can see the scan directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the document file."
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "split_pdf",
        "description": "Split a PDF into smaller files. Each output file contains pages_per_file pages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the source PDF."},
                "output_dir": {"type": "string", "description": "Folder to save the split PDFs."},
                "pages_per_file": {
                    "type": "integer",
                    "description": "Number of pages per output file. Default is 1.",
                    "default": 1
                }
            },
            "required": ["file_path", "output_dir"]
        }
    },
    {
        "name": "validate_invoice",
        "description": (
            "Validate extracted invoice data. Checks required fields, amount math "
            "(subtotal + tax ≈ total), and flags anomalies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_data": {
                    "type": "object",
                    "description": "The extracted invoice dict (vendor, total_amount, line_items, etc.)"
                }
            },
            "required": ["invoice_data"]
        }
    },
    {
        "name": "export_data",
        "description": "Export structured data to JSON, CSV, or Excel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"description": "Data to export (dict or list of dicts)."},
                "output_path": {"type": "string", "description": "Destination file path including extension."},
                "format": {
                    "type": "string",
                    "enum": ["json", "csv", "excel"],
                    "description": "Output format. Default is json.",
                    "default": "json"
                }
            },
            "required": ["data", "output_path"]
        }
    },
    {
        "name": "save_document",
        "description": "Copy a document to a destination folder, optionally renaming it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "description": "Path to the source file."},
                "destination_folder": {"type": "string", "description": "Target folder."},
                "rename": {
                    "type": "string",
                    "description": "New file name (without path). Optional — keeps original name if omitted."
                }
            },
            "required": ["source_path", "destination_folder"]
        }
    },
    {
        "name": "send_email",
        "description": (
            "Send an email with optional file attachment. "
            "Uses SMTP if SMTP_HOST env var is set, otherwise logs a mock send."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Email body (plain text)."},
                "attachment_path": {
                    "type": "string",
                    "description": "Path to a file to attach. Optional."
                }
            },
            "required": ["to", "subject", "body"]
        }
    }
]

# ── Tool implementations ──────────────────────────────────────────────────────

def list_documents(folder_path: str) -> dict:
    path = Path(folder_path)
    if not path.exists():
        return {"error": f"Folder not found: {folder_path}"}

    result = {"pdfs": [], "images": [], "csvs": [], "excels": [], "others": []}
    img_exts = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}

    for f in sorted(path.iterdir()):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext == ".pdf":
            result["pdfs"].append(str(f))
        elif ext in img_exts:
            result["images"].append(str(f))
        elif ext == ".csv":
            result["csvs"].append(str(f))
        elif ext in {".xlsx", ".xls", ".xlsm"}:
            result["excels"].append(str(f))
        else:
            result["others"].append(str(f))

    total = sum(len(v) for v in result.values())
    result["total"] = total
    return result


def read_document(file_path: str) -> dict:
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    ext = path.suffix.lower()
    img_exts = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}

    if ext in img_exts:
        # Signal to the agent loop to send this as a vision block
        return {"__send_as_image__": True, "path": str(path)}

    if ext == ".pdf":
        if not HAS_PDFPLUMBER:
            return {"error": "pdfplumber not installed. Run: pip install pdfplumber"}
        pages = []
        tables_all = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                pages.append({"page": i + 1, "text": text})
                for t in tables:
                    tables_all.append({"page": i + 1, "rows": t})
        return {"type": "pdf", "page_count": len(pages), "pages": pages, "tables": tables_all}

    if ext == ".csv":
        if not HAS_PANDAS:
            return {"error": "pandas not installed. Run: pip install pandas"}
        df = pd.read_csv(file_path)
        return {"type": "csv", "rows": len(df), "columns": list(df.columns), "data": df.head(100).to_dict(orient="records")}

    if ext in {".xlsx", ".xls", ".xlsm"}:
        if not HAS_PANDAS:
            return {"error": "pandas not installed. Run: pip install pandas"}
        sheets = {}
        xf = pd.ExcelFile(file_path)
        for sheet in xf.sheet_names:
            df = xf.parse(sheet)
            sheets[sheet] = {"rows": len(df), "columns": list(df.columns), "data": df.head(100).to_dict(orient="records")}
        return {"type": "excel", "sheets": sheets}

    # Fallback: read as text
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return {"type": "text", "content": text[:5000]}
    except Exception as e:
        return {"error": str(e)}


def split_pdf(file_path: str, output_dir: str, pages_per_file: int = 1) -> dict:
    if not HAS_PYPDF:
        return {"error": "pypdf not installed. Run: pip install pypdf"}

    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(path))
    total_pages = len(reader.pages)
    output_files = []
    stem = path.stem

    chunk_num = 1
    for start in range(0, total_pages, pages_per_file):
        writer = PdfWriter()
        end = min(start + pages_per_file, total_pages)
        for i in range(start, end):
            writer.add_page(reader.pages[i])

        label = f"p{start + 1}" if pages_per_file == 1 else f"p{start + 1}-{end}"
        out_name = f"{stem}_{label}.pdf"
        out_path = out_dir / out_name
        with open(out_path, "wb") as f:
            writer.write(f)

        output_files.append(str(out_path))
        chunk_num += 1

    return {
        "source": str(path),
        "total_pages": total_pages,
        "files_created": len(output_files),
        "output_files": output_files
    }


def validate_invoice(invoice_data: dict) -> dict:
    errors = []
    warnings = []

    required = ["vendor", "invoice_number", "date", "total_amount"]
    for field in required:
        if not invoice_data.get(field):
            errors.append(f"Missing required field: {field}")

    optional_recommended = ["due_date", "line_items", "subtotal", "tax_amount", "currency"]
    for field in optional_recommended:
        if not invoice_data.get(field):
            warnings.append(f"Missing recommended field: {field}")

    # Amount math check
    try:
        total = float(invoice_data.get("total_amount", 0) or 0)
        subtotal = float(invoice_data.get("subtotal", 0) or 0)
        tax = float(invoice_data.get("tax_amount", 0) or 0)

        if subtotal and tax:
            computed = subtotal + tax
            if abs(computed - total) > 0.02:
                errors.append(
                    f"Amount mismatch: subtotal ({subtotal}) + tax ({tax}) = {computed:.2f}, "
                    f"but total_amount = {total}"
                )
    except (TypeError, ValueError):
        warnings.append("Could not verify amount math — non-numeric values in total/subtotal/tax")

    # Line items total vs subtotal
    line_items = invoice_data.get("line_items") or []
    if line_items:
        try:
            items_total = sum(float(item.get("amount", 0) or 0) for item in line_items)
            subtotal = float(invoice_data.get("subtotal", 0) or 0)
            if subtotal and abs(items_total - subtotal) > 0.02:
                warnings.append(
                    f"Line items sum ({items_total:.2f}) differs from subtotal ({subtotal:.2f})"
                )
        except (TypeError, ValueError):
            pass

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "fields_present": [k for k, v in invoice_data.items() if v is not None]
    }


def export_data(data: Any, output_path: str, format: str = "json") -> dict:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fmt = format.lower()
    if fmt == "json":
        out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return {"saved": str(out), "format": "json"}

    if fmt in ("csv", "excel"):
        if not HAS_PANDAS:
            return {"error": "pandas not installed. Run: pip install pandas"}
        if isinstance(data, dict):
            rows = [data]
        elif isinstance(data, list):
            rows = data
        else:
            return {"error": "data must be a dict or list of dicts for csv/excel export"}

        df = pd.DataFrame(rows)
        if fmt == "csv":
            df.to_csv(str(out), index=False)
        else:
            df.to_excel(str(out), index=False)
        return {"saved": str(out), "format": fmt, "rows": len(df)}

    return {"error": f"Unknown format: {format}. Use json, csv, or excel."}


def save_document(source_path: str, destination_folder: str, rename: str = None) -> dict:
    src = Path(source_path)
    if not src.exists():
        return {"error": f"Source not found: {source_path}"}

    dest_dir = Path(destination_folder)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_name = rename if rename else src.name
    dest = dest_dir / dest_name
    shutil.copy2(str(src), str(dest))
    return {"copied": str(src), "to": str(dest)}


def send_email(to: str, subject: str, body: str, attachment_path: str = None) -> dict:
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_host:
        # Mock mode
        print(f"\n[MOCK EMAIL]\n  To: {to}\n  Subject: {subject}\n  Body: {body}")
        if attachment_path:
            print(f"  Attachment: {attachment_path}")
        return {"status": "mock_sent", "to": to, "subject": subject, "note": "Set SMTP_HOST env var to send real emails"}

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if attachment_path:
        att_path = Path(attachment_path)
        if att_path.exists():
            mime_type, _ = mimetypes.guess_type(str(att_path))
            main_type, sub_type = (mime_type or "application/octet-stream").split("/", 1)
            part = MIMEBase(main_type, sub_type)
            part.set_payload(att_path.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=att_path.name)
            msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to, msg.as_string())

    return {"status": "sent", "to": to, "subject": subject}


# ── Dispatch + image handling ─────────────────────────────────────────────────

def dispatch_tool(name: str, inputs: dict) -> tuple[Any, bool]:
    """Returns (result, is_image). is_image=True when read_document hits an image file."""
    fn_map = {
        "list_documents": list_documents,
        "read_document": read_document,
        "split_pdf": split_pdf,
        "validate_invoice": validate_invoice,
        "export_data": export_data,
        "save_document": save_document,
        "send_email": send_email,
    }
    if name not in fn_map:
        return {"error": f"Unknown tool: {name}"}, False

    result = fn_map[name](**inputs)

    if isinstance(result, dict) and result.get("__send_as_image__"):
        return result, True
    return result, False


def build_tool_result(tool_use_id: str, result: Any, is_image: bool) -> dict:
    if is_image:
        file_path = result["path"]
        path = Path(file_path)
        raw = path.read_bytes()
        b64 = base64.standard_b64encode(raw).decode("utf-8")
        mime, _ = mimetypes.guess_type(file_path)
        media_type = mime or "image/jpeg"
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": [
                {"type": "text", "text": f"Scanned image: {path.name}"},
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
            ]
        }
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(result, default=str)
    }


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_agent(task: str, verbose: bool = True) -> str:
    messages = [{"role": "user", "content": task}]

    if verbose:
        print(f"\n{'='*60}")
        print(f"Task: {task}")
        print('='*60)

    while True:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text
            if verbose:
                print(f"\nAgent: {final_text}")
            return final_text

        if response.stop_reason != "tool_use":
            break

        # Collect all tool_use blocks and dispatch them
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if verbose:
                print(f"\n→ Tool: {block.name}({json.dumps(block.input, default=str)})")

            result, is_image = dispatch_tool(block.name, block.input)

            if verbose:
                if is_image:
                    print(f"← Image result: {result.get('path')}")
                else:
                    preview = json.dumps(result, default=str)[:200]
                    print(f"← {preview}{'...' if len(json.dumps(result, default=str)) > 200 else ''}")

            tool_results.append(build_tool_result(block.id, result, is_image))

        messages.append({"role": "user", "content": tool_results})

    return "Agent stopped unexpectedly."


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python agent.py \"<task>\"")
        print()
        print("Examples:")
        print('  python agent.py "List all documents in ./samples"')
        print('  python agent.py "Read invoice.pdf, extract data, validate it, and export to invoice.json"')
        print('  python agent.py "Split multi_page.pdf into single pages in ./output"')
        print('  python agent.py "Read receipt.png and tell me the total amount"')
        print('  python agent.py "Process all invoices in ./invoices and email a summary to boss@company.com"')
        sys.exit(0)

    task = " ".join(sys.argv[1:])
    run_agent(task)
