"""TrussLab year selector. Run with: streamlit run app.py."""
from pathlib import Path
import runpy

import streamlit as st

st.set_page_config(page_title="TrussLab | EG1011", page_icon="🔺", layout="wide", initial_sidebar_state="expanded")

ROOT = Path(__file__).resolve().parent
YEARS = (2027, 2026)


def change_year():
    previous = st.session_state.get("_tl_active_year")
    if previous == 2026:
        st.session_state["_tl_2026_snapshot"] = {
            key: value for key, value in st.session_state.items()
            if not key.startswith("_tl") and "editor" not in key
            and not key.endswith("_button")
        }
    for key in list(st.session_state):
        if not key.startswith("_tl"):
            del st.session_state[key]
    selected = st.session_state["_tl_year"]
    if selected == 2026:
        for key, value in st.session_state.get("_tl_2026_snapshot", {}).items():
            st.session_state[key] = value
    st.session_state["_tl_active_year"] = selected


st.sidebar.selectbox(
    "Practical year", YEARS, key="_tl_year",
    format_func=lambda year: f"{year} · Latest" if year == YEARS[0] else str(year),
    on_change=change_year,
)
st.session_state.setdefault("_tl_active_year", st.session_state["_tl_year"])
st.sidebar.caption(f"You are using the {st.session_state['_tl_year']} practical.")

if st.session_state["_tl_year"] == 2026:
    runpy.run_path(str(ROOT / "app_2026.py"), run_name="__main__")
else:
    from app_2027 import main
    main(ROOT)
