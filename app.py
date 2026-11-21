"""TrussLab year selector. Run with: streamlit run app.py."""
from pathlib import Path
import hashlib
from importlib.machinery import ModuleSpec
import runpy
import sys
import types

import streamlit as st

st.set_page_config(page_title="TrussLab | EG1011", page_icon="🔺", layout="wide", initial_sidebar_state="expanded")

ROOT = Path(__file__).resolve().parent
YEARS = (2027, 2026)


@st.cache_resource(show_spinner=False)
def load_2027_version(sources: tuple, root_path: str):
    """Load matching app, core and report modules in a private package.

    The cache key includes every source file, including helper-only updates.
    Relative imports use this package's modules, never old absolute imports
    left in Python's cache. Existing sessions can finish using their revision;
    loading a new one does not mutate modules used by another student.
    """
    version=hashlib.sha256(b"\0".join(name.encode()+b"\0"+source for name,source in sources)).hexdigest()
    location=hashlib.sha256(root_path.encode()).hexdigest()[:12]
    name="_trusslab_2027_"+version+"_"+location
    package=types.ModuleType(name)
    package.__file__=str(Path(root_path)/"app.py")
    package.__package__=name
    package.__path__=[root_path]
    package.__spec__=ModuleSpec(name,loader=None,is_package=True)
    sys.modules[name]=package
    loaded=[name]
    try:
        # Core first, then reports, then the app: dependencies are registered
        # before the next module executes its standard relative imports.
        for filename,source in sources:
            stem=Path(filename).stem
            module_name=name+"."+stem
            script_path=str(Path(root_path)/filename)
            module=types.ModuleType(module_name)
            module.__file__=script_path
            module.__package__=name
            module.__spec__=ModuleSpec(module_name,loader=None,origin=script_path)
            sys.modules[module_name]=module
            loaded.append(module_name)
            setattr(package,stem,module)
            exec(compile(source,script_path,"exec"),module.__dict__)
    except BaseException:
        for module_name in reversed(loaded):
            sys.modules.pop(module_name,None)
        raise
    return package.app_2027


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
    source_files=("trusslab_2027_core.py","trusslab_2027_reports.py","app_2027.py")
    sources=tuple((name,(ROOT/name).read_bytes()) for name in source_files)
    load_2027_version(sources,str(ROOT)).main(ROOT)
