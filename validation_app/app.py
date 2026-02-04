"""
Streamlit app for human validation of extraction results.
Split screen: PDF viewer on left, extracted data on right.

To use R2 PDFs in production:
1. Go to Cloudflare Dashboard > R2 > devchat-pdfs bucket
2. Settings > Public access > Enable "Allow Access"  
3. Copy the public URL (e.g., https://pub-xxx.r2.dev)
4. Update R2_PUBLIC_URL below
"""
import streamlit as st
import pandas as pd
import json
import os
from pathlib import Path
from datetime import datetime

# Page config
st.set_page_config(
    page_title="Extraction Validator",
    page_icon="📊",
    layout="wide"
)

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_PATH = BASE_DIR / "extraction_pipeline" / "outputs" / "full_corpus_for_validation.csv"
VALIDATION_PATH = BASE_DIR / "validation_app" / "validation_results.json"

# R2 Configuration - Update with your public bucket URL
# To get this: Cloudflare Dashboard > R2 > devchat-pdfs > Settings > Public access
R2_PUBLIC_URL = os.environ.get(
    "R2_PUBLIC_URL", 
    "https://pub-84c0e17c977e43b88fea7ec63d3f8dad.r2.dev"
)
R2_PDF_PREFIX = "rags/0816e8d3-ab23-417c-bf3f-e45531411c73/input-pdfs/"

# Load data
@st.cache_data
def load_data():
    df = pd.read_csv(DATA_PATH)
    return df

# Load/save validation results
def load_validation_results():
    if VALIDATION_PATH.exists():
        with open(VALIDATION_PATH) as f:
            return json.load(f)
    return {}

def save_validation_results(results):
    VALIDATION_PATH.parent.mkdir(exist_ok=True)
    with open(VALIDATION_PATH, 'w') as f:
        json.dump(results, f, indent=2)

# Initialize
df = load_data()
validation_results = load_validation_results()

# Get unique studies
studies = df.groupby(['study_id', 'pdf_name']).size().reset_index(name='rows')
studies = studies.sort_values('rows', ascending=False)

# Sidebar - Study selector
st.sidebar.title("📊 Extraction Validator")
st.sidebar.markdown("---")

# Calculate progress
total_rows = len(df)
validated_count = len([k for k, v in validation_results.items() if v.get('status') in ['confirmed', 'rejected']])
st.sidebar.metric("Progress", f"{validated_count}/{total_rows}", f"{100*validated_count/total_rows:.1f}%")

st.sidebar.markdown("---")
st.sidebar.subheader("Select Study")

# Study filter
study_options = [f"{row['study_id']} ({row['rows']} rows)" for _, row in studies.iterrows()]
selected_study_idx = st.sidebar.selectbox(
    "Study",
    range(len(study_options)),
    format_func=lambda x: study_options[x]
)

selected_study_id = studies.iloc[selected_study_idx]['study_id']
selected_pdf_name = studies.iloc[selected_study_idx]['pdf_name']

# Filter to selected study
study_df = df[df['study_id'] == selected_study_id].copy()
study_df = study_df.reset_index(drop=True)

# Row selector
st.sidebar.markdown("---")
st.sidebar.subheader("Navigate Rows")

# Show validation status for each row
row_statuses = []
for idx in range(len(study_df)):
    row_key = f"{selected_study_id}_{idx}"
    status = validation_results.get(row_key, {}).get('status', 'pending')
    row_statuses.append(status)

# Row navigation with status
def get_status_icon(status):
    return {'confirmed': '✅', 'rejected': '❌', 'edited': '✏️', 'pending': '⬜'}[status]

current_row = st.sidebar.number_input(
    "Row #", 
    min_value=0, 
    max_value=len(study_df)-1, 
    value=0,
    help="Navigate to specific row"
)

# Quick navigation buttons
col1, col2, col3 = st.sidebar.columns(3)
if col1.button("◀ Prev"):
    if current_row > 0:
        st.session_state['current_row'] = current_row - 1
        st.rerun()
