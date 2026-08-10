import html
import os
import tempfile

import streamlit as st

from database import delete_resume, find_duplicate, get_all_resumes, init_db, save_resume
from extractor import parse_resume

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HR digitalization",
    page_icon="📄",
    layout="wide",
)

init_db()

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📄 HR digitalization")
st.markdown(
    "Upload PDF resumes to automatically extract candidate information and store it for review."
)
st.divider()

# ── Upload & Parse ────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader("Upload a Resume (PDF only)", type=["pdf"])

if uploaded_file:
    # Only parse (and call the LLM) once per uploaded file — Streamlit reruns this
    # whole script on every button click, so without caching, clicking "Save" would
    # silently trigger a second Gemini call and could fail on a transient API error.
    if st.session_state.get("parsed_file_id") != uploaded_file.file_id:
        with st.spinner("Reading and extracting information…"):
            # Write to a temp file so pdfplumber can open it by path
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name

            try:
                data = parse_resume(tmp_path)
            except Exception as e:
                os.unlink(tmp_path)
                st.error(f"Failed to extract resume data (Gemini API error): {e}")
                st.stop()
            os.unlink(tmp_path)

        st.session_state["parsed_file_id"] = uploaded_file.file_id
        st.session_state["parsed_data"] = data

    data = st.session_state["parsed_data"]

    st.success("Resume parsed successfully!")

    # ── Results layout ────────────────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("👤 Candidate Info")
        st.write(f"**Name:** {data['name']}")
        st.write(f"**Email:** {data['email']}")
        st.write(f"**Phone:** {data['phone']}")

        st.subheader("🎓 Education")
        for entry in data["education"]:
            st.markdown(
                f'<div style="background:#f0f2f6;border-left:4px solid #0078D4;'
                f'padding:8px 12px;margin-bottom:8px;border-radius:4px;font-size:14px">'
                f'{html.escape(entry)}</div>',
                unsafe_allow_html=True,
            )

    with col_right:
        st.subheader("🛠️ Skills Detected")
        if data["skills"]:
            # Display skills as badge-style pills
            badge_html = " ".join(
                f'<span style="background:#0078D4;color:white;padding:4px 10px;'
                f'border-radius:12px;margin:3px;display:inline-block;font-size:13px">'
                f'{html.escape(skill)}</span>'
                for skill in data["skills"]
            )
            st.markdown(badge_html, unsafe_allow_html=True)
        else:
            st.info("No matching skills found in the resume.")

    st.divider()

    if st.button("💾 Save to Database", type="primary"):
        duplicate = find_duplicate(data["email"])
        if duplicate:
            dup_name, dup_uploaded_at = duplicate
            st.warning(
                f"A resume with email **{data['email']}** was already saved as "
                f"**{dup_name}** on {str(dup_uploaded_at)[:16]}. Not saved again to avoid duplicates."
            )
        else:
            save_resume(uploaded_file.name, data)
            st.success(f"Saved **{data['name']}** to the database.")
            st.rerun()

# ── Database Table ────────────────────────────────────────────────────────────
st.subheader("📊 All Parsed Resumes")

df = get_all_resumes()

if df.empty:
    st.info("No resumes saved yet. Upload a PDF above and click Save.")
else:
    # Show count metric
    st.metric("Total Candidates", len(df))

    # ── Per-row table with individual delete buttons ──────────────────────────
    header = st.columns([2, 2, 2, 2, 1])
    for col, label in zip(header, ["Name", "Email", "Phone", "Uploaded At", "Action"]):
        col.markdown(f"**{label}**")
    st.divider()

    for _, row in df.iterrows():
        cols = st.columns([2, 2, 2, 2, 1])
        cols[0].write(row["name"])
        cols[1].write(row["email"])
        cols[2].write(row["phone"])
        cols[3].write(str(row["uploaded_at"])[:16])
        if cols[4].button("🗑️ Delete", key=f"del_{row['id']}"):
            delete_resume(int(row["id"]))
            st.success(f"Deleted record for **{row['name']}**.")
            st.rerun()

    st.divider()

    # ── Download CSV ──────────────────────────────────────────────────────────
    csv = df.drop(columns=["id"]).to_csv(index=False)
    st.download_button(
        label="⬇️ Download All as CSV",
        data=csv,
        file_name="parsed_resumes.csv",
        mime="text/csv",
    )
