"""
Streamlit app for human validation of extraction results.
With admin panel for managing reviewers and paper assignments.

Features:
- Admin panel for managing reviewers
- Paper assignment to reviewers  
- Email-based access control
- Split screen PDF + data validation
"""
import streamlit as st
import pandas as pd
import json
import os
import urllib.parse
from pathlib import Path
from datetime import datetime
import hashlib

# Page config
st.set_page_config(
    page_title="Extraction Validator",
    page_icon="📊",
    layout="wide"
)

# Paths - hardcoded to avoid path resolution issues
BASE_DIR = Path(r"C:\Users\LucasSempe\OneDrive - International Initiative for Impact Evaluation\Desktop\Gen AI tools\devchat_v2_sota")
DATA_PATH = BASE_DIR / "extraction_pipeline" / "outputs" / "full_corpus_for_validation.csv"
FULL_DATA_PATH = BASE_DIR / "extraction_pipeline" / "outputs" / "full_corpus_all_studies.csv"
VALIDATION_PATH = BASE_DIR / "validation_app" / "validation_results.json"
USERS_PATH = BASE_DIR / "validation_app" / "users.json"
ASSIGNMENTS_PATH = BASE_DIR / "validation_app" / "assignments.json"
PDF_MAPPING_PATH = BASE_DIR / "validation_app" / "pdf_mapping.json"

# R2 Configuration
R2_PUBLIC_URL = os.environ.get(
    "R2_PUBLIC_URL", 
    "https://pub-84c0e17c977e43b88fea7ec63d3f8dad.r2.dev"
)
R2_PDF_PREFIX = "rags/0816e8d3-ab23-417c-bf3f-e45531411c73/input-pdfs/"

# Admin credentials (in production, use environment variables or Streamlit secrets)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "lucas.sempe@3ieimpact.org")
ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH", 
    hashlib.sha256("admin123".encode()).hexdigest()
)

# ============== Data Loading ==============

@st.cache_data
def load_data():
    return pd.read_csv(DATA_PATH)

@st.cache_data  
def load_full_data():
    return pd.read_csv(FULL_DATA_PATH)

