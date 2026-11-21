"""TrussLab year selector. Run with: streamlit run app.py."""
from pathlib import Path
import hashlib
import runpy
import sys
import types

import streamlit as st

st.set_page_config(page_title="TrussLab | EG1011", page_icon="🔺", layout="wide", initial_sidebar_state="expanded")

ROOT = Path(__file__).resolve().parent
YEARS = (2027, 2026)


@st.cache_resource(show_spinner=False)
def load_2027_version(source: bytes, script_path: str):
    """Cache each source revision separately, never a stale imported module.

    The resource cache serialises initialisation for concurrent sessions. All
    student data remains in Streamlit session state and existing progress files.
    """
    version=hashlib.sha256(source).hexdigest()
    location=hashlib.sha256(script_path.encode()).hexdigest()[:12]
    name="_trusslab_2027_"+version+"_"+location
    module=types.ModuleType(name)
    module.__file__=script_path
    module.__package__=""
    exec(compile(source,script_path,"exec"),module.__dict__)
    sys.modules[name]=module
    return module


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
    script=ROOT/"app_2027.py"
    load_2027_version(script.read_bytes(),str(script)).main(ROOT)
