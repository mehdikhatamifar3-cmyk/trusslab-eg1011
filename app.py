from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Polygon
import numpy as np
import pandas as pd
import streamlit as st

from report_builder import build_practical_report


st.set_page_config(
    page_title="TrussLab | EG1011",
    page_icon="🔺",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_DIR = Path(__file__).resolve().parent
ASSET_DIR = APP_DIR / "assets"
G = 9.81
APP_VERSION = "14"

PHYSICAL_MODE = "Physical laboratory"
ONLINE_MODE = "Online simulated practical"
MODE_OPTIONS = ["Select practical mode...", PHYSICAL_MODE, ONLINE_MODE]

JCU_ID_PATTERN = re.compile(r"^\d{8}$")
_ONLINE_DATASET_SALT = "EG1011_TRUSSLAB_CONTROLLED_DATA_V9"

# Four confidential, controlled online datasets. The student-facing app does
# not display the set identifier. Values are signed dial displacement in mm.
ONLINE_DATASETS: Tuple[Dict[int, Dict[str, float]], ...] = (
    {
        0:  {"AF": 0.000, "FE": 0.001, "AE": -0.001, "AB": 0.000, "EB": 0.001},
        10: {"AF": -0.002, "FE": 0.001, "AE": -0.174, "AB": 0.121, "EB": 0.257},
        20: {"AF": -0.004, "FE": 0.001, "AE": -0.350, "AB": 0.241, "EB": 0.513},
        30: {"AF": -0.006, "FE": -0.001, "AE": -0.525, "AB": 0.361, "EB": 0.770},
    },
    {
        0:  {"AF": 0.001, "FE": -0.001, "AE": 0.000, "AB": 0.001, "EB": -0.001},
        10: {"AF": 0.001, "FE": -0.001, "AE": -0.178, "AB": 0.118, "EB": 0.251},
        20: {"AF": 0.002, "FE": -0.002, "AE": -0.356, "AB": 0.236, "EB": 0.503},
        30: {"AF": 0.003, "FE": -0.003, "AE": -0.534, "AB": 0.354, "EB": 0.756},
    },
    {
        0:  {"AF": -0.001, "FE": 0.001, "AE": -0.001, "AB": 0.000, "EB": 0.001},
        10: {"AF": -0.001, "FE": 0.002, "AE": -0.172, "AB": 0.122, "EB": 0.260},
        20: {"AF": -0.002, "FE": 0.003, "AE": -0.344, "AB": 0.244, "EB": 0.520},
        30: {"AF": -0.003, "FE": 0.004, "AE": -0.517, "AB": 0.366, "EB": 0.780},
    },
    {
        0:  {"AF": 0.001, "FE": 0.000, "AE": -0.001, "AB": 0.001, "EB": 0.000},
        10: {"AF": 0.002, "FE": -0.001, "AE": -0.181, "AB": 0.116, "EB": 0.249},
        20: {"AF": 0.004, "FE": 0.000, "AE": -0.362, "AB": 0.232, "EB": 0.498},
        30: {"AF": 0.005, "FE": 0.001, "AE": -0.543, "AB": 0.348, "EB": 0.748},
    },
)


# This key is owned by Streamlit's data_editor widget. It must not be
# reassigned by the general state-persistence workaround.
PHYSICAL_EDITOR_KEY = "physical_lab_editor_v7"

ALL_MEMBERS = ["AF", "FE", "ED", "DC", "AB", "BC", "AE", "EC", "EB"]
INSTRUMENTED = ["AF", "FE", "AE", "AB", "EB"]
EXPECTED_STATE = {
    "AF": "Zero force",
    "FE": "Zero force",
    "AE": "Compression",
    "AB": "Tension",
    "EB": "Tension",
}

SAFETY_CHECK_KEYS = (
    "safety_attendance_briefing",
    "safety_ppe_clothing",
    "safety_equipment_inspection",
    "safety_loading_controls",
    "safety_supervision_housekeeping",
    "safety_emergency_reporting",
    "safety_final_declaration",
)

COLORS = {
    "member": "#334155",
    "joint": "#111827",
    "load": "#C62828",
    "reaction": "#1565C0",
    "tension": "#2E7D32",
    "compression": "#C62828",
    "zero": "#64748B",
    "ring": "#0B4F8A",
    "guide": "#94A3B8",
    "warning": "#B45309",
}


def load_config() -> Dict[str, object]:
    defaults = {
        "course_code": "EG1011",
        "course_name": "Statics and Dynamics",
        "practical_number": "Practical",
        "practical_title": "Forces in a Plane Truss",
        "allowed_tension_N": 300.0,
        "allowed_compression_N": 220.0,
        "approved_max_mass_kg": 30.0,
        "report_prefix": "EG1011_Truss_Practical",
    }
    path = APP_DIR / "app_config.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        defaults.update(loaded)
    except Exception:
        pass
    return defaults


CONFIG = load_config()
TENSION_LIMIT = float(CONFIG["allowed_tension_N"])
COMPRESSION_LIMIT = float(CONFIG["allowed_compression_N"])
APPROVED_MASS = float(CONFIG["approved_max_mass_kg"])


def load_calibration() -> Tuple[Dict[str, float], bool]:
    defaults = {"AF": 420.0, "FE": 405.0, "AE": 395.0, "AB": 410.0, "EB": 385.0}
    path = APP_DIR / "calibration.csv"
    if not path.exists():
        return defaults, True
    try:
        table = pd.read_csv(path)
        required = {"member", "factor_N_per_mm"}
        if not required.issubset(table.columns):
            return defaults, True
        values = {
            str(row["member"]).strip().upper(): float(row["factor_N_per_mm"])
            for _, row in table.iterrows()
        }
        if not all(member in values and values[member] > 0 for member in INSTRUMENTED):
            return defaults, True
        return {member: values[member] for member in INSTRUMENTED}, False
    except Exception:
        return defaults, True


CALIBRATION, USING_DEMO_CALIBRATION = load_calibration()


def load_image_b64(filename: str) -> str:
    path = ASSET_DIR / filename
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("ascii")


APPARATUS_B64 = load_image_b64("apparatus_photo.png")
JCU_LOGO_B64 = load_image_b64("jcu_logo.png")
DESIGNER_NAME = "Dr Mehdi Khatamifar"

st.markdown(
    """
    <style>
      .stApp { background:#ffffff; }
      .block-container { max-width:1480px; padding-top:1.0rem; padding-bottom:2.2rem; }
      [data-testid="stSidebar"] {
        background:linear-gradient(180deg,#f8fafc 0%,#eef3f7 55%,#e8eef4 100%);
        border-right:1px solid #d5dde7;
      }
      [data-testid="stSidebar"] > div:first-child { padding-top:0.8rem; }
      [data-testid="stSidebar"] [data-testid="stRadio"] > div { gap:0.28rem; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label {
        background:rgba(255,255,255,0.88);
        border:1px solid #dbe3ec;
        border-radius:10px;
        padding:0.50rem 0.62rem;
        margin:0.06rem 0;
        transition:all 0.16s ease;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        border-color:#9bb8d2;
        background:#ffffff;
        transform:translateX(2px);
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background:#e8f2ff;
        border-color:#5b91bd;
        box-shadow:inset 4px 0 0 #0B4F8A;
      }
      [data-testid="stSidebar"] [data-testid="stProgress"] > div > div { background-color:#0B4F8A; }
      .sidebar-brand {
        position:relative;
        background:linear-gradient(180deg,#ffffff 0%,#f4f8fc 100%);
        color:#172033;
        border-radius:13px;
        padding:14px 15px 13px 17px;
        margin:0 0 14px;
        border:1px solid #d4e0eb;
        box-shadow:0 4px 14px rgba(15,23,42,0.055);
        overflow:hidden;
      }
      .sidebar-brand::before {
        content:"";
        position:absolute;
        left:0;
        top:0;
        bottom:0;
        width:4px;
        background:#0B4F8A;
      }
      .sidebar-brand .course {
        color:#5f7184;
        font-size:9.5px;
        font-weight:800;
        letter-spacing:0.105em;
        text-transform:uppercase;
      }
      .sidebar-brand .title {
        color:#0f3555;
        font-size:22px;
        font-weight:800;
        line-height:1.08;
        margin-top:4px;
      }
      .sidebar-brand .subtitle {
        color:#607083;
        font-size:11.2px;
        line-height:1.42;
        margin-top:7px;
      }
      .sidebar-brand .rule {
        width:34px;
        height:2px;
        border-radius:999px;
        background:#7fa9cc;
        margin-top:10px;
      }
      .sidebar-section-label {
        color:#526274; font-size:10px; font-weight:800; letter-spacing:0.12em;
        text-transform:uppercase; margin:14px 2px 7px;
      }
      .sidebar-card {
        background:rgba(255,255,255,0.92); border:1px solid #dbe3ec; border-radius:11px;
        padding:11px 12px; margin:8px 0; box-shadow:0 2px 8px rgba(15,23,42,0.035);
      }
      .sidebar-card .label { color:#64748b; font-size:10px; font-weight:800; letter-spacing:0.09em; text-transform:uppercase; }
      .sidebar-card .value { color:#172033; font-size:13px; font-weight:700; margin-top:3px; }
      .sidebar-card .meta { color:#64748b; font-size:11px; line-height:1.42; margin-top:5px; }
      .sidebar-badge {
        display:inline-block; padding:3px 8px; border-radius:999px;
        background:#e8f2ff; color:#0B4F8A; border:1px solid #c7ddf5;
        font-size:10px; font-weight:800; letter-spacing:0.04em; margin-top:7px;
      }
      .sidebar-status-good { color:#166534; background:#ecfdf3; border:1px solid #bbf7d0; border-radius:9px; padding:8px 10px; font-size:11px; margin:7px 0; }
      .sidebar-status-warn { color:#854d0e; background:#fffbeb; border:1px solid #fde68a; border-radius:9px; padding:8px 10px; font-size:11px; margin:7px 0; }
      .sidebar-footer { color:#7a8796; font-size:10.5px; line-height:1.45; margin-top:13px; padding:10px 3px 2px; border-top:1px solid #d7dfe8; }
      header[data-testid="stHeader"] { background:transparent; }
      #MainMenu, footer { visibility:hidden; }
      .app-header { display:grid; grid-template-columns:280px 1fr 260px; gap:24px; align-items:center; padding:8px 8px 18px; }
      .brand-box { border:1px solid #cbd5e1; border-radius:12px; background:#ffffff; padding:10px 14px; text-align:center; }
      .brand-box img { max-width:100%; height:auto; }
      .app-header-title h1 { margin:0; font-size:35px; line-height:1.05; color:#0f172a; }
      .app-header-title p { margin:8px 0 0; color:#334155; line-height:1.45; font-size:15px; }
      .app-header-author { text-align:right; color:#334155; font-size:13px; line-height:1.6; }
      .app-divider { height:1px; background:#d9dee5; margin:2px 0 18px; }
      .info { background:#e8f2ff; border:1px solid #c7ddf5; border-radius:10px; padding:13px 15px; color:#0f4c81; margin:8px 0 16px; }
      .hint { background:#ecfdf3; border:1px solid #bbf7d0; border-radius:10px; padding:11px 13px; color:#166534; margin:8px 0 14px; }
      .warning { background:#fff8e8; border:1px solid #f3d69b; border-radius:10px; padding:11px 13px; color:#7c4a03; margin:8px 0 14px; }
      .good { background:#ecfdf3; border:1px solid #bbf7d0; color:#166534; border-radius:9px; padding:10px 12px; margin:6px 0; }
      .bad { background:#fff1f2; border:1px solid #fecdd3; color:#9f1239; border-radius:9px; padding:10px 12px; margin:6px 0; }
      .card { border:1px solid #dfe4ea; border-radius:10px; padding:14px 16px; margin-bottom:14px; background:#fff; }
      .small-note { color:#64748b; font-size:13px; line-height:1.45; }
      div[data-testid="stMetric"] { background:#ffffff; border:1px solid #e2e8f0; padding:10px 12px; border-radius:10px; }
      @media (max-width:980px) {
        .app-header { grid-template-columns:1fr; text-align:center; }
        .app-header-author { text-align:center; }
        .brand-box { max-width:280px; margin:auto; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_header() -> None:
    logo_html = f"<img src=\"data:image/png;base64,{JCU_LOGO_B64}\" alt=\"JCU logo\">" if JCU_LOGO_B64 else "<div style=\"font-size:28px;font-weight:800;color:#0B4F8A\">JCU</div>"
    st.markdown(
        f"""
        <div class="app-header">
          <div class="brand-box">{logo_html}</div>
          <div class="app-header-title">
            <h1>TrussLab</h1>
            <p>A complete physical or online practical for tension, compression, zero-force members, selected equilibrium calculations and a short engineering safe-load decision.</p>
          </div>
          <div class="app-header-author">
            {CONFIG['course_code']} {CONFIG['course_name']}<br>
            <b>{CONFIG['practical_number']}</b><br>
            {CONFIG['practical_title']}<br><br>
            <b>Designed by</b><br>{DESIGNER_NAME}
          </div>
        </div>
        <div class="app-divider"></div>
        """,
        unsafe_allow_html=True,
    )


def blank_lab_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Member": INSTRUMENTED,
            "10 kg (mm)": [np.nan] * len(INSTRUMENTED),
            "20 kg (mm)": [np.nan] * len(INSTRUMENTED),
            "30 kg (mm)": [np.nan] * len(INSTRUMENTED),
        }
    )


def initialise_state() -> None:
    defaults = {
        "student_name": "",
        "student_id": "",
        "group": "",
        "practical_mode": MODE_OPTIONS[0],
        "previous_mode": MODE_OPTIONS[0],
        "lab_data": blank_lab_dataframe(),
        "captured_loads": [],
        "zero_return": "Not checked",
        "prelab_score": 0,
        "prediction_score": 0,
        "prelab_complete": False,
        "prediction_complete": False,
        "lab_complete": False,
        "calculation_complete": False,
        "experimental_calc_complete": False,
        "part_b_complete": False,
        "report_bytes": None,
        "report_filename": "",
        "simulation_student_id": "",
        "clear_apparatus_requested": False,
        "apparatus_clear_notice": False,
        "safety_complete": False,
        "safety_acknowledged_at": "",
        "safety_acknowledged_student_id": "",
        "safety_acknowledged_student_name": "",
        "safety_acknowledged_group": "",
        "safety_attendance_briefing": False,
        "safety_ppe_clothing": False,
        "safety_equipment_inspection": False,
        "safety_loading_controls": False,
        "safety_supervision_housekeeping": False,
        "safety_emergency_reporting": False,
        "safety_final_declaration": False,
        "pre_q1": None,
        "pre_q2": None,
        "pre_q3": None,
        "pre_q4": None,
        "pre_q5": None,
        "online_mass": 10,
        "calc_w_input": None,
        "calc_ay_input": None,
        "calc_ae_input": None,
        "calc_ab_input": None,
        "calc_eb_input": None,
        "experimental_calc_input": None,
        "safe_test_mass": 30.0,
        "safe_mass_input": None,
        "critical_member_input": "Select...",
        "critical_type_input": None,
        "review_declaration": False,
        "calc_w": None,
        "calc_ay": None,
        "calc_ae": None,
        "calc_ab": None,
        "calc_eb": None,
        "experimental_calc": None,
        "safe_mass_answer": None,
        "critical_member_answer": "",
        "critical_type_answer": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialise_state()


def safety_gate_is_open(
    mode: str,
    checklist_complete: bool,
    confirmation_complete: bool,
    current_student_id: str,
    acknowledged_student_id: str,
    current_student_name: str,
    acknowledged_student_name: str,
    current_group: str,
    acknowledged_group: str,
) -> bool:
    """Pure safety-gate logic, separated for reliable testing."""
    if mode == ONLINE_MODE:
        return True
    if mode != PHYSICAL_MODE:
        return False
    return bool(
        checklist_complete
        and confirmation_complete
        and valid_jcu_student_id(current_student_id)
        and normalise_jcu_student_id(current_student_id) == normalise_jcu_student_id(acknowledged_student_id)
        and current_student_name.strip() == acknowledged_student_name.strip()
        and current_group.strip() == acknowledged_group.strip()
    )


def _safety_checklist_complete() -> bool:
    return all(bool(st.session_state.get(key, False)) for key in SAFETY_CHECK_KEYS)


def safety_requirement_complete() -> bool:
    return safety_gate_is_open(
        st.session_state.get("practical_mode", MODE_OPTIONS[0]),
        _safety_checklist_complete(),
        bool(st.session_state.get("safety_complete", False)),
        st.session_state.get("student_id", ""),
        st.session_state.get("safety_acknowledged_student_id", ""),
        st.session_state.get("student_name", ""),
        st.session_state.get("safety_acknowledged_student_name", ""),
        st.session_state.get("group", ""),
        st.session_state.get("safety_acknowledged_group", ""),
    )


def reset_safety_acknowledgement() -> None:
    st.session_state.safety_complete = False
    st.session_state.safety_acknowledged_at = ""
    st.session_state.safety_acknowledged_student_id = ""
    st.session_state.safety_acknowledged_student_name = ""
    st.session_state.safety_acknowledged_group = ""
    for key in SAFETY_CHECK_KEYS:
        st.session_state[key] = False


def require_safety_before_main_practical() -> bool:
    """Gate physical-laboratory sections until the attendance/safety step is complete."""
    if st.session_state.get("practical_mode") == PHYSICAL_MODE and not safety_requirement_complete():
        st.error("Complete Section 4: Lab attendance and safety before starting the apparatus data or later practical sections.")
        st.info("Return to Section 4, review every safety item, tick the acknowledgements and confirm the safety declaration.")
        return False
    return True

# Streamlit removes the state of widgets that are not rendered on the current
# section. Reassigning ordinary widget keys interrupts that cleanup so entries
# remain available when navigating. Complex widgets such as data_editor own
# their internal session-state value and must be excluded from this operation.
_WIDGET_MANAGED_KEYS = {
    PHYSICAL_EDITOR_KEY,
    "physical_lab_editor",
    "clear_apparatus_data_button",  # legacy key from v10; never preserve/reassign
}


def preserve_cross_section_state() -> None:
    """Keep ordinary widget values while leaving complex widget state untouched."""
    for state_key in list(st.session_state.keys()):
        if state_key not in _WIDGET_MANAGED_KEYS:
            st.session_state[state_key] = st.session_state[state_key]



def reset_report_cache() -> None:
    st.session_state.report_bytes = None
    st.session_state.report_filename = ""


def clear_mode_dependent_work() -> None:
    st.session_state.lab_data = blank_lab_dataframe()
    st.session_state.captured_loads = []
    st.session_state.zero_return = "Not checked"
    st.session_state.lab_complete = False
    st.session_state.experimental_calc_complete = False
    st.session_state.simulation_student_id = ""
    # Remove widget-owned editor state so the next physical table is rebuilt
    # cleanly from lab_data. The legacy key is removed for users upgrading from v6.
    st.session_state.pop(PHYSICAL_EDITOR_KEY, None)
    st.session_state.pop("physical_lab_editor", None)
    reset_report_cache()


def request_clear_mode_dependent_work() -> None:
    st.session_state.clear_apparatus_requested = True


def apply_pending_apparatus_clear() -> None:
    # v10 used an explicit key on the clear button. Remove any stale value
    # before Streamlit creates widgets in the current run.
    st.session_state.pop("clear_apparatus_data_button", None)
    if st.session_state.get("clear_apparatus_requested", False):
        st.session_state.clear_apparatus_requested = False
        clear_mode_dependent_work()
        st.session_state.apparatus_clear_notice = True


# These must run before render_header() and before the selected section creates
# any widgets. This prevents StreamlitValueAssignmentNotAllowedError.
apply_pending_apparatus_clear()
preserve_cross_section_state()


def theoretical_forces(mass_kg: float) -> Dict[str, float]:
    """Signed member forces in N. Positive = tension; negative = compression."""
    w = float(mass_kg) * G
    return {
        "AF": 0.0,
        "FE": 0.0,
        "ED": 0.0,
        "DC": 0.0,
        "AB": w / 2.0,
        "BC": w / 2.0,
        "AE": -w / math.sqrt(2.0),
        "EC": -w / math.sqrt(2.0),
        "EB": w,
    }


def force_state(force: float, tolerance: float = 1e-7) -> str:
    if abs(force) <= tolerance:
        return "Zero force"
    return "Tension" if force > 0 else "Compression"


def member_colour(force: float) -> str:
    state = force_state(force)
    if state == "Tension":
        return COLORS["tension"]
    if state == "Compression":
        return COLORS["compression"]
    return COLORS["zero"]


def _draw_ground(ax, x_left: float, x_right: float, y: float) -> None:
    """Draw a conventional ground line with short hatch marks."""
    ax.plot([x_left, x_right], [y, y], color="black", linewidth=1.8, zorder=1)
    hatch_spacing = 0.10
    x = x_left + 0.02
    while x <= x_right - 0.02:
        ax.plot([x, x - 0.055], [y, y - 0.07], color="black", linewidth=0.9, zorder=1)
        x += hatch_spacing


def add_supports(ax) -> None:
    """Draw a pin at A and a roller at C using standard statics symbols."""
    # Pin support at A: the joint is at the apex and the broad base sits on ground.
    pin = Polygon(
        [(0.0, -0.015), (-0.20, -0.27), (0.20, -0.27)],
        closed=True,
        facecolor="white",
        edgecolor="black",
        linewidth=1.8,
        zorder=3,
    )
    ax.add_patch(pin)
    _draw_ground(ax, -0.31, 0.31, -0.34)

    # Roller support at C: triangular bearing above rollers and ground.
    roller = Polygon(
        [(4.0, -0.015), (3.80, -0.24), (4.20, -0.24)],
        closed=True,
        facecolor="white",
        edgecolor="black",
        linewidth=1.8,
        zorder=3,
    )
    ax.add_patch(roller)
    for x in (3.88, 4.00, 4.12):
        ax.add_patch(
            Circle((x, -0.315), 0.047, facecolor="white", edgecolor="black", linewidth=1.2, zorder=3)
        )
    _draw_ground(ax, 3.69, 4.31, -0.40)


def plot_apparatus(mass_kg: float = 0.0, show_force_colours: bool = False, title: str | None = None):
    points = {"A": (0.0, 0.0), "B": (2.0, 0.0), "C": (4.0, 0.0), "F": (0.0, 2.0), "E": (2.0, 2.0), "D": (4.0, 2.0)}
    pairs = [
        ("A", "F", "AF"), ("F", "E", "FE"), ("E", "D", "ED"), ("D", "C", "DC"),
        ("A", "B", "AB"), ("B", "C", "BC"), ("A", "E", "AE"), ("E", "C", "EC"), ("E", "B", "EB"),
    ]
    member_label_offsets = {
        "AF": (-0.24, 0.0), "FE": (0.0, 0.24), "ED": (0.0, 0.24), "DC": (0.24, 0.0),
        "AB": (0.0, -0.24), "BC": (0.0, -0.24), "AE": (-0.18, 0.22), "EC": (0.18, 0.22), "EB": (0.24, 0.0),
    }
    forces = theoretical_forces(mass_kg)
    fig, ax = plt.subplots(figsize=(9.7, 5.0))
    for start_pt, end_pt, name in pairs:
        state_colour = member_colour(forces[name])
        colour = state_colour if show_force_colours else COLORS["member"]
        ax.plot([points[start_pt][0], points[end_pt][0]], [points[start_pt][1], points[end_pt][1]], color=colour, linewidth=4, solid_capstyle="round", zorder=2)
        mx = (points[start_pt][0] + points[end_pt][0]) / 2
        my = (points[start_pt][1] + points[end_pt][1]) / 2
        ox, oy = member_label_offsets[name]
        label_colour = state_colour if show_force_colours else "#0B4F8A"
        ax.text(mx + ox, my + oy, name, fontsize=10, fontweight="bold", color=label_colour,
                bbox=dict(facecolor="white", edgecolor=label_colour, boxstyle="round,pad=0.18", alpha=0.96), zorder=8)
        if name in INSTRUMENTED:
            ax.add_patch(Circle((mx, my), 0.16, facecolor="white", edgecolor=COLORS["ring"], linewidth=3, zorder=4))
            ax.add_patch(Circle((mx, my), 0.052, facecolor="white", edgecolor=COLORS["ring"], linewidth=1.8, zorder=5))
    offsets = {"A": (-0.20, -0.16), "B": (-0.05, -0.36), "C": (0.15, -0.16), "F": (-0.20, 0.20), "E": (-0.02, 0.28), "D": (0.15, 0.20)}
    joint_colours = {"A": "#7C3AED", "B": "#D97706", "C": "#0891B2", "D": "#2563EB", "E": "#16A34A", "F": "#DC2626"}
    for label, (x, y) in points.items():
        ax.scatter([x], [y], s=75, color=COLORS["joint"], zorder=7)
        ox, oy = offsets[label]
        ax.text(x + ox, y + oy, label, fontsize=12, fontweight="bold", color=joint_colours[label],
                bbox=dict(facecolor="white", edgecolor=joint_colours[label], boxstyle="round,pad=0.16", alpha=0.96), zorder=9)
    add_supports(ax)
    if mass_kg > 0:
        ax.add_patch(FancyArrowPatch((2.0, -0.04), (2.0, -0.78), arrowstyle="-|>", mutation_scale=20, color=COLORS["load"], linewidth=2.8))
        ax.text(2.20, -0.65, f"{mass_kg:g} kg ({mass_kg * G:.1f} N)", fontsize=12, color="#991B1B",
                bbox=dict(facecolor="white", edgecolor="#991B1B", boxstyle="round,pad=0.18", alpha=0.96))
    if show_force_colours:
        ax.text(0.02, 2.42, "Green: tension     Red: compression     Grey: zero force", fontsize=11, color="#475569")
    ax.set_xlim(-0.60, 4.62)
    ax.set_ylim(-1.05, 2.70)
    ax.set_aspect("equal")
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=14, pad=8)
    fig.tight_layout()
    return fig


def normalise_jcu_student_id(student_id: str) -> str:
    return str(student_id).strip()


def valid_jcu_student_id(student_id: str) -> bool:
    return bool(JCU_ID_PATTERN.fullmatch(normalise_jcu_student_id(student_id)))


def _online_dataset_index(student_id: str) -> int:
    normalised = normalise_jcu_student_id(student_id)
    if not valid_jcu_student_id(normalised):
        raise ValueError("A valid eight-digit JCU student ID is required.")
    digest = hashlib.sha256(f"{_ONLINE_DATASET_SALT}|{normalised}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % len(ONLINE_DATASETS)


def simulated_readings(mass_kg: float, student_id: str, realistic: bool = True) -> Dict[str, float]:
    mass_key = int(round(float(mass_kg)))
    if mass_key not in (0, 10, 20, 30):
        raise ValueError("Online readings are available only for 0, 10, 20 and 30 kg.")
    if not realistic:
        forces = theoretical_forces(mass_key)
        return {member: float(forces[member] / CALIBRATION[member]) for member in INSTRUMENTED}
    dataset = ONLINE_DATASETS[_online_dataset_index(student_id)]
    return {member: float(dataset[mass_key][member]) for member in INSTRUMENTED}


def plot_dials(readings: Dict[str, float]):
    fig, axes = plt.subplots(1, 5, figsize=(12.2, 2.8))
    full_scale = max(0.85, max(abs(v) for v in readings.values()) * 1.15)
    for ax, member in zip(axes, INSTRUMENTED):
        value = readings[member]
        theta_min, theta_max = math.radians(-135), math.radians(135)
        angles = np.linspace(theta_min, theta_max, 200)
        ax.plot(np.cos(angles), np.sin(angles), color="#334155", linewidth=2)
        for fraction in np.linspace(0, 1, 9):
            theta = theta_min + fraction * (theta_max - theta_min)
            ax.plot([0.86 * math.cos(theta), math.cos(theta)], [0.86 * math.sin(theta), math.sin(theta)], color="#64748B", linewidth=1)
        clipped = max(-full_scale, min(full_scale, value))
        fraction = (clipped + full_scale) / (2 * full_scale)
        theta = theta_min + fraction * (theta_max - theta_min)
        ax.plot([0, 0.77 * math.cos(theta)], [0, 0.77 * math.sin(theta)], color="#C62828", linewidth=2.5)
        ax.add_patch(Circle((0, 0), 0.06, color="#111827"))
        ax.text(0, -0.48, f"{value:+.3f} mm", ha="center", fontsize=10, fontweight="bold")
        ax.text(0, 1.18, member, ha="center", fontsize=12, fontweight="bold")
        ax.text(-0.92, -0.82, "C", fontsize=9, color=COLORS["compression"])
        ax.text(0.83, -0.82, "T", fontsize=9, color=COLORS["tension"])
        ax.set_xlim(-1.12, 1.12)
        ax.set_ylim(-1.0, 1.30)
        ax.set_aspect("equal")
        ax.axis("off")
    fig.tight_layout()
    return fig


def data_quality_messages(dataframe: pd.DataFrame) -> List[Tuple[str, str]]:
    """Check completeness and basic measurement consistency without revealing solutions."""
    messages: List[Tuple[str, str]] = []
    for _, row in dataframe.iterrows():
        member = row["Member"]
        vals = [row["10 kg (mm)"], row["20 kg (mm)"], row["30 kg (mm)"]]
        if any(pd.isna(v) for v in vals):
            messages.append(("warning", f"{member}: one or more readings are missing."))
            continue
        vals = [float(v) for v in vals]
        magnitudes = [abs(v) for v in vals]
        if magnitudes[2] > 0.02 and (magnitudes[1] < 0.65 * magnitudes[0] or magnitudes[2] < 0.65 * magnitudes[1]):
            messages.append(("warning", f"{member}: the reading magnitude changes unexpectedly as load increases. Recheck the recorded values and units."))
        if max(magnitudes) > 2.0:
            messages.append(("warning", f"{member}: the recorded displacement is unusually large. Check whether the dial units were entered in millimetres."))
    if not messages:
        messages.append(("good", "The data are complete and no major recording inconsistency was detected. This is a data-quality check, not a solution check."))
    return messages

def plot_lab_readings(dataframe: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    loads = np.array([10.0, 20.0, 30.0])
    for _, row in dataframe.iterrows():
        values = np.array([row["10 kg (mm)"], row["20 kg (mm)"], row["30 kg (mm)"]], dtype=float)
        if np.isnan(values).any():
            continue
        ax.plot(loads, values, marker="o", linewidth=2, label=row["Member"])
    ax.axhline(0, color="#94A3B8", linewidth=0.9)
    ax.set_xlabel("Applied mass (kg)")
    ax.set_ylabel("Signed dial displacement (mm)")
    ax.set_title("Dial response as the applied mass increased")
    ax.grid(True, linewidth=0.4, alpha=0.45)
    ax.legend(ncol=5, loc="best")
    fig.tight_layout()
    return fig


def fig_to_png_bytes(fig, dpi: int = 180) -> bytes:
    stream = io.BytesIO()
    fig.savefig(stream, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return stream.getvalue()


def compare_table() -> pd.DataFrame:
    data = st.session_state.lab_data
    student_theory = {
        "AF": 0.0 if st.session_state.get("predict_AF") == "Zero force" else np.nan,
        "FE": 0.0 if st.session_state.get("predict_FE") == "Zero force" else np.nan,
        "AE": st.session_state.get("calc_ae_input"),
        "AB": st.session_state.get("calc_ab_input"),
        "EB": st.session_state.get("calc_eb_input"),
    }
    rows = []
    for member in INSTRUMENTED:
        raw = data.loc[data["Member"] == member, "30 kg (mm)"]
        reading = float(raw.iloc[0]) if len(raw) and not pd.isna(raw.iloc[0]) else np.nan
        experimental = reading * CALIBRATION[member] if not np.isnan(reading) else np.nan
        theoretical_raw = student_theory.get(member)
        theoretical = float(theoretical_raw) if theoretical_raw is not None and not pd.isna(theoretical_raw) else np.nan
        if not np.isnan(theoretical) and abs(theoretical) > 1e-9 and not np.isnan(experimental):
            comparison = abs(experimental - theoretical) / abs(theoretical) * 100
            comparison_label = f"{comparison:.1f}% difference"
        elif not np.isnan(theoretical) and not np.isnan(experimental):
            comparison_label = f"{abs(experimental):.2f} N residual"
        else:
            comparison_label = "Incomplete"
        rows.append(
            {
                "Member": member,
                "Dial (mm)": reading,
                "Calibration (N/mm)": CALIBRATION[member],
                "Experimental force (N)": experimental,
                "Student theoretical force (N)": theoretical,
                "Comparison": comparison_label,
                "Student classification": st.session_state.get(f"predict_{member}", "Select..."),
            }
        )
    return pd.DataFrame(rows)

def safe_load_values(mass_kg: float) -> Dict[str, float | str | bool]:
    force = theoretical_forces(mass_kg)
    max_tension_member = max(ALL_MEMBERS, key=lambda m: force[m])
    compression_members = [m for m in ALL_MEMBERS if force[m] < 0]
    max_compression_member = min(compression_members, key=lambda m: force[m]) if compression_members else "-"
    max_tension = max(force.values())
    max_compression = abs(min(force.values()))
    tension_util = max_tension / TENSION_LIMIT
    compression_util = max_compression / COMPRESSION_LIMIT
    return {
        "max_tension_member": max_tension_member,
        "max_compression_member": max_compression_member,
        "max_tension": max_tension,
        "max_compression": max_compression,
        "tension_util": tension_util,
        "compression_util": compression_util,
        "passes": tension_util <= 1.0 + 1e-9 and compression_util <= 1.0 + 1e-9,
    }


def plot_safe_load(mass_kg: float):
    values = safe_load_values(mass_kg)
    force = theoretical_forces(mass_kg)
    points = {"A": (0.0, 0.0), "B": (2.0, 0.0), "C": (4.0, 0.0), "F": (0.0, 2.0), "E": (2.0, 2.0), "D": (4.0, 2.0)}
    pairs = [
        ("A", "F", "AF"), ("F", "E", "FE"), ("E", "D", "ED"), ("D", "C", "DC"),
        ("A", "B", "AB"), ("B", "C", "BC"), ("A", "E", "AE"), ("E", "C", "EC"), ("E", "B", "EB"),
    ]
    fig, ax = plt.subplots(figsize=(9.8, 5.0))
    for start, end, name in pairs:
        f = force[name]
        if f > 0:
            utilisation = f / TENSION_LIMIT
        elif f < 0:
            utilisation = abs(f) / COMPRESSION_LIMIT
        else:
            utilisation = 0.0
        if utilisation > 1.0:
            colour = "#7F1D1D"
            width = 6.0
        else:
            colour = member_colour(f)
            width = 3.0 + 2.0 * min(utilisation, 1.0)
        ax.plot([points[start][0], points[end][0]], [points[start][1], points[end][1]], color=colour, linewidth=width, solid_capstyle="round")
        mx = (points[start][0] + points[end][0]) / 2
        my = (points[start][1] + points[end][1]) / 2
        label_edge = colour if utilisation > 0 else "#94A3B8"
        label_text = colour if utilisation > 0 else "#475569"
        ax.text(mx, my + 0.10, f"{name}\n{f:+.0f} N", ha="center", va="center", fontsize=8, color=label_text, bbox=dict(facecolor="white", edgecolor=label_edge, alpha=0.92, pad=1.4))
    joint_colours = {"A": "#7C3AED", "B": "#D97706", "C": "#0891B2", "D": "#2563EB", "E": "#16A34A", "F": "#DC2626"}
    for label, (x, y) in points.items():
        ax.scatter([x], [y], s=65, color="black", zorder=5)
        ax.text(x + 0.08, y + 0.08, label, fontweight="bold", color=joint_colours[label], bbox=dict(facecolor="white", edgecolor=joint_colours[label], boxstyle="round,pad=0.14", alpha=0.95))
    add_supports(ax)
    if mass_kg > 0:
        ax.add_patch(FancyArrowPatch((2.0, -0.04), (2.0, -0.78), arrowstyle="-|>", mutation_scale=20, color=COLORS["load"], linewidth=2.8))
        ax.text(2.12, -0.63, f"{mass_kg:.1f} kg", color="#991B1B", fontsize=11)
    status = "PASS" if values["passes"] else "LIMIT EXCEEDED"
    ax.set_title(
        f"Safe-load check: {status} | Tension utilisation {values['tension_util']:.2f} | Compression utilisation {values['compression_util']:.2f}",
        fontsize=12,
    )
    ax.text(0.0, 2.35, "Green = tension | Red = compression | Grey = zero force | Dark thick member = capacity exceeded", fontsize=9, color="#475569")
    ax.set_xlim(-0.55, 4.55)
    ax.set_ylim(-0.98, 2.58)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    return fig


def closest_member_to_theory(comparison: pd.DataFrame) -> str:
    candidates = []
    for _, row in comparison.iterrows():
        exp = row["Experimental force (N)"]
        theory = row["Theoretical force (N)"]
        if pd.isna(exp):
            continue
        if abs(theory) > 1e-9:
            metric = abs(exp - theory) / abs(theory)
        else:
            metric = abs(exp) / 10.0
        candidates.append((metric, row["Member"]))
    return min(candidates)[1] if candidates else ""



def render_apparatus_overview() -> None:
    st.markdown(
        '<div class="info"><b>Apparatus overview:</b> a simply supported plane truss is loaded vertically at joint B. Five members (AF, FE, AE, AB and EB) contain proving rings / dial gauges so their axial response can be measured directly.</div>',
        unsafe_allow_html=True,
    )
    st.pyplot(plot_apparatus(30, False, "Plane-truss apparatus and instrumented members"), width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            """
            <div class="card">
            <h4 style="margin-top:0;color:#0B4F8A;">What the apparatus contains</h4>
            <ul style="margin-bottom:0; line-height:1.55;">
              <li><b>Pin support at A</b> and <b>roller support at C</b>.</li>
              <li><b>Load hanger at joint B</b> for 10 kg, 20 kg and 30 kg test loads.</li>
              <li><b>Five instrumented members</b>: AF, FE, AE, AB and EB.</li>
              <li>Signed dial readings in <b>millimetres (mm)</b>.</li>
              <li>The dial direction is interpreted as <b>tension</b> or <b>compression</b> using the apparatus convention shown in the laboratory.</li>
            </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class="card">
            <h4 style="margin-top:0;color:#0B4F8A;">What students do</h4>
            <ol style="margin-bottom:0; line-height:1.55;">
              <li>Enter your details and choose <b>Physical laboratory</b> or <b>Online simulated practical</b>.</li>
              <li>Complete the short pre-lab and prediction sections.</li>
              <li>Record or generate readings for <b>10 kg, 20 kg and 30 kg</b>.</li>
              <li>Enter selected theoretical values for the <b>30 kg</b> case.</li>
              <li>Compare theoretical and measured behaviour.</li>
              <li>Generate the Word report template, complete the shaded writing spaces, and submit the final DOCX to <b>LearnJCU</b>.</li>
            </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )


def section_start() -> None:
    st.subheader("1. Start: student details and practical mode")
    st.markdown(
        '<div class="info"><b>Two equivalent pathways:</b> choose the physical laboratory when the apparatus is available, or the online simulated practical when an in-person session cannot run. Both pathways produce the same structured Word report template. Students complete the remaining writing spaces in Word and submit the finished DOCX through LearnJCU.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="warning"><b>Important - use your official JCU student ID:</b> Enter the eight-digit student number shown in your JCU account. Do not enter your email address, name, initials or a made-up number. A valid JCU student ID is required for the practical report and the online practical pathway.</div>',
        unsafe_allow_html=True,
    )
    left, right = st.columns([0.95, 1.05])
    with left:
        st.text_input("Student full name *", key="student_name")
        st.text_input("JCU student ID (8 digits) *", key="student_id", max_chars=8, placeholder="Example: 12345678")
        if st.session_state.student_id and not valid_jcu_student_id(st.session_state.student_id):
            st.error("Enter your official eight-digit JCU student ID using numbers only.")
        elif valid_jcu_student_id(st.session_state.student_id):
            st.success("JCU student ID format accepted.")
        st.text_input("Practical/tutorial group *", key="group", placeholder="Example: Tuesday 2 pm")
        mode = st.selectbox("Practical mode *", MODE_OPTIONS, key="practical_mode")
        if mode != st.session_state.previous_mode:
            clear_mode_dependent_work()
            reset_safety_acknowledgement()
            st.session_state.previous_mode = mode
            st.info("The apparatus data were cleared because the practical mode changed.")

        if mode == PHYSICAL_MODE:
            st.markdown('<div class="hint"><b>Physical laboratory:</b> use the real truss apparatus, observe the proving-ring / dial-gauge responses and enter the signed readings directly into the table in Section 5.</div>', unsafe_allow_html=True)
        elif mode == ONLINE_MODE:
            st.markdown('<div class="hint"><b>Online simulated practical:</b> the app generates a controlled, reproducible dataset using your official JCU student ID.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="warning">Select a practical mode before entering apparatus data.</div>', unsafe_allow_html=True)

        st.markdown("### What students submit")
        st.markdown(
            "TrussLab generates a uniform eight-page Word report template containing the student data, numerical results, tables and figures. Students complete every shaded writing space in their own words, keep the prescribed formatting and page length, and submit the finished DOCX through LearnJCU."
        )
    with right:
        render_apparatus_overview()


def section_prepare() -> None:
    st.subheader("2. Prepare: short pre-lab responses")
    st.markdown(
        '<div class="info"><b>Expected workload:</b> approximately 10 minutes. Enter your responses; they will be included in the generated report for lecturer marking.</div>',
        unsafe_allow_html=True,
    )
    st.pyplot(plot_apparatus(0, False, "Plane truss and instrumented members"), width="stretch")
    st.radio("1. The support at A is a:", ["Pin support", "Roller support", "Fixed support"], index=None, key="pre_q1")
    st.radio("2. The support at C is a:", ["Pin support", "Roller support", "Fixed support"], index=None, key="pre_q2")
    st.number_input("3. Weight produced by a 10 kg mass, in N:", min_value=0.0, max_value=200.0, value=None, step=0.1, key="pre_q3")
    st.radio("4. Predict the state of member AE:", ["Tension", "Compression", "Zero force"], index=None, key="pre_q4")
    st.radio("5. Which is a zero-force member?", ["AE", "EB", "FE"], index=None, key="pre_q5")

    complete = all(st.session_state.get(k) is not None for k in ["pre_q1", "pre_q2", "pre_q3", "pre_q4", "pre_q5"])
    st.session_state.prelab_complete = complete
    if complete:
        st.success("All five pre-lab responses have been entered and saved.")
    else:
        st.caption("Complete all five responses before generating the report. The app does not mark or reveal the answers.")

def section_predict() -> None:
    st.subheader("3. Predict the instrumented member behaviour")
    st.markdown('<div class="hint">Enter your prediction for each proving-ring member. The lecturer will mark these responses from the generated report.</div>', unsafe_allow_html=True)
    col1, col2 = st.columns([0.95, 1.05])
    with col1:
        for member in INSTRUMENTED:
            st.selectbox(f"Member {member}", ["Select...", "Tension", "Compression", "Zero force"], key=f"predict_{member}")
        complete = all(st.session_state.get(f"predict_{member}") not in (None, "Select...") for member in INSTRUMENTED)
        st.session_state.prediction_complete = complete
        if complete:
            st.success("All five predictions have been entered and saved.")
        else:
            st.caption("Select a response for every member. No answers are revealed in the student app.")
    with col2:
        st.pyplot(plot_apparatus(30, False, "Use the truss geometry to support your predictions"), width="stretch")


def section_safety() -> None:
    st.subheader("4. Lab attendance and safety acknowledgement")
    mode = st.session_state.get("practical_mode", MODE_OPTIONS[0])

    if mode == MODE_OPTIONS[0]:
        st.error("Return to Section 1 and select the practical mode first.")
        return

    if mode == ONLINE_MODE:
        st.markdown(
            '<div class="info"><b>Online pathway:</b> laboratory attendance is not required. You may continue directly to Section 5 after completing the pre-lab and prediction sections.</div>',
            unsafe_allow_html=True,
        )
        st.caption("The physical-laboratory safety gate is automatically bypassed for the online simulated practical.")
        return

    st.markdown(
        '<div class="warning"><b>Required before using the apparatus:</b> this checklist supports the local JCU laboratory/workshop induction. It does not replace the demonstrator briefing, laboratory signage, the local risk assessment or any task-specific instruction. Follow the stricter local requirement whenever it differs from this summary.</div>',
        unsafe_allow_html=True,
    )

    identity_ready = bool(
        st.session_state.get("student_name", "").strip()
        and valid_jcu_student_id(st.session_state.get("student_id", ""))
        and st.session_state.get("group", "").strip()
    )
    if not identity_ready:
        st.error("Enter your full name, official eight-digit JCU student ID and practical group in Section 1 before confirming attendance and safety.")

    left, right = st.columns(2)
    with left:
        st.markdown(
            """
            <div class="card">
            <h4 style="margin-top:0;color:#0B4F8A;">Entry, induction and PPE</h4>
            <p style="margin-bottom:0;line-height:1.55;">JCU laboratory users must receive relevant local and task-specific induction. Required clothing and PPE are determined by the local hazards, risk assessment, signage and supervisor instructions.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.checkbox(
            "I am physically present at my scheduled practical and have received the local safety briefing from the demonstrator.",
            key="safety_attendance_briefing",
        )
        st.checkbox(
            "I am wearing enclosed footwear and suitable clothing; long hair and loose items are secured, and I will use all PPE required by the entrance signage or demonstrator.",
            key="safety_ppe_clothing",
        )
        st.checkbox(
            "I will not bring or consume food or drink in the laboratory/workshop area.",
            key="safety_equipment_inspection",
        )

    with right:
        st.markdown(
            """
            <div class="card">
            <h4 style="margin-top:0;color:#0B4F8A;">Equipment, loading and emergency response</h4>
            <p style="margin-bottom:0;line-height:1.55;">Use the truss only as instructed, keep clear of moving or loaded parts, stop if anything appears unsafe and report hazards, incidents and near misses promptly.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.checkbox(
            "Before loading, I will inspect the truss, supports, load hanger and gauges and immediately report damage, looseness, binding or any other unsafe condition.",
            key="safety_loading_controls",
        )
        st.checkbox(
            "I will keep hands and body clear of the load hanger and moving parts, add/remove masses carefully, and never exceed the approved 30 kg load.",
            key="safety_supervision_housekeeping",
        )
        st.checkbox(
            "I will work only under authorised supervision, keep the area and emergency access clear, and will not modify or misuse the apparatus.",
            key="safety_emergency_reporting",
        )

    st.markdown(
        '<div class="info"><b>Emergency and reporting:</b> know the local emergency exits and the locations of first aid and emergency equipment. Stop work and tell the demonstrator immediately if there is a hazard, incident, injury or near miss. JCU RiskWare is used for formal hazard and incident reporting when required.</div>',
        unsafe_allow_html=True,
    )
    st.checkbox(
        "I have reviewed the safety information above, understand the demonstrator remains in control of the activity, and agree to stop and ask for assistance whenever I am uncertain or observe an unsafe condition.",
        key="safety_final_declaration",
    )

    checklist_complete = _safety_checklist_complete()
    if st.session_state.get("safety_complete", False) and not checklist_complete:
        st.session_state.safety_complete = False
        st.session_state.safety_acknowledged_at = ""

    if st.button("Confirm attendance and safety acknowledgement", type="primary", disabled=not identity_ready):
        if not checklist_complete:
            st.error("Review and tick every safety acknowledgement before continuing.")
        else:
            st.session_state.safety_complete = True
            st.session_state.safety_acknowledged_at = datetime.now().strftime("%d %B %Y, %H:%M")
            st.session_state.safety_acknowledged_student_id = normalise_jcu_student_id(st.session_state.student_id)
            st.session_state.safety_acknowledged_student_name = st.session_state.student_name.strip()
            st.session_state.safety_acknowledged_group = st.session_state.group.strip()
            st.success("Attendance and safety acknowledgement recorded. You may continue to Section 5.")

    if safety_requirement_complete():
        st.success(f"Safety gate complete for {st.session_state.student_name.strip()} at {st.session_state.safety_acknowledged_at}.")
    elif checklist_complete:
        st.warning("All items are ticked, but you must click Confirm attendance and safety acknowledgement before continuing.")

    with st.expander("JCU safety basis used for this checklist"):
        st.markdown(
            """
            This practical checklist is based on JCU requirements for local/site-specific induction, authorised and inducted laboratory access, PPE and clothing determined by local risks and signage, safe procedures for plant/equipment, and reporting hazards or incidents through the supervisor and RiskWare when required.

            - [JCU WHS-PRO-013 Laboratory Safety Procedure](https://www.jcu.edu.au/policy/university-management/whs-management/whs-pro-013-laboratory-safety-procedure)
            - [JCU WHS-PRO-004 Training and Competency Procedure](https://www.jcu.edu.au/policy/university-management/whs-management/whs-pro-004-whs-training-and-competency-procedure)
            - [JCU RiskWare information](https://www.jcu.edu.au/work-health-and-safety/report-and-manage-an-accident-incident-or-hazard/what-is-riskware)
            """
        )

def set_lab_value(member: str, column: str, value: float) -> None:
    df = st.session_state.lab_data.copy()
    df.loc[df["Member"] == member, column] = value
    st.session_state.lab_data = df



def section_data() -> None:
    st.subheader("5. Apparatus and data collection")
    mode = st.session_state.practical_mode
    if mode == MODE_OPTIONS[0]:
        st.error("Return to Section 1 and select either the physical or online practical mode.")
        return
    if not require_safety_before_main_practical():
        return

    if mode == PHYSICAL_MODE:
        st.markdown('<div class="warning"><b>Safety:</b> inspect the apparatus, keep hands clear of the load hanger and do not exceed the approved 30 kg load.</div>', unsafe_allow_html=True)
        top_left, top_right = st.columns([0.58, 0.42])
        with top_left:
            st.markdown(
                """
                <div class="card">
                <h4 style="margin-top:0;color:#0B4F8A;">Physical laboratory procedure</h4>
                <ol style="margin-bottom:0; line-height:1.58;">
                  <li>Check that the truss is not touching or binding against the support frame.</li>
                  <li>Identify which dial direction represents <b>tension</b> and which represents <b>compression</b>.</li>
                  <li>With no applied load, carefully zero the five gauges.</li>
                  <li>Apply <b>10 kg</b>, then <b>20 kg</b>, then <b>30 kg</b> at joint B.</li>
                  <li>For each load, enter the signed dial reading for AF, FE, AE, AB and EB in the table below.</li>
                  <li>Remove the load and record whether the gauges return close to zero.</li>
                  <li>Click <b>Check data completeness and quality</b> before moving on.</li>
                </ol>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with top_right:
            st.markdown(
                """
                <div class="card">
                <h4 style="margin-top:0;color:#0B4F8A;">What to enter</h4>
                <ul style="margin-bottom:0; line-height:1.58;">
                  <li>Use units of <b>millimetres (mm)</b>.</li>
                  <li>Enter the <b>signed</b> reading shown by the apparatus.</li>
                  <li>The table saves entries automatically in the current session.</li>
                  <li>If a reading looks inconsistent, recheck the apparatus before re-entering it.</li>
                  <li>Only proceed when all <b>15 readings</b> and the return-to-zero response are complete.</li>
                </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.pyplot(plot_apparatus(30, False, "Apparatus layout and instrumented members"), width="stretch")
        edited = st.data_editor(
            st.session_state.lab_data,
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            disabled=["Member"],
            column_config={
                "Member": st.column_config.TextColumn("Member", width="small"),
                "10 kg (mm)": st.column_config.NumberColumn("10 kg (mm)", format="%.3f", step=0.001),
                "20 kg (mm)": st.column_config.NumberColumn("20 kg (mm)", format="%.3f", step=0.001),
                "30 kg (mm)": st.column_config.NumberColumn("30 kg (mm)", format="%.3f", step=0.001),
            },
            key=PHYSICAL_EDITOR_KEY,
        )
        st.session_state.lab_data = edited.copy()
        st.caption("Your table entries are saved in the current TrussLab session and will be inserted into the generated Word report template.")
        st.radio("After unloading, did the gauges return close to zero? *", ["Not checked", "Yes", "Approximately", "No"], horizontal=True, key="zero_return")

    else:
        id_is_valid = valid_jcu_student_id(st.session_state.student_id)
        if not id_is_valid:
            st.error("Return to Section 1 and enter your official eight-digit JCU student ID before recording online data.")
        st.markdown(
            '<div class="info"><b>Online-only pathway:</b> select each load and click <i>Record this load</i>. The simulated readings contain small, realistic imperfections and are reproducible for the same student ID.</div>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns([0.35, 0.65])
        with c1:
            mass = st.select_slider("Applied mass", options=[0, 10, 20, 30], value=10, format_func=lambda x: f"{x} kg", key="online_mass")
            st.write(f"Applied force: **{mass * G:.1f} N**")
            if mass in (10, 20, 30):
                if st.button(f"Record {mass} kg readings", type="primary", disabled=not id_is_valid):
                    readings = simulated_readings(mass, st.session_state.student_id, realistic=True)
                    column = f"{mass} kg (mm)"
                    for member, value in readings.items():
                        set_lab_value(member, column, value)
                    if mass not in st.session_state.captured_loads:
                        st.session_state.captured_loads.append(mass)
                    st.session_state.simulation_student_id = normalise_jcu_student_id(st.session_state.student_id)
                    st.success(f"The {mass} kg readings were recorded.")
            else:
                st.caption("Use the 0 kg setting to inspect the return-to-zero behaviour after recording the loaded cases.")
                if st.button("Confirm simulated return to zero", disabled=not id_is_valid):
                    st.session_state.zero_return = "Approximately"
                    st.success("Return-to-zero observation recorded as approximately zero.")
        with c2:
            if id_is_valid:
                readings = simulated_readings(mass, st.session_state.student_id, realistic=True)
                st.pyplot(plot_dials(readings), width="stretch")
                st.pyplot(plot_apparatus(mass, True, "Online simulated apparatus"), width="stretch")
            else:
                st.info("Enter a valid JCU student ID in Section 1 to activate the online apparatus.")
                st.pyplot(plot_apparatus(0, False, "Online simulated apparatus"), width="stretch")

        captured = sorted(st.session_state.captured_loads)
        st.write(f"Recorded loads: **{', '.join(str(x) + ' kg' for x in captured) if captured else 'none'}**")
        st.dataframe(st.session_state.lab_data.style.format({"10 kg (mm)": "{:+.3f}", "20 kg (mm)": "{:+.3f}", "30 kg (mm)": "{:+.3f}"}), hide_index=True, width="stretch")

    c1, c2 = st.columns([0.35, 0.65])
    with c1:
        check_clicked = st.button("Check data completeness and quality", type="primary")
    with c2:
        st.button("Clear all apparatus data", on_click=request_clear_mode_dependent_work)

    if st.session_state.get("apparatus_clear_notice", False):
        st.success("All apparatus readings and the return-to-zero response were cleared.")
        st.session_state.apparatus_clear_notice = False

    readings_complete = not st.session_state.lab_data[["10 kg (mm)", "20 kg (mm)", "30 kg (mm)"]].isna().any().any()
    zero_checked = st.session_state.zero_return != "Not checked"
    correct_id = mode != ONLINE_MODE or (valid_jcu_student_id(st.session_state.student_id) and st.session_state.simulation_student_id == normalise_jcu_student_id(st.session_state.student_id))
    st.session_state.lab_complete = readings_complete and zero_checked and correct_id

    if check_clicked:
        for kind, message in data_quality_messages(st.session_state.lab_data):
            class_name = "good" if kind == "good" else "warning"
            st.markdown(f'<div class="{class_name}">{message}</div>', unsafe_allow_html=True)
        if not readings_complete:
            st.error("All 15 dial readings must be recorded.")
        if not zero_checked:
            st.error("Record the return-to-zero observation.")
        if not correct_id:
            st.error("The online dataset was recorded for a different student ID. Clear and record the data again.")
        if st.session_state.lab_complete:
            st.success("Apparatus data section complete.")

def numeric_result(value, expected: float, tolerance: float) -> bool:
    return value is not None and abs(float(value) - expected) <= tolerance


def _text_entered(key: str) -> bool:
    value = st.session_state.get(key, "")
    return value is not None and bool(str(value).strip())


def _prelab_entries_complete() -> bool:
    return (
        st.session_state.get("pre_q1") is not None
        and st.session_state.get("pre_q2") is not None
        and st.session_state.get("pre_q3") is not None
        and st.session_state.get("pre_q4") is not None
        and st.session_state.get("pre_q5") is not None
    )


def _prediction_entries_complete() -> bool:
    return all(
        st.session_state.get(f"predict_{member}") not in (None, "Select...")
        for member in INSTRUMENTED
    )


def _lab_entries_complete() -> bool:
    readings_complete = not st.session_state.lab_data[
        ["10 kg (mm)", "20 kg (mm)", "30 kg (mm)"]
    ].isna().any().any()
    zero_checked = st.session_state.zero_return != "Not checked"
    dataset_matches_student = (
        st.session_state.practical_mode != ONLINE_MODE
        or st.session_state.simulation_student_id == st.session_state.student_id.strip()
    )
    return readings_complete and zero_checked and dataset_matches_student


def _calculation_entries_complete() -> bool:
    required = ["calc_w_input", "calc_ay_input", "calc_ae_input", "calc_ab_input", "calc_eb_input"]
    return all(st.session_state.get(key) is not None for key in required)


def _experimental_entry_complete() -> bool:
    return st.session_state.get("experimental_calc_input") is not None


def _part_b_entries_complete() -> bool:
    return (
        st.session_state.get("safe_mass_input") is not None
        and st.session_state.get("critical_member_input") not in (None, "Select...")
        and st.session_state.get("critical_type_input") is not None
    )


def section_calculate() -> None:
    if not require_safety_before_main_practical():
        return
    st.subheader("6. Selected theoretical calculations")
    st.markdown('<div class="info">Enter the numerical results for the 30 kg case. The generated Word report provides a fixed, professionally formatted space for you to show the equations and complete working.</div>', unsafe_allow_html=True)
    st.pyplot(plot_apparatus(30, False, "Calculation case: 30 kg at joint B"), width="stretch")
    st.markdown("Use **positive for tension** and **negative for compression**.")
    c1, c2 = st.columns(2)
    with c1:
        st.number_input("Applied load W (N) *", value=None, step=0.1, key="calc_w_input")
        st.number_input("Vertical reaction Ay (N) *", value=None, step=0.1, key="calc_ay_input")
        st.number_input("Member force F_EB (N) *", value=None, step=0.1, key="calc_eb_input")
    with c2:
        st.number_input("Member force F_AE (N) *", value=None, step=0.1, key="calc_ae_input")
        st.number_input("Member force F_AB (N) *", value=None, step=0.1, key="calc_ab_input")
    complete = _calculation_entries_complete()
    st.session_state.calculation_complete = complete
    if complete:
        st.success("All five theoretical values have been entered and saved.")
    else:
        st.caption("Enter all five numerical values. The app does not check or reveal the solution.")


def section_compare() -> None:
    if not require_safety_before_main_practical():
        return
    st.subheader("7. Compare results")
    if not st.session_state.lab_complete:
        st.warning("Complete and save the apparatus data in Section 5 before finalising this section.")
    if USING_DEMO_CALIBRATION and st.session_state.practical_mode == PHYSICAL_MODE:
        st.markdown('<div class="warning">Demonstration calibration factors are active. The lecturer should replace calibration.csv with apparatus-specific factors before assessing physical measurements.</div>', unsafe_allow_html=True)

    comparison = compare_table()
    st.dataframe(
        comparison.style.format(
            {
                "Dial (mm)": lambda x: "" if pd.isna(x) else f"{x:+.3f}",
                "Calibration (N/mm)": "{:.1f}",
                "Experimental force (N)": lambda x: "" if pd.isna(x) else f"{x:+.2f}",
                "Student theoretical force (N)": lambda x: "" if pd.isna(x) else f"{x:+.2f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption("The comparison uses the theoretical forces entered in Section 6; the app does not substitute the lecturer solution.")
    if not st.session_state.lab_data[["10 kg (mm)", "20 kg (mm)", "30 kg (mm)"]].isna().all().all():
        st.pyplot(plot_lab_readings(st.session_state.lab_data), width="stretch")

    st.markdown("### One worked experimental-force calculation")
    comparison_ae = comparison.loc[comparison["Member"] == "AE"]
    ae_reading = comparison_ae.iloc[0]["Dial (mm)"] if not comparison_ae.empty else np.nan
    if pd.isna(ae_reading):
        st.info("Record the 30 kg AE dial reading before completing this calculation.")
    else:
        st.write(f"For member AE, use D = {ae_reading:+.3f} mm and f = {CALIBRATION['AE']:.1f} N/mm.")
        st.number_input("Your calculated experimental force F_AE = Df (N) *", value=None, step=0.1, key="experimental_calc_input")

    st.session_state.experimental_calc_complete = _experimental_entry_complete()
    if st.session_state.experimental_calc_complete:
        st.success("The worked experimental-force value has been entered and saved.")

    st.markdown("### Analysis and discussion")
    st.markdown(
        '<div class="info">The generated Word report includes four guided discussion questions and fixed response boxes. Complete those sections in your own words after downloading the report. This keeps the report style and length consistent while leaving the analysis to you.</div>',
        unsafe_allow_html=True,
    )


def section_part_b() -> None:
    if not require_safety_before_main_practical():
        return
    st.subheader("8. Engineering challenge: safe-load assessment")
    st.markdown(
        f'<div class="info"><b>Design question:</b> Why is the apparatus practical limited to approximately {APPROVED_MASS:.0f} kg? Use the graph and allowable values to determine the maximum safe mass. The allowable tension is {TENSION_LIMIT:.0f} N and allowable compression magnitude is {COMPRESSION_LIMIT:.0f} N.</div>',
        unsafe_allow_html=True,
    )
    mass = st.slider("Test applied mass (kg)", min_value=0.0, max_value=40.0, value=30.0, step=0.1, key="safe_test_mass")
    values = safe_load_values(mass)
    c1, c2, c3 = st.columns(3)
    c1.metric("Maximum tension", f"{values['max_tension']:.1f} N", f"Limit {TENSION_LIMIT:.0f} N")
    c2.metric("Maximum compression", f"{values['max_compression']:.1f} N", f"Limit {COMPRESSION_LIMIT:.0f} N")
    c3.metric("Status", "PASS" if values["passes"] else "LIMIT EXCEEDED")
    st.pyplot(plot_safe_load(mass), width="stretch")

    st.number_input("Maximum safe mass, to the nearest 0.1 kg *", value=None, step=0.1, key="safe_mass_input")
    st.selectbox("Controlling member *", ["Select...", "EB", "AE/EC", "AB/BC", "AF/FE"], key="critical_member_input")
    st.radio("Controlling force type *", ["Tension", "Compression"], index=None, key="critical_type_input")

    st.session_state.safe_mass_answer = st.session_state.get("safe_mass_input")
    st.session_state.critical_member_answer = st.session_state.get("critical_member_input")
    st.session_state.critical_type_answer = st.session_state.get("critical_type_input")
    complete = _part_b_entries_complete()
    st.session_state.part_b_complete = complete
    if complete:
        st.success("The engineering-challenge responses have been entered and saved.")
    else:
        st.caption("Complete the three engineering-challenge responses. The derivation and engineering interpretation are completed in the generated Word report.")


def report_validation_issues() -> List[str]:
    issues: List[str] = []
    if not st.session_state.student_name.strip():
        issues.append("Enter the student full name in Section 1.")
    if not valid_jcu_student_id(st.session_state.student_id):
        issues.append("Enter your official eight-digit JCU student ID in Section 1.")
    if not st.session_state.group.strip():
        issues.append("Enter the practical/tutorial group in Section 1.")
    if st.session_state.practical_mode not in (PHYSICAL_MODE, ONLINE_MODE):
        issues.append("Select the practical mode in Section 1.")
    if not _prelab_entries_complete():
        issues.append("Enter all five pre-lab responses in Section 2.")
    if not _prediction_entries_complete():
        issues.append("Enter all five member predictions in Section 3.")
    if not safety_requirement_complete():
        issues.append("Complete the lab attendance and safety acknowledgement in Section 4.")

    if not _lab_entries_complete():
        issues.append("Complete and save all apparatus readings and the return-to-zero observation in Section 5.")
    if st.session_state.practical_mode == ONLINE_MODE and st.session_state.simulation_student_id != normalise_jcu_student_id(st.session_state.student_id):
        issues.append("The online data do not match the current JCU student ID. Clear and record the simulated readings again.")

    if not _calculation_entries_complete():
        issues.append("Enter all five theoretical values in Section 6.")
    if not _experimental_entry_complete():
        issues.append("Enter the worked experimental-force value in Section 7.")
    if not _part_b_entries_complete():
        issues.append("Complete the three engineering-challenge responses in Section 8.")
    if not st.session_state.get("review_declaration", False):
        issues.append("Tick the student review declaration on this page.")
    return issues

def student_predictions_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [{"Member": member, "Student prediction": st.session_state.get(f"predict_{member}", "Select...")} for member in INSTRUMENTED]
    )

def prelab_responses_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["Support at A", st.session_state.get("pre_q1")],
            ["Support at C", st.session_state.get("pre_q2")],
            ["Weight produced by 10 kg (N)", st.session_state.get("pre_q3")],
            ["Predicted state of AE", st.session_state.get("pre_q4")],
            ["Selected zero-force member", st.session_state.get("pre_q5")],
        ],
        columns=["Question", "Student response"],
    )


def safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    return cleaned.strip("_") or "Student"


def create_report_bytes() -> Tuple[bytes, str]:
    comparison = compare_table()
    mode_note = (
        f"Physical laboratory mode was used. Attendance and safety were acknowledged on {st.session_state.get('safety_acknowledged_at', 'not recorded')}. Dial readings were entered from the apparatus."
        if st.session_state.practical_mode == PHYSICAL_MODE
        else "Online simulated practical mode was used because an in-person apparatus session was unavailable. The dataset was generated reproducibly from the student ID."
    )
    data = {
        "student_name": st.session_state.student_name.strip(),
        "student_id": normalise_jcu_student_id(st.session_state.student_id),
        "group": st.session_state.group.strip(),
        "mode": st.session_state.practical_mode,
        "mode_note": mode_note,
        "generated_at": datetime.now().strftime("%d %B %Y, %H:%M"),
        "prelab_responses": prelab_responses_dataframe(),
        "predictions": student_predictions_dataframe(),
        "lab_data": st.session_state.lab_data.copy(),
        "zero_return": st.session_state.zero_return,
        "calc_w": st.session_state.get("calc_w_input"),
        "calc_ay": st.session_state.get("calc_ay_input"),
        "calc_ae": st.session_state.get("calc_ae_input"),
        "calc_ab": st.session_state.get("calc_ab_input"),
        "calc_eb": st.session_state.get("calc_eb_input"),
        "comparison": comparison,
        "experimental_calc": st.session_state.get("experimental_calc_input"),
        "safe_mass_answer": st.session_state.get("safe_mass_input"),
        "critical_member_answer": st.session_state.get("critical_member_input"),
        "critical_type_answer": st.session_state.get("critical_type_input"),
        "designer_name": DESIGNER_NAME,
        "jcu_logo": (ASSET_DIR / "jcu_logo.png").read_bytes() if (ASSET_DIR / "jcu_logo.png").exists() else None,
        "truss_image": fig_to_png_bytes(plot_apparatus(30, False, "Plane truss used for the 30 kg calculation case")),
        "dial_graph": fig_to_png_bytes(plot_lab_readings(st.session_state.lab_data)),
        "safe_load_image": fig_to_png_bytes(plot_safe_load(float(st.session_state.safe_test_mass))),
    }
    report = build_practical_report(data)
    filename = f"{safe_filename(str(CONFIG['report_prefix']))}_{safe_filename(normalise_jcu_student_id(st.session_state.student_id))}.docx"
    return report, filename


def section_report() -> None:
    if not require_safety_before_main_practical():
        return
    st.session_state.prelab_complete = _prelab_entries_complete()
    st.session_state.prediction_complete = _prediction_entries_complete()
    st.session_state.lab_complete = _lab_entries_complete()
    st.session_state.calculation_complete = _calculation_entries_complete()
    st.session_state.experimental_calc_complete = _experimental_entry_complete()
    st.session_state.part_b_complete = _part_b_entries_complete()

    st.subheader("9. Validate, generate and download the Word report")
    st.markdown(
        '<div class="info">The app inserts the student details, numerical results, tables and figures into a uniform Word report template. The student then completes the introduction, method, calculation working, analysis, discussion and conclusion in the fixed spaces provided.</div>',
        unsafe_allow_html=True,
    )
    checks = {
        "Student details and mode": bool(st.session_state.student_name.strip() and valid_jcu_student_id(st.session_state.student_id) and st.session_state.group.strip() and st.session_state.practical_mode in (PHYSICAL_MODE, ONLINE_MODE)),
        "Pre-lab responses": _prelab_entries_complete(),
        "Member predictions entered": _prediction_entries_complete(),
        "Lab attendance and safety": safety_requirement_complete(),
        "Apparatus data": _lab_entries_complete(),
        "Theoretical values entered": _calculation_entries_complete(),
        "Experimental-force value entered": _experimental_entry_complete(),
        "Engineering challenge responses": _part_b_entries_complete(),
    }
    completed = sum(checks.values())
    st.progress(completed / len(checks), text=f"{completed} of {len(checks)} practical components complete")
    for label, done in checks.items():
        st.write(f"{'✅' if done else '⬜'} {label}")

    st.checkbox("I have reviewed my entries and want the app to create my submission report. *", key="review_declaration")

    if st.button("Check completeness and generate Word report", type="primary", width="stretch"):
        issues = report_validation_issues()
        if issues:
            st.session_state.report_bytes = None
            st.error("The report cannot be generated yet. Complete the following items:")
            for issue in issues:
                st.write(f"• {issue}")
        else:
            try:
                report, filename = create_report_bytes()
                st.session_state.report_bytes = report
                st.session_state.report_filename = filename
                st.success("The Word report template was generated successfully. Open it, complete all shaded writing spaces in your own words, review the full report and then submit it to the lecturer.")
            except Exception as exc:
                st.session_state.report_bytes = None
                st.error(f"The report could not be generated: {exc}")

    if st.session_state.report_bytes:
        st.download_button(
            "Download practical report template (.docx)",
            data=st.session_state.report_bytes,
            file_name=st.session_state.report_filename,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            width="stretch",
        )
        st.caption("Complete the shaded response boxes in Word without changing the page layout, margins or section headings.")

    st.markdown('<div class="small-note"><b>Privacy:</b> the app does not upload student answers to a server database. Entries remain in the active Streamlit session unless students download the generated report.</div>', unsafe_allow_html=True)


render_header()


def render_sidebar() -> str:
    st.sidebar.markdown(
        """
        <div class="sidebar-brand">
          <div class="course">EG1011 · Statics and Dynamics</div>
          <div class="title">TrussLab</div>
          <div class="subtitle">Plane-truss practical, guided analysis and report preparation</div>
          <div class="rule"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sections = [
        "1. Student details",
        "2. Pre-lab preparation",
        "3. Member predictions",
        "4. Safety induction",
        "5. Data collection",
        "6. Truss calculations",
        "7. Results analysis",
        "8. Engineering challenge",
        "9. Report submission",
    ]

    st.sidebar.markdown('<div class="sidebar-section-label">Practical workflow</div>', unsafe_allow_html=True)
    selected_page = st.sidebar.radio(
        "Choose a section",
        sections,
        label_visibility="collapsed",
    )

    start_complete = (
        bool(st.session_state.student_name.strip())
        and valid_jcu_student_id(st.session_state.student_id)
        and bool(st.session_state.group.strip())
        and st.session_state.practical_mode in (PHYSICAL_MODE, ONLINE_MODE)
    )
    workflow_checks = [
        start_complete,
        _prelab_entries_complete(),
        _prediction_entries_complete(),
        safety_requirement_complete(),
        _lab_entries_complete(),
        _calculation_entries_complete(),
        _experimental_entry_complete(),
        _part_b_entries_complete(),
        bool(st.session_state.report_bytes),
    ]
    completed = sum(bool(value) for value in workflow_checks)
    progress = completed / len(workflow_checks)

    st.sidebar.markdown('<div class="sidebar-section-label">Practical status</div>', unsafe_allow_html=True)
    st.sidebar.progress(progress)
    st.sidebar.markdown(
        f'<div class="sidebar-card"><div class="label">Overall progress</div>'
        f'<div class="value">{completed} of {len(workflow_checks)} stages complete</div>'
        f'<div class="meta">Your entries are retained while you move between sections.</div>'
        f'<div class="sidebar-badge">{round(progress * 100)}% COMPLETE</div></div>',
        unsafe_allow_html=True,
    )

    mode = st.session_state.practical_mode
    mode_value = "Choose in Section 1" if mode == MODE_OPTIONS[0] else mode
    st.sidebar.markdown(
        f'<div class="sidebar-card"><div class="label">Selected pathway</div>'
        f'<div class="value">{mode_value}</div>'
        f'<div class="meta">Physical and online pathways use the same report structure.</div></div>',
        unsafe_allow_html=True,
    )

    if mode == PHYSICAL_MODE:
        if safety_requirement_complete():
            st.sidebar.markdown(
                '<div class="sidebar-status-good"><b>Safety induction complete</b><br>Data collection and analysis sections are available.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.sidebar.markdown(
                '<div class="sidebar-status-warn"><b>Safety induction required</b><br>Complete Section 4 before accessing laboratory data collection.</div>',
                unsafe_allow_html=True,
            )
    elif mode == ONLINE_MODE:
        st.sidebar.markdown(
            '<div class="sidebar-status-good"><b>Online pathway selected</b><br>Use your official JCU student ID to generate reproducible readings.</div>',
            unsafe_allow_html=True,
        )

    st.sidebar.markdown(
        f'<div class="sidebar-footer"><b>Submission:</b> generate the Word template, complete the shaded writing spaces, and submit the final DOCX through LearnJCU.'
        f'<br><br>TrussLab v{APP_VERSION}</div>',
        unsafe_allow_html=True,
    )
    return selected_page


page = render_sidebar()

if page == "1. Student details":
    section_start()
elif page == "2. Pre-lab preparation":
    section_prepare()
elif page == "3. Member predictions":
    section_predict()
elif page == "4. Safety induction":
    section_safety()
elif page == "5. Data collection":
    section_data()
elif page == "6. Truss calculations":
    section_calculate()
elif page == "7. Results analysis":
    section_compare()
elif page == "8. Engineering challenge":
    section_part_b()
else:
    section_report()
