# Document Processing Agent

An AI-powered document processing agent built with Claude. Upload invoices, PDFs, spreadsheets, or scanned images and let the agent extract, validate, split, export, and route your documents automatically.

## Features

- **Extract** structured data from invoices and bills (vendor, amounts, dates, line items)
- **Read** PDFs, CSV, Excel, and scanned images (via vision)
- **Split** multi-page PDFs into individual pages or sections
- **Validate** invoice data — checks required fields and amount math
- **Export** results to JSON, CSV, or Excel
- **Save & route** documents to destination folders
- **Email** documents with attachments (SMTP or mock mode)

## Tech Stack

- [Claude API](https://anthropic.com) — `claude-opus-4-7` with adaptive thinking
- FastAPI — web server
- pdfplumber — PDF text & table extraction
- pypdf — PDF splitting
- pandas — CSV/Excel processing
- Pillow — image handling

## Getting Started

```bash
pip install -r requirements.txt
```

Set your Anthropic API key:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Run locally:
```bash
uvicorn app:app --reload
```

Open `http://localhost:8000` in your browser.

## CLI Usage

```bash
python agent.py "Extract invoice data from invoice.pdf and export to JSON"
python agent.py "Split contract.pdf into single pages and save to ./output"
python agent.py "Read receipt.png and tell me the total amount"
```

## Deployment

Deployed on [Railway](https://railway.app). Set `ANTHROPIC_API_KEY` as an environment variable in the Railway dashboard.

## Author

**Harsha Nandhan Reddy**
- GitHub: [@Harshanandhan](https://github.com/Harshanandhan)
- Email: harshanandhan09@gmail.com
- Python developer · AI/ML Graduate · Blockchain & Web3 · Cybersecurity

## License

MIT
