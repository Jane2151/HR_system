import html
import os
import tempfile

import altair as alt
import pandas as pd
import streamlit as st

from database import PIPELINE_STAGES, find_duplicate, get_all_resumes, get_pipeline_counts, init_db, save_resume
from extractor import parse_resume


def _render_box(inner_html: str) -> None:
    # Fixed light background with an explicit dark text color, so the box stays
    # readable regardless of the viewer's light/dark Streamlit theme.
    st.markdown(
        f'<div style="background:#f0f2f6;color:#1a1a1a;border-left:4px solid #0078D4;'
        f'padding:8px 12px;margin-bottom:8px;border-radius:4px;font-size:14px">'
        f'{inner_html}</div>',
        unsafe_allow_html=True,
    )


def _render_entries(entries: list[dict]) -> None:
    for entry in entries:
        inner = f"<strong>{html.escape(entry['header'])}</strong>"
        if entry["bullets"]:
            bullets_html = "".join(f"<li>{html.escape(b)}</li>" for b in entry["bullets"])
            inner += f'<ul style="margin:6px 0 0 0;padding-left:18px">{bullets_html}</ul>'
        _render_box(inner)


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
    # silently trigger a second OpenRouter call and could fail on a transient API error.
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
                st.error(f"Failed to extract resume data (OpenRouter API error): {e}")
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
            _render_box(html.escape(entry))

    with col_right:
        st.subheader("🛠️ Other Skills")
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

    st.subheader("💼 Experience")
    if data["experience"]:
        _render_entries(data["experience"])
    else:
        st.info("No work experience listed.")

    st.subheader("🧩 Projects")
    if data["projects"]:
        _render_entries(data["projects"])
    else:
        st.info("No projects listed.")

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
            st.success(f"Saved **{data['name']}** to the database — added to the Screening stage.")
            st.rerun()

st.divider()

# ── Recruitment Dashboard ──────────────────────────────────────────────────────
st.subheader("📊 Recruitment Dashboard")

dashboard_df = get_all_resumes()

st.metric("Total Candidates", len(dashboard_df))

if dashboard_df.empty:
    st.info("No candidates yet. Upload and save a resume above to get started.")
else:
    counts = get_pipeline_counts()
    chart_df = pd.DataFrame({
        "Stage": PIPELINE_STAGES,
        "Candidates": [counts[stage] for stage in PIPELINE_STAGES],
    })

    # Ordinal blue ramp for the funnel stages (one hue, light -> dark = depth in
    # the pipeline). Only the darkest step swaps for dark mode so it doesn't
    # sink below the 2:1 legibility floor on the dark chart surface.
    theme_type = st.context.theme.type or "light"
    offer_color = "#184f95" if theme_type == "dark" else "#0d366b"
    stage_colors = ["#86b6ef", "#3987e5", "#1c5cab", offer_color]

    bars = (
        alt.Chart(chart_df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("Stage:N", sort=PIPELINE_STAGES, title=None),
            y=alt.Y("Candidates:Q", title="Candidates"),
            color=alt.Color(
                "Stage:N",
                sort=PIPELINE_STAGES,
                scale=alt.Scale(domain=PIPELINE_STAGES, range=stage_colors),
                legend=None,
            ),
            tooltip=[alt.Tooltip("Stage:N"), alt.Tooltip("Candidates:Q")],
        )
    )
    labels = bars.mark_text(dy=-8).encode(text="Candidates:Q")

    st.altair_chart(bars + labels, width="stretch")