if col2.button("Next ▶"):
    if current_row < len(study_df) - 1:
        st.session_state['current_row'] = current_row + 1
        st.rerun()
if col3.button("Skip ⏭"):
    # Find next pending
    for i in range(current_row + 1, len(study_df)):
        if row_statuses[i] == 'pending':
            st.session_state['current_row'] = i
            st.rerun()
            break

# Show row status summary
status_counts = pd.Series(row_statuses).value_counts()
st.sidebar.markdown("---")
st.sidebar.write("**This Study:**")
for status in ['confirmed', 'rejected', 'edited', 'pending']:
    count = status_counts.get(status, 0)
    st.sidebar.write(f"{get_status_icon(status)} {status.title()}: {count}")

# Main content - Split view
left_col, right_col = st.columns([1, 1])

# LEFT: PDF Viewer
with left_col:
    st.subheader(f"📄 PDF: {selected_pdf_name}")
    
    # Get page number for this row
    row_data = study_df.iloc[current_row]
    page_num = row_data.get('page_number', 1)
    if pd.isna(page_num):
        page_num = 1
    else:
        page_num = int(page_num)
    
    # Get the original filename from the data to construct R2 URL
    # The filename in the CSV is like: "076ec917aab5_PDFs_of_included_programs_121378172_Gilligan_(2024).json"
    # The PDF in R2 is: "076ec917aab5_PDFs_of_included_programs_121378172_Gilligan_(2024).pdf"
    original_filename = study_df.iloc[current_row].get('filename', '') if 'filename' not in study_df.columns else df[df['study_id'] == selected_study_id]['filename'].iloc[0]
    
    # Try to get the R2 filename (with hash prefix)
    # The pdf_name has hash removed, but we need it for R2
    # Let's construct from the CSV data
    import urllib.parse
    
    # Get the raw filename from the original data
    raw_df = pd.read_csv(DATA_PATH.parent / "full_corpus_all_studies.csv")
    study_files = raw_df[raw_df['study_id'] == selected_study_id]['filename'].unique()
    
    if len(study_files) > 0:
        r2_filename = study_files[0].replace('.json', '.pdf')
        pdf_url = f"{R2_PUBLIC_URL}/{R2_PDF_PREFIX}{urllib.parse.quote(r2_filename)}"
    else:
        # Fallback - try numeric study ID
        pdf_url = f"{R2_PUBLIC_URL}/{R2_PDF_PREFIX}{selected_study_id}.pdf"
    
    st.markdown(f"**Page {page_num}** | [Open PDF ↗]({pdf_url})")
    
    # Embed PDF viewer using Google Docs viewer (works with public URLs)
    # Or use direct iframe for R2 public URLs
    pdf_embed = f"""
    <iframe 
        src="{pdf_url}#page={page_num}" 
        width="100%" 
        height="700px"
        style="border: 1px solid #ddd; border-radius: 5px;">
    </iframe>
    """
    st.markdown(pdf_embed, unsafe_allow_html=True)
    
    # Show table context below PDF
    st.markdown("---")
    caption = row_data.get('table_caption', '')
    if caption and not pd.isna(caption):
        st.markdown(f"**Table:** {row_data.get('table_number', 'N/A')}")
        st.markdown(f"**Caption:** {caption[:300]}{'...' if len(str(caption)) > 300 else ''}")