def load_json_file(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

def save_json_file(path, data):
    path.parent.mkdir(exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def load_users():
    return load_json_file(USERS_PATH)

def save_users(users):
    save_json_file(USERS_PATH, users)

def load_assignments():
    return load_json_file(ASSIGNMENTS_PATH)

def save_assignments(assignments):
    save_json_file(ASSIGNMENTS_PATH, assignments)

def load_validation_results():
    return load_json_file(VALIDATION_PATH)

def save_validation_results(results):
    save_json_file(VALIDATION_PATH, results)

@st.cache_data
def load_pdf_mapping():
    """Load mapping from clean PDF names to R2 filenames with hash prefix."""
    return load_json_file(PDF_MAPPING_PATH)
    save_json_file(VALIDATION_PATH, results)

# ============== Authentication ==============

def check_password(password):
    return hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD_HASH

def login_form():
    """Display login form."""
    st.title("🔐 Extraction Validator Login")
    
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_password")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Login as Admin", type="primary"):
            if email.lower() == ADMIN_EMAIL.lower() and check_password(password):
                st.session_state['authenticated'] = True
                st.session_state['user_email'] = email.lower()
                st.session_state['is_admin'] = True
                st.rerun()
            else:
                st.error("Invalid admin credentials")
    
    with col2:
        if st.button("Login as Reviewer"):
            users = load_users()
            email_lower = email.lower()
            if email_lower in users:
                stored_hash = users[email_lower].get('password_hash')
                if stored_hash and stored_hash == hashlib.sha256(password.encode()).hexdigest():
                    st.session_state['authenticated'] = True
                    st.session_state['user_email'] = email_lower
                    st.session_state['is_admin'] = False
                    st.rerun()
                elif not stored_hash:
                    # First login - set password
                    users[email_lower]['password_hash'] = hashlib.sha256(password.encode()).hexdigest()
                    save_users(users)
                    st.session_state['authenticated'] = True
                    st.session_state['user_email'] = email_lower
                    st.session_state['is_admin'] = False
                    st.success("Password set! Welcome!")
                    st.rerun()
                else:
                    st.error("Invalid password")
            else:
                st.error("You are not authorized. Contact admin to get access.")
    
    st.markdown("---")
    st.info("**First time reviewer?** Enter your authorized email and create a password.")

# ============== Admin Panel ==============

def admin_panel():
    """Admin panel for managing reviewers and assignments."""
    st.title("👑 Admin Panel")
    
    tab1, tab2, tab3 = st.tabs(["📋 Manage Reviewers", "📚 Assign Papers", "📊 Progress Dashboard"])
    
    users = load_users()
    assignments = load_assignments()
    df = load_data()
    
    # Get unique studies
    studies = df.groupby(['study_id', 'pdf_name']).size().reset_index(name='rows')
    
    # Tab 1: Manage Reviewers
    with tab1:
        st.subheader("Add New Reviewer")
        
        col1, col2 = st.columns(2)
        with col1:
            new_email = st.text_input("Reviewer Email", key="new_reviewer_email")
            new_name = st.text_input("Reviewer Name", key="new_reviewer_name")
        
        if st.button("➕ Add Reviewer", type="primary"):
            if new_email and new_name:
                email_lower = new_email.lower()
                if email_lower not in users:
                    users[email_lower] = {
                        'name': new_name,
                        'email': email_lower,
                        'created_at': datetime.now().isoformat(),
                        'password_hash': None
                    }
                    save_users(users)
                    st.success(f"Added reviewer: {new_name} ({email_lower})")
                    st.rerun()
                else:
                    st.warning("Reviewer already exists")
            else:
                st.error("Please enter both email and name")
        
        st.markdown("---")
        st.subheader("Current Reviewers")
        
        if users:
            for email, user in users.items():
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.write(f"**{user['name']}** ({email})")
                with col2:
                    assigned = [s for s, r in assignments.items() if email in r]
                    st.write(f"📚 {len(assigned)} papers assigned")
                with col3:
                    if st.button("🗑️", key=f"remove_{email}"):
                        del users[email]
                        save_users(users)
                        st.rerun()
        else:
            st.info("No reviewers added yet")
    
    # Tab 2: Assign Papers
    with tab2:
        st.subheader("Assign Papers to Reviewers")
        
        if not users:
            st.warning("⚠️ Add reviewers first!")
        else:
            reviewer_options = {f"{u['name']} ({e})": e for e, u in users.items()}
            
            st.markdown("### Quick Assign")
            col1, col2 = st.columns([1, 2])
            
            with col1:
                selected_reviewer = st.selectbox(
                    "Select Reviewer",
                    options=list(reviewer_options.keys()),
                    key="assign_reviewer"
                )
            
            with col2:
                study_options = [f"{row['study_id']} ({row['rows']} rows)" for _, row in studies.iterrows()]
                selected_papers = st.multiselect(
                    "Select Papers to Assign",
                    options=study_options,
                    key="assign_papers"
                )
            
            if st.button("📌 Assign Selected Papers", type="primary"):
                if selected_reviewer and selected_papers:
                    reviewer_email = reviewer_options[selected_reviewer]
                    for paper in selected_papers:
                        study_id = paper.split(" ")[0]
                        if study_id not in assignments:
                            assignments[study_id] = []
                        if reviewer_email not in assignments[study_id]:
                            assignments[study_id].append(reviewer_email)
                    save_assignments(assignments)
                    st.success(f"Assigned {len(selected_papers)} papers!")
                    st.rerun()
            
            st.markdown("---")
            st.markdown("### Current Assignments")
            
            assignment_data = []
            for _, row in studies.iterrows():
                study_id = str(row['study_id'])
                assigned_to = assignments.get(study_id, [])
                assigned_names = [users.get(e, {}).get('name', e) for e in assigned_to]
                assignment_data.append({
                    'Study ID': study_id,
                    'PDF': str(row['pdf_name'])[:50] + '...' if len(str(row['pdf_name'])) > 50 else row['pdf_name'],
                    'Rows': row['rows'],
                    'Assigned To': ', '.join(assigned_names) if assigned_names else '—'
                })
            
            assignment_df = pd.DataFrame(assignment_data)
            
            # Filters
            col1, col2 = st.columns(2)
            with col1:
                show_unassigned = st.checkbox("Show only unassigned", value=False)
            with col2:
                filter_reviewer = st.selectbox(
                    "Filter by reviewer",
                    options=["All"] + list(reviewer_options.keys())
                )
            
            display_df = assignment_df.copy()
            if show_unassigned:
                display_df = display_df[display_df['Assigned To'] == '—']
            if filter_reviewer != "All":
                reviewer_name = users[reviewer_options[filter_reviewer]]['name']
                display_df = display_df[display_df['Assigned To'].str.contains(reviewer_name, na=False)]
            
            st.dataframe(display_df, use_container_width=True, height=400)
            
            # Bulk actions
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Auto-assign unassigned (round-robin)"):
                    unassigned = [str(row['study_id']) for _, row in studies.iterrows() 
                                  if str(row['study_id']) not in assignments or not assignments[str(row['study_id'])]]
                    reviewer_list = list(users.keys())
                    
                    if reviewer_list and unassigned:
                        for i, study_id in enumerate(unassigned):
                            reviewer_email = reviewer_list[i % len(reviewer_list)]
                            if study_id not in assignments:
                                assignments[study_id] = []
                            if reviewer_email not in assignments[study_id]:
                                assignments[study_id].append(reviewer_email)
                        save_assignments(assignments)
                        st.success(f"Auto-assigned {len(unassigned)} papers!")
                        st.rerun()
            
            with col2:
                if st.button("🗑️ Clear all assignments"):
                    save_assignments({})
                    st.warning("All assignments cleared")
                    st.rerun()
    
    # Tab 3: Progress Dashboard
    with tab3:
        st.subheader("📊 Validation Progress")
        
        validation_results = load_validation_results()
        
        total_rows = len(df)
        validated = len([k for k, v in validation_results.items() 
                        if v.get('status') in ['confirmed', 'rejected', 'edited']])
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Rows", f"{total_rows:,}")
        col2.metric("Validated", f"{validated:,}")
        col3.metric("Progress", f"{100*validated/total_rows:.1f}%")
        col4.metric("Remaining", f"{total_rows - validated:,}")
        
        st.markdown("---")
        st.markdown("### Progress by Reviewer")
        
        reviewer_progress = []
        for email, user in users.items():
            assigned_studies = [s for s, reviewers in assignments.items() if email in reviewers]
            assigned_rows = df[df['study_id'].astype(str).isin(assigned_studies)]
            total_assigned = len(assigned_rows)
            
            validated_count = sum(1 for idx in range(len(assigned_rows))
                                  if validation_results.get(f"{assigned_rows.iloc[idx]['study_id']}_{idx}", {}).get('status') 
                                  in ['confirmed', 'rejected', 'edited'])
            
            reviewer_progress.append({
                'Reviewer': user['name'],
                'Email': email,
                'Papers': len(assigned_studies),
                'Rows': total_assigned,
                'Validated': validated_count,
                'Progress': f"{100*validated_count/total_assigned:.1f}%" if total_assigned > 0 else "—"
            })
        
        if reviewer_progress:
            st.dataframe(pd.DataFrame(reviewer_progress), use_container_width=True)
        else:
            st.info("No reviewers assigned yet")

# ============== Reviewer Interface ==============

def reviewer_interface(user_email):
    """Validation interface for reviewers."""
    
    users = load_users()
    assignments = load_assignments()
    validation_results = load_validation_results()
    df = load_data()
    full_df = load_full_data()
    
    user_name = users.get(user_email, {}).get('name', user_email)
    assigned_studies = [s for s, reviewers in assignments.items() if user_email in reviewers]
    
    if not assigned_studies:
        st.title(f"👋 Welcome, {user_name}")
        st.warning("You don't have any papers assigned yet. Please contact the admin.")
        return
    
    study_df_all = df[df['study_id'].astype(str).isin(assigned_studies)]
    studies = study_df_all.groupby(['study_id', 'pdf_name']).size().reset_index(name='rows')
    studies = studies.sort_values('rows', ascending=False)
    
    # Sidebar
    st.sidebar.title(f"👤 {user_name}")
    st.sidebar.markdown("---")
    
    total_rows = len(study_df_all)
    validated_count = sum(1 for study_id in assigned_studies
                         for idx in range(len(df[df['study_id'].astype(str) == study_id]))
                         if validation_results.get(f"{study_id}_{idx}", {}).get('status') 
                         in ['confirmed', 'rejected', 'edited'])
    
    st.sidebar.metric("Your Progress", f"{validated_count}/{total_rows}", 
                      f"{100*validated_count/total_rows:.1f}%" if total_rows > 0 else "0%")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Your Papers")
    
    study_options = [f"{row['study_id']} ({row['rows']} rows)" for _, row in studies.iterrows()]
    selected_idx = st.sidebar.selectbox("Select Paper", range(len(study_options)), 
                                        format_func=lambda x: study_options[x])
    
    selected_study_id = str(studies.iloc[selected_idx]['study_id'])
    selected_pdf_name = studies.iloc[selected_idx]['pdf_name']
    
    study_df = df[df['study_id'].astype(str) == selected_study_id].reset_index(drop=True)
    
    # Table selector - show tables with row counts
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Table Filter")
    
    # Get unique tables with counts
    table_counts = study_df.groupby('table_number').size().reset_index(name='count')
    table_counts = table_counts.sort_values('table_number', key=lambda x: x.str.extract(r'(\d+)')[0].astype(float))
    
    table_options = ["All Tables"] + [f"{row['table_number']} ({row['count']} rows)" 
                                      for _, row in table_counts.iterrows()]
    
    selected_table_idx = st.sidebar.selectbox("Select Table", range(len(table_options)), 
                                              format_func=lambda x: table_options[x],
                                              key="table_selector")
    
    # Filter study_df by selected table
    if selected_table_idx > 0:
        selected_table = table_counts.iloc[selected_table_idx - 1]['table_number']
        study_df = study_df[study_df['table_number'] == selected_table].reset_index(drop=True)
        st.sidebar.caption(f"Showing {len(study_df)} rows from {selected_table}")
    
    # Row navigation
    st.sidebar.markdown("---")
    
    # Add filter for suspicious rows
    st.sidebar.subheader("🔍 Quick Filters")
    filter_option = st.sidebar.radio(
        "Show rows:",
        ["All rows", "Pending only", "Suspicious (potential errors)"],
        index=0
    )
    
    # Identify suspicious rows - potential extraction errors
    def is_suspicious_row(row):
        """Flag rows that might have extraction issues."""
        outcome = str(row.get('outcome_name', ''))
        treatment = str(row.get('treatment_arm', ''))
        coef = row.get('coefficient')
        
        # Empty or too short outcome name
        if len(outcome) < 5:
            return True
        # Treatment arm contains unexpected text
        if len(treatment) > 50 or treatment.count(' ') > 5:
            return True
        # Coefficient is extreme
        if coef is not None and not pd.isna(coef):
            try:
                c = float(coef)
                if abs(c) > 1000:  # Extremely large coefficient
                    return True
            except:
                pass
        return False
    
    suspicious_mask = study_df.apply(is_suspicious_row, axis=1)
    
    row_statuses = [validation_results.get(f"{selected_study_id}_{i}", {}).get('status', 'pending') 
                   for i in range(len(study_df))]
    
    # Apply filter
    if filter_option == "Pending only":
        filtered_indices = [i for i, s in enumerate(row_statuses) if s == 'pending']
    elif filter_option == "Suspicious (potential errors)":
        filtered_indices = [i for i, sus in enumerate(suspicious_mask) if sus]
    else:
        filtered_indices = list(range(len(study_df)))
    
    if not filtered_indices:
        st.sidebar.warning("No rows match filter")
        filtered_indices = list(range(len(study_df)))
    
    # Show count
    st.sidebar.caption(f"Showing {len(filtered_indices)} of {len(study_df)} rows")
    
    # Use session state for navigation
    if 'nav_row' not in st.session_state:
        st.session_state['nav_row'] = 0
    
    # Clamp nav_row to valid range
    max_row = len(filtered_indices) - 1
    if st.session_state['nav_row'] > max_row:
        st.session_state['nav_row'] = max_row
    if st.session_state['nav_row'] < 0:
        st.session_state['nav_row'] = 0
    
    current_row = st.sidebar.number_input(
        "Row #", 0, max_row, st.session_state['nav_row'],
        key=f"row_input_{selected_study_id}"
    )
    # Sync back to session state
    if current_row != st.session_state['nav_row']:
        st.session_state['nav_row'] = current_row
    
    actual_row = filtered_indices[current_row]
    
    col1, col2, col3 = st.sidebar.columns(3)
    if col1.button("◀"):
        if current_row > 0:
            st.session_state['nav_row'] = current_row - 1
            st.rerun()
    if col2.button("▶"):
        if current_row < len(filtered_indices) - 1:
            st.session_state['nav_row'] = current_row + 1
            st.rerun()
    if col3.button("⏭"):
        for i in range(current_row + 1, len(filtered_indices)):
            if row_statuses[filtered_indices[i]] == 'pending':
                st.session_state['nav_row'] = i
                st.rerun()
                break
    
    # Status summary
    status_counts = pd.Series(row_statuses).value_counts()
    st.sidebar.markdown("---")
    for status, icon in [('confirmed', '✅'), ('rejected', '❌'), ('edited', '✏️'), ('pending', '⬜')]:
        st.sidebar.write(f"{icon} {status.title()}: {status_counts.get(status, 0)}")
    
    # Suspicious count
    suspicious_count = sum(suspicious_mask)
    if suspicious_count > 0:
        st.sidebar.markdown("---")
        st.sidebar.warning(f"⚠️ {suspicious_count} potentially suspicious rows")
    
    # Main content
    left_col, right_col = st.columns([1, 1])
    
    with left_col:
        row_data = study_df.iloc[actual_row]
        page_num = int(row_data.get('page_number', 1)) if not pd.isna(row_data.get('page_number')) else 1
        
        # Table info header - PROMINENT
        table_num = row_data.get('table_number', 'N/A')
        table_caption = row_data.get('table_caption', '')
        
        st.markdown(f"### 📊 {table_num if table_num and not pd.isna(table_num) else 'Table'}")
        if table_caption and not pd.isna(table_caption):
            st.info(f"**Caption:** {str(table_caption)[:300]}{'...' if len(str(table_caption)) > 300 else ''}")
        
        st.markdown(f"**PDF:** {selected_pdf_name}")
        
        # Build PDF URL using mapping
        pdf_mapping = load_pdf_mapping()
        pdf_name_clean = selected_pdf_name if selected_pdf_name and not pd.isna(selected_pdf_name) else f"PDFs_of_included_programs_{selected_study_id}.pdf"
        
        # Normalize pdf_name to match mapping keys (remove "PDFs_of_included_programs_" prefix)
        pdf_name_for_lookup = pdf_name_clean
        if pdf_name_clean.startswith("PDFs_of_included_programs_"):
            # Strip the prefix and try common patterns
            stripped = pdf_name_clean.replace("PDFs_of_included_programs_", "")
            # Try direct lookup first
            if stripped in pdf_mapping:
                pdf_name_for_lookup = stripped
            # For study IDs like "121058356", the key might be "121058356.pdf"
            elif not stripped.endswith(".pdf"):
                pdf_name_for_lookup = f"{stripped}.pdf" if f"{stripped}.pdf" in pdf_mapping else stripped
        
        # Look up the R2 filename (with hash prefix)
        r2_filename = pdf_mapping.get(pdf_name_for_lookup, pdf_name_clean)
        pdf_url = f"{R2_PUBLIC_URL}/{R2_PDF_PREFIX}{urllib.parse.quote(r2_filename)}"
        
        st.markdown(f"**Page {page_num}** | [Open PDF in new tab ↗]({pdf_url})")
        st.markdown(f'<iframe src="{pdf_url}#page={page_num}" width="100%" height="550px" style="border:1px solid #ddd;border-radius:5px;"></iframe>', unsafe_allow_html=True)
    
    with right_col:
        st.subheader(f"📋 Row {actual_row + 1} of {len(study_df)}")
        
        # Flag if suspicious
        if suspicious_mask.iloc[actual_row]:
            st.warning("⚠️ This row may have extraction errors")
        
        row_key = f"{selected_study_id}_{actual_row}"
        current_status = validation_results.get(row_key, {}).get('status', 'pending')
        colors = {'confirmed': 'green', 'rejected': 'red', 'edited': 'orange', 'pending': 'gray'}
        st.markdown(f"**Status:** :{colors[current_status]}[{current_status.upper()}]")
        
        # Instructions
        st.markdown("""
        <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
        <b>📝 How to validate:</b><br>
        • <b>✅ Confirm</b> = Extraction is correct as shown<br>
        • <b>❌ Reject</b> = This is NOT a treatment effect (e.g., it's a baseline stat)<br>
        • <b>💾 Save Edits</b> = Make corrections in the fields below, then save
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### Extracted Values")
        st.caption("Edit any field below if the extraction is wrong, then click 'Save Edits'")
        
        with st.form(key=f"form_{row_key}"):
            c1, c2 = st.columns(2)
            with c1:
                treatment = st.text_input("Treatment Arm", str(row_data.get('treatment_arm', '')) if not pd.isna(row_data.get('treatment_arm')) else '')
                outcome = st.text_input("Outcome Name", str(row_data.get('outcome_name', '')) if not pd.isna(row_data.get('outcome_name')) else '')
                coef = st.text_input("Coefficient (effect size)", str(row_data.get('coefficient', '')) if not pd.isna(row_data.get('coefficient')) else '')
            with c2:
                se = st.text_input("Standard Error", str(row_data.get('standard_error', '')) if not pd.isna(row_data.get('standard_error')) else '')
                pval = st.text_input("P-Value", str(row_data.get('p_value', '')) if not pd.isna(row_data.get('p_value')) else '')
                sig = st.text_input("Significance (*, **, ***)", str(row_data.get('significance', '')) if not pd.isna(row_data.get('significance')) else '')
            
            st.markdown("---")
            st.markdown("**📄 Original cell text from PDF:**")
            cell_text = str(row_data.get('literal_cell_text', 'N/A'))
            st.code(cell_text, language=None)
            
            st.markdown("---")
            b1, b2, b3 = st.columns(3)
            confirm_btn = b1.form_submit_button("✅ Confirm", type="primary", help="Extraction is correct")
            reject_btn = b2.form_submit_button("❌ Reject", help="Not a treatment effect")
            edit_btn = b3.form_submit_button("💾 Save Edits", help="Save your corrections")
            
            if confirm_btn:
                validation_results[row_key] = {
                    'status': 'confirmed', 
                    'timestamp': datetime.now().isoformat(),
                    'reviewer': user_email,
                    'original': {
                        'treatment_arm': str(row_data.get('treatment_arm', '')),
                        'outcome_name': str(row_data.get('outcome_name', '')),
                        'coefficient': str(row_data.get('coefficient', '')),
                        'standard_error': str(row_data.get('standard_error', '')),
                        'p_value': str(row_data.get('p_value', '')),
                        'significance': str(row_data.get('significance', ''))
                    }
                }
                save_validation_results(validation_results)
                # Auto-advance to next row
                if st.session_state.get('nav_row', 0) < len(filtered_indices) - 1:
                    st.session_state['nav_row'] = st.session_state.get('nav_row', 0) + 1
                st.rerun()
            if reject_btn:
                validation_results[row_key] = {
                    'status': 'rejected',
                    'timestamp': datetime.now().isoformat(), 
                    'reviewer': user_email,
                    'reason': 'Not a treatment effect'
                }
                save_validation_results(validation_results)
                # Auto-advance to next row
                if st.session_state.get('nav_row', 0) < len(filtered_indices) - 1:
                    st.session_state['nav_row'] = st.session_state.get('nav_row', 0) + 1
                st.rerun()
            if edit_btn:
                validation_results[row_key] = {
                    'status': 'edited',
                    'timestamp': datetime.now().isoformat(),
                    'reviewer': user_email,
                    'original': {
                        'treatment_arm': str(row_data.get('treatment_arm', '')),
                        'outcome_name': str(row_data.get('outcome_name', '')),
                        'coefficient': str(row_data.get('coefficient', '')),
                        'standard_error': str(row_data.get('standard_error', '')),
                        'p_value': str(row_data.get('p_value', '')),
                        'significance': str(row_data.get('significance', ''))
                    },
                    'edited': {
                        'treatment_arm': treatment, 
                        'outcome_name': outcome, 
                        'coefficient': coef, 
                        'standard_error': se, 
                        'p_value': pval, 
                        'significance': sig
                    }
                }
                save_validation_results(validation_results)
                st.success("✅ Edits saved!")
                # Auto-advance to next row
                if st.session_state.get('nav_row', 0) < len(filtered_indices) - 1:
                    st.session_state['nav_row'] = st.session_state.get('nav_row', 0) + 1
                st.rerun()
        
        # Show previous edits if any
        if current_status == 'edited':
            st.markdown("---")
            st.markdown("### 📝 Your Previous Edits")
            prev_edit = validation_results.get(row_key, {}).get('edited', {})
            if prev_edit:
                edit_df = pd.DataFrame([prev_edit]).T
                edit_df.columns = ['Edited Value']
                st.dataframe(edit_df, use_container_width=True)

# ============== Main ==============

def main():
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
    
    if not st.session_state['authenticated']:
        login_form()
        return
    
    with st.sidebar:
        if st.button("🚪 Logout"):
            for key in ['authenticated', 'user_email', 'is_admin']:
                st.session_state[key] = None
            st.rerun()
    
    if st.session_state.get('is_admin'):
        mode = st.sidebar.radio("Mode", ["👑 Admin", "📋 Review", "💾 Database"])
        if mode == "👑 Admin":
            admin_panel()
        elif mode == "📋 Review":
            reviewer_interface(st.session_state['user_email'])
        else:
            database_viewer()
    else:
        reviewer_interface(st.session_state['user_email'])

def database_viewer():
    """View the validation database (admin only)."""
    st.title("💾 Validation Database")
    
    validation_results = load_validation_results()
    
    if not validation_results:
        st.info("No validation results yet.")
        return
    
    st.markdown(f"**Total records:** {len(validation_results)}")
    
    # Convert to DataFrame for viewing
    records = []
    for key, val in validation_results.items():
        parts = key.rsplit('_', 1)
        study_id = parts[0] if len(parts) > 1 else key
        row_num = parts[1] if len(parts) > 1 else '0'
        
        record = {
            'study_id': study_id,
            'row': row_num,
            'status': val.get('status', 'unknown'),
            'reviewer': val.get('reviewer', 'unknown'),
            'timestamp': val.get('timestamp', '')[:19] if val.get('timestamp') else '',
            'has_edits': 'edited' in val
        }
        records.append(record)
    
    df = pd.DataFrame(records)
    
    # Filters
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.multiselect("Filter by status", 
                                       options=['confirmed', 'rejected', 'edited', 'pending'],
                                       default=['confirmed', 'rejected', 'edited'])
    with col2:
        reviewer_filter = st.selectbox("Filter by reviewer", 
                                       options=['All'] + list(df['reviewer'].unique()))
    
    filtered_df = df[df['status'].isin(status_filter)]
    if reviewer_filter != 'All':
        filtered_df = filtered_df[filtered_df['reviewer'] == reviewer_filter]
    
    st.dataframe(filtered_df.sort_values(['study_id', 'row']), use_container_width=True, height=400)
    
    # Export option
    st.markdown("---")
    st.markdown("### Export Data")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Download as JSON"):
            st.download_button(
                label="Download validation_results.json",
                data=json.dumps(validation_results, indent=2),
                file_name="validation_results.json",
                mime="application/json"
            )
    
    with col2:
        if st.button("📥 Download as CSV"):
            # Create detailed CSV
            detailed_records = []
            for key, val in validation_results.items():
                parts = key.rsplit('_', 1)
                study_id = parts[0] if len(parts) > 1 else key
                row_num = parts[1] if len(parts) > 1 else '0'
                
                record = {
                    'study_id': study_id,
                    'row': row_num,
                    'status': val.get('status', ''),
                    'reviewer': val.get('reviewer', ''),
                    'timestamp': val.get('timestamp', ''),
                }
                
                # Add original values
                orig = val.get('original', {})
                for k, v in orig.items():
                    record[f'original_{k}'] = v
                
                # Add edited values
                edited = val.get('edited', {})
                for k, v in edited.items():
                    record[f'edited_{k}'] = v
                
                detailed_records.append(record)
            
            export_df = pd.DataFrame(detailed_records)
            st.download_button(
                label="Download validation_results.csv",
                data=export_df.to_csv(index=False),
                file_name="validation_results.csv",
                mime="text/csv"
            )
    
    st.markdown("---")
    st.markdown("### Raw Database Location")
    st.code(str(VALIDATION_PATH), language=None)
    st.caption("All changes are automatically saved to this JSON file.")

if __name__ == "__main__":
    main()
