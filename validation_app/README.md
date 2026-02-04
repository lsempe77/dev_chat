# Validation App for Extraction Results

A Streamlit app for human validation of extraction results with split-screen PDF viewing.

## Features

- **Split screen**: PDF on left, extracted data on right
- **Per-row validation**: Confirm, reject, or edit each extraction
- **Progress tracking**: See validation status per study
- **Auto-save**: Results saved to JSON after each action
- **Page navigation**: Jumps to the correct page in the PDF

## Setup

### 1. Install dependencies

```bash
pip install streamlit pandas
```

### 2. Enable R2 Public Access

To view PDFs in the browser, make your R2 bucket publicly accessible:

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) > R2
2. Select the `devchat-pdfs` bucket
3. Go to **Settings** > **Public access**
4. Enable **"Allow Access"** (or create a custom domain)
5. Copy the public URL (e.g., `https://pub-xxx.r2.dev`)
6. Set the environment variable:

```bash
export R2_PUBLIC_URL="https://pub-xxx.r2.dev"
```

Or update the URL directly in `app.py`:

```python
R2_PUBLIC_URL = "https://your-public-bucket-url.r2.dev"
```

### 3. Run the app

```bash
cd devchat_v2_sota
streamlit run validation_app/app.py
```

## Usage

1. **Select a study** from the sidebar dropdown
2. **Navigate rows** using Previous/Next buttons or row number input
3. **Review the PDF** on the left (auto-navigates to correct page)
4. **Validate the extraction** on the right:
   - ✅ **Confirm**: Extraction is correct
   - ❌ **Reject**: Extraction is wrong (e.g., not a treatment effect)
   - 💾 **Save Edits**: Correct values and save
5. **Add notes** for any observations

## Output

Validation results are saved to `validation_app/validation_results.json`:

```json
{
  "study_id_rownum": {
    "status": "confirmed|rejected|edited",
    "timestamp": "2026-01-29T18:30:00",
    "original": { ... },
    "edited": { ... },  // if edited
    "notes": "..."
  }
}
```

## Deployment

For production deployment (e.g., Streamlit Cloud):

1. Ensure R2 bucket is public
2. Set `R2_PUBLIC_URL` as a secret/env variable
3. Deploy to Streamlit Cloud or your preferred platform

```bash
# Streamlit Cloud secrets.toml
R2_PUBLIC_URL = "https://pub-xxx.r2.dev"
```