# RIGHT: Extracted Data & Validation
with right_col:
    st.subheader(f"📋 Row {current_row + 1} of {len(study_df)}")
    
    row_key = f"{selected_study_id}_{current_row}"
    current_status = validation_results.get(row_key, {}).get('status', 'pending')
    
    # Status indicator
    status_color = {'confirmed': 'green', 'rejected': 'red', 'edited': 'orange', 'pending': 'gray'}[current_status]
    st.markdown(f"**Status:** :{status_color}[{current_status.upper()}]")
    
    st.markdown("---")
    
    # Show table context
    st.markdown(f"**Table:** {row_data.get('table_number', 'N/A')}")
    caption = row_data.get('table_caption', '')
    if caption and not pd.isna(caption):
        st.markdown(f"**Caption:** {caption[:200]}...")
    
    st.markdown("---")
    
    # Editable fields
    st.markdown("### Extracted Values")
    
    with st.form(key=f"validation_form_{row_key}"):
        col_a, col_b = st.columns(2)
        
        with col_a:
            treatment = st.text_input(
                "Treatment Arm",
                value=str(row_data.get('treatment_arm', '')) if not pd.isna(row_data.get('treatment_arm')) else '',
                key=f"treatment_{row_key}"
            )
            outcome = st.text_input(
                "Outcome Name",
                value=str(row_data.get('outcome_name', '')) if not pd.isna(row_data.get('outcome_name')) else '',
                key=f"outcome_{row_key}"
            )
            coefficient = st.text_input(
                "Coefficient",
                value=str(row_data.get('coefficient', '')) if not pd.isna(row_data.get('coefficient')) else '',
                key=f"coef_{row_key}"
            )
        
        with col_b:
            se = st.text_input(
                "Standard Error",
                value=str(row_data.get('standard_error', '')) if not pd.isna(row_data.get('standard_error')) else '',
                key=f"se_{row_key}"
            )
            pvalue = st.text_input(
                "P-Value",
                value=str(row_data.get('p_value', '')) if not pd.isna(row_data.get('p_value')) else '',
                key=f"pval_{row_key}"
            )
            significance = st.text_input(
                "Significance",
                value=str(row_data.get('significance', '')) if not pd.isna(row_data.get('significance')) else '',
                key=f"sig_{row_key}"
            )
        
        # Original cell text for reference
        st.markdown("---")
        st.markdown("**Original Cell Text:**")
        cell_text = row_data.get('literal_cell_text', '')
        st.code(cell_text if not pd.isna(cell_text) else 'N/A')
        
        # Validation buttons
        st.markdown("---")
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        
        confirm_btn = btn_col1.form_submit_button("✅ Confirm", type="primary")
        reject_btn = btn_col2.form_submit_button("❌ Reject")
        save_edit_btn = btn_col3.form_submit_button("💾 Save Edits")
        
        if confirm_btn:
            validation_results[row_key] = {
                'status': 'confirmed',
                'timestamp': datetime.now().isoformat(),
                'original': row_data.to_dict()
            }
            save_validation_results(validation_results)
            st.success("Row confirmed!")
            st.rerun()
        
        if reject_btn:
            validation_results[row_key] = {
                'status': 'rejected',
                'timestamp': datetime.now().isoformat(),
                'original': row_data.to_dict(),
                'reason': 'Rejected by validator'
            }
            save_validation_results(validation_results)
            st.warning("Row rejected!")
            st.rerun()
        
        if save_edit_btn:
            validation_results[row_key] = {
                'status': 'edited',
                'timestamp': datetime.now().isoformat(),
                'original': row_data.to_dict(),
                'edited': {
                    'treatment_arm': treatment,
                    'outcome_name': outcome,
                    'coefficient': coefficient,
                    'standard_error': se,
                    'p_value': pvalue,
                    'significance': significance
                }
            }
            save_validation_results(validation_results)
            st.info("Edits saved!")
            st.rerun()
    
    # Notes field (outside form for quick notes)
    st.markdown("---")
    notes = st.text_area(
        "Notes (optional)",
        value=validation_results.get(row_key, {}).get('notes', ''),
        key=f"notes_{row_key}",
        height=100
    )
    if st.button("Save Notes"):
        if row_key not in validation_results:
            validation_results[row_key] = {'status': 'pending'}
        validation_results[row_key]['notes'] = notes
        save_validation_results(validation_results)
        st.success("Notes saved!")

# Footer
st.markdown("---")
st.markdown(
    f"*Validation App | Data: {len(df):,} rows from {len(studies)} studies | "
    f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*"
)
