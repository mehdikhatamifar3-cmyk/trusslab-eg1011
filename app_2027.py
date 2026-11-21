"""Guided 2027 practical and password-protected staff checking workspace."""
from __future__ import annotations

import copy
import base64
from html import escape
import hashlib
import hmac
import inspect
import io
import json
import os
import re
import time
import tempfile
import textwrap
from pathlib import Path

import pandas as pd
import streamlit as st

if __package__:
    from . import trusslab_2027_core as core
    from . import trusslab_2027_reports as reports
else:
    import trusslab_2027_core as core
    import trusslab_2027_reports as reports

# This metadata must not prevent startup when this module is imported directly
# by an older entry point. The normal entry point loads a matching private set.
REPORT_LAYOUT_VERSION=getattr(reports,"REPORT_LAYOUT_VERSION","2027.4")
build_bundle=reports.build_bundle
diagram_png=reports.diagram_png
read_bundle=reports.read_bundle
readings_plot_png=reports.readings_plot_png

SECTIONS = (
    "1 Student details", "2 Pre-lab and predictions", "3 Safety",
    "4 Data collection", "5 Theoretical calculations", "6 Experimental calculations",
    "7 Results and explanations", "8 Capacity challenge", "9 Review and submission",
)
CSS = """
<style>

      :root { --jcu-blue:#A62C63; --jcu-blue-dark:#7D1F49; --ink:#29202A; --muted:#70616C; --line:#ECDCE3; }
      html { scroll-behavior:smooth; }
      .stApp { background:#ffffff; color:var(--ink); }
      .block-container { max-width:1420px; padding-top:0.75rem; padding-bottom:2.5rem; }
      [data-testid="stSidebar"] {
        background:linear-gradient(180deg,#FCF8FA 0%,#F9F1F5 60%,#F6ECF0 100%);
        border-right:1px solid #E9D7DF;
        min-width:278px;
        max-width:298px;
      }
      [data-testid="stSidebar"] > div:first-child { padding-top:0.7rem; }
      [data-testid="stSidebar"] [data-testid="stRadio"] > div { gap:0.28rem; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label {
        background:rgba(255,255,255,0.88);
        border:1px solid #ECDBE3;
        border-radius:10px;
        padding:0.50rem 0.62rem;
        margin:0.06rem 0;
        transition:all 0.16s ease;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        border-color:#D1A8BA;
        background:#ffffff;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background:#FCEDF4;
        border-color:#CA88A6;
        box-shadow:inset 3px 0 0 var(--jcu-blue), 0 1px 3px rgba(42,15,27,0.04);
      }
      [data-testid="stSidebar"] [data-testid="stProgress"] > div > div { background-color:#A62C63; }
      .sidebar-brand {
        background:transparent;
        color:var(--ink);
        padding:5px 4px 13px 13px;
        margin:1px 0 12px;
        border-left:3px solid var(--jcu-blue);
      }
      .sidebar-brand::before { display:none; }
      .sidebar-brand .course {
        color:#866172;
        font-size:9.5px;
        font-weight:800;
        letter-spacing:0.105em;
        text-transform:uppercase;
      }
      .sidebar-brand .title {
        color:#541A34;
        font-size:21px;
        font-weight:800;
        line-height:1.08;
        margin-top:4px;
      }
      .sidebar-brand .subtitle {
        color:#8A6877;
        font-size:11px;
        line-height:1.42;
        margin-top:6px;
        max-width:230px;
      }
      .sidebar-brand .rule { display:none; }
      .sidebar-section-label {
        color:#745261; font-size:10px; font-weight:800; letter-spacing:0.12em;
        text-transform:uppercase; margin:14px 2px 7px;
      }
      .sidebar-card {
        background:rgba(255,255,255,0.78); border:1px solid #ECDCE3; border-radius:10px;
        padding:10px 11px; margin:7px 0;
      }
      .sidebar-card .label { color:#70616C; font-size:10px; font-weight:800; letter-spacing:0.09em; text-transform:uppercase; }
      .sidebar-card .value { color:#29202A; font-size:13px; font-weight:700; margin-top:3px; }
      .sidebar-card .meta { color:#70616C; font-size:11px; line-height:1.42; margin-top:5px; }
      .sidebar-badge {
        display:inline-block; padding:3px 8px; border-radius:999px;
        background:#FFE8F2; color:#A62C63; border:1px solid #F5C7DC;
        font-size:10px; font-weight:800; letter-spacing:0.04em; margin-top:7px;
      }
      .sidebar-status-good { color:#166534; background:#ecfdf3; border:1px solid #bbf7d0; border-radius:9px; padding:8px 10px; font-size:11px; margin:7px 0; }
      .sidebar-status-warn { color:#854d0e; background:#fffbeb; border:1px solid #fde68a; border-radius:9px; padding:8px 10px; font-size:11px; margin:7px 0; }
      .sidebar-footer { color:#967A87; font-size:10.5px; line-height:1.45; margin-top:13px; padding:10px 3px 2px; border-top:1px solid #E8D7DF; }
      header[data-testid="stHeader"] { background:transparent; }
      #MainMenu, footer { visibility:hidden; }
      .app-header {
        display:grid;
        grid-template-columns:235px minmax(0,1fr) 235px;
        gap:28px;
        align-items:center;
        padding:8px 6px 16px;
      }
      .header-logo {
        display:flex;
        align-items:center;
        min-height:82px;
        padding:2px 26px 2px 2px;
        border-right:1px solid #EEE0E6;
      }
      .header-logo img { display:block; width:100%; max-width:220px; height:auto; }
      .app-header-title .kicker {
        color:var(--jcu-blue);
        font-size:10px;
        font-weight:800;
        letter-spacing:0.13em;
        text-transform:uppercase;
        margin-bottom:5px;
      }
      .app-header-title h1 { margin:0; font-size:34px; line-height:1.03; color:#29202A; letter-spacing:-0.025em; }
      .app-header-title p { margin:8px 0 0; color:#735361; line-height:1.48; font-size:14px; max-width:720px; }
      .app-header-meta {
        border-left:1px solid #EEE0E6;
        padding-left:24px;
        text-align:left;
      }
      .app-header-meta .label { color:#967182; font-size:9.5px; font-weight:800; letter-spacing:0.12em; text-transform:uppercase; }
      .app-header-meta .title { color:#472434; font-size:13px; font-weight:750; line-height:1.35; margin-top:4px; }
      .app-header-meta .designer { color:#967A87; font-size:10.5px; line-height:1.45; margin-top:10px; }
      .app-divider { height:1px; background:linear-gradient(90deg,#EBD8E1 0%,#F6EEF2 100%); margin:1px 0 19px; }
      .info { background:#FFE8F2; border:1px solid #F5C7DC; border-radius:10px; padding:13px 15px; color:#6D2344; margin:8px 0 16px; }
      .hint { background:#ecfdf3; border:1px solid #bbf7d0; border-radius:10px; padding:11px 13px; color:#166534; margin:8px 0 14px; }
      .warning { background:#fff8e8; border:1px solid #f3d69b; border-radius:10px; padding:11px 13px; color:#7c4a03; margin:8px 0 14px; }
      .good { background:#ecfdf3; border:1px solid #bbf7d0; color:#166534; border-radius:9px; padding:10px 12px; margin:6px 0; }
      .bad { background:#fff1f2; border:1px solid #fecdd3; color:#9f1239; border-radius:9px; padding:10px 12px; margin:6px 0; }
      .card { border:1px solid #EADFE4; border-radius:10px; padding:14px 16px; margin-bottom:14px; background:#fff; }
      .small-note { color:#70616C; font-size:13px; line-height:1.45; }
      .page-heading {
        padding:2px 0 12px; margin:0 0 6px; border-bottom:1px solid #F2E6EB;
      }
      .page-heading .section-label {
        color:#A62C63; font-size:10px; font-weight:800; letter-spacing:0.13em;
        text-transform:uppercase; margin-bottom:4px;
      }
      .page-heading .section-title {
        color:#29202A; font-size:25px; font-weight:800; line-height:1.16; letter-spacing:-0.02em;
      }
      .page-heading .section-summary {
        color:#836070; font-size:13px; line-height:1.48; margin-top:5px; max-width:920px;
      }
      div[data-testid="stPopover"] > button {
        border:1px solid #E4C9D5 !important; border-radius:999px !important;
        background:#FDF7FA !important; color:#5F233E !important; font-weight:750 !important;
        min-height:2.25rem !important; padding:0.35rem 0.8rem !important;
        box-shadow:none !important;
      }
      div[data-testid="stPopover"] > button:hover {
        background:#FCEDF4 !important; border-color:#CC8EAA !important; color:#A62C63 !important;
      }
      .help-completion {
        background:#FDF2F7; border:1px solid #F3D4E2; border-left:4px solid #A62C63;
        border-radius:9px; padding:9px 11px; color:#6B344D; font-size:12px; line-height:1.45; margin-top:10px;
      }
      div[data-testid="stMetric"] { background:#ffffff; border:1px solid #F0E2E8; padding:10px 12px; border-radius:10px; }
      .start-hero {
        display:flex; align-items:flex-start; justify-content:space-between; gap:24px;
        padding:18px 20px; margin:0 0 18px; border:1px solid #ECD7E0; border-radius:14px;
        background:linear-gradient(135deg,#FEF8FB 0%,#ffffff 58%,#FCF4F8 100%);
        box-shadow:0 3px 12px rgba(42,15,27,0.035);
      }
      .start-hero .eyebrow { color:#A62C63; font-size:10px; font-weight:800; letter-spacing:0.13em; text-transform:uppercase; margin-bottom:5px; }
      .start-hero .headline { color:#29202A; font-size:22px; line-height:1.15; font-weight:800; }
      .start-hero .description { color:#735361; font-size:13px; line-height:1.5; max-width:720px; margin-top:7px; }
      .start-steps { display:flex; flex-wrap:wrap; gap:7px; justify-content:flex-end; min-width:330px; }
      .start-step-chip {
        display:flex; align-items:center; gap:7px; padding:7px 10px; border-radius:999px;
        background:#ffffff; border:1px solid #EDD8E1; color:#664252; font-size:11px; font-weight:700; white-space:nowrap;
      }
      .start-step-chip .num {
        display:inline-flex; align-items:center; justify-content:center; width:19px; height:19px; border-radius:50%;
        background:#FFE8F2; color:#A62C63; font-size:10px; font-weight:800;
      }
      .panel-heading { margin:0 0 3px; color:#29202A; font-size:18px; font-weight:800; }
      .panel-subheading { margin:0 0 12px; color:#70616C; font-size:12px; line-height:1.45; }
      .start-id-note {
        background:#fffaf0; border:1px solid #f2d8a4; border-left:4px solid #c98b21; border-radius:9px;
        color:#71440a; font-size:11.5px; line-height:1.45; padding:9px 11px; margin:4px 0 11px;
      }
      .mode-summary {
        border-radius:10px; padding:10px 12px; margin:8px 0 2px; font-size:12px; line-height:1.45;
        background:#FCF4F8; border:1px solid #EED7E1; color:#6B4053;
      }
      .submission-summary {
        margin-top:12px; padding:11px 12px; border-radius:10px; background:#FCF8FA; border:1px solid #EEE1E7;
        color:#745261; font-size:11.5px; line-height:1.5;
      }
      .submission-summary b { color:#471F31; }
      .apparatus-topline { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; margin-bottom:2px; }
      .apparatus-title { color:#29202A; font-size:18px; font-weight:800; line-height:1.2; }
      .apparatus-caption { color:#70616C; font-size:12px; line-height:1.45; margin-top:4px; }
      .apparatus-badges { display:flex; flex-wrap:wrap; gap:6px; justify-content:flex-end; }
      .apparatus-badge {
        padding:5px 8px; border-radius:999px; background:#FBF3F7; border:1px solid #EDD8E1;
        color:#664252; font-size:10.5px; font-weight:700; white-space:nowrap;
      }
      .apparatus-legend {
        display:flex; flex-wrap:wrap; justify-content:center; gap:9px; margin:-2px 0 8px;
        color:#70616C; font-size:10.5px;
      }
      .legend-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:4px; }
      .detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
      .detail-box { background:#FCF8FA; border:1px solid #EEE1E7; border-radius:9px; padding:10px 11px; color:#745261; font-size:11px; line-height:1.5; }
      .detail-box b { color:#471F31; }

      /* Consistent controls and interaction styling */
      .stButton > button, .stDownloadButton > button {
        min-height:2.42rem;
        border-radius:9px;
        font-weight:700;
        transition:background-color .14s ease, border-color .14s ease, box-shadow .14s ease;
      }
      .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
        background:var(--jcu-blue);
        border-color:var(--jcu-blue);
        color:#ffffff;
        box-shadow:0 2px 6px rgba(166,44,99,.16);
      }
      .stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
        background:var(--jcu-blue-dark);
        border-color:var(--jcu-blue-dark);
        box-shadow:0 3px 9px rgba(166,44,99,.22);
      }
      .stButton > button[kind="secondary"] {
        background:#ffffff;
        border-color:#E1CAD4;
        color:#5A3143;
      }
      .stButton > button[kind="secondary"]:hover { border-color:#C488A3; color:var(--jcu-blue); }
      [data-baseweb="input"] > div, [data-baseweb="select"] > div, [data-baseweb="textarea"] > div {
        border-radius:9px !important;
        border-color:#E7D5DD !important;
        background:#FDFBFC !important;
      }
      [data-baseweb="input"] > div:focus-within, [data-baseweb="select"] > div:focus-within, [data-baseweb="textarea"] > div:focus-within {
        border-color:#C56E95 !important;
        box-shadow:0 0 0 3px rgba(166,44,99,.09) !important;
        background:#ffffff !important;
      }
      div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color:#ECDCE3 !important;
        border-radius:14px !important;
        box-shadow:0 3px 12px rgba(42,15,27,.035);
        background:#ffffff;
      }
      div[data-testid="stAlert"] { border-radius:10px; }
      div[data-testid="stDataEditor"] { border:1px solid #ECDCE3; border-radius:11px; overflow:hidden; }
      div[data-testid="stMetric"] {
        background:#ffffff;
        border:1px solid #EEDFE6;
        padding:12px 14px;
        border-radius:11px;
        box-shadow:0 2px 8px rgba(42,15,27,.025);
      }
      details[data-testid="stExpander"] { border-color:#ECDCE3 !important; border-radius:10px !important; background:#FDFBFC; }
      h1, h2, h3 { letter-spacing:-0.018em; }
      h2, h3 { color:#29202A; }
      .stCaption { color:#947482; }

      @media (max-width:980px) {
        .start-hero { flex-direction:column; }
        .start-steps { justify-content:flex-start; min-width:0; }
        .detail-grid { grid-template-columns:1fr; }
        .app-header { grid-template-columns:1fr; text-align:center; gap:14px; }
        .header-logo { justify-content:center; border-right:0; border-bottom:1px solid #EEE0E6; padding:2px 12px 15px; }
        .header-logo img { max-width:235px; }
        .app-header-meta { border-left:0; border-top:1px solid #EEE0E6; padding:13px 0 0; text-align:center; }
      }
    

      :root {
        --jcu-blue:#A62C63;
        --jcu-blue-dark:#7D1F49;
        --secondary:#C34C83;
        --success:#27AE60;
        --warning-ui:#F2994A;
        --neutral:#FCF8FA;
        --ink:#29202A;
        --muted:#70616C;
        --line:#F0E3E9;
      }

      /* A lighter, narrower sidebar that supports rather than dominates. */
      [data-testid="stSidebar"] {
        background:#FFFFFF;
        border-right:1px solid var(--line);
        min-width:236px;
        max-width:248px;
      }
      [data-testid="stSidebar"] > div:first-child { padding:0.70rem 0.78rem 1rem; }
      .sidebar-brand {
        padding:3px 2px 10px;
        margin:0 0 7px;
        border-left:0;
        background:transparent;
      }
      .sidebar-brand .title { color:var(--jcu-blue); font-size:20px; margin:0; }
      .sidebar-brand .course {
        color:#745261; font-size:11px; font-weight:700; letter-spacing:0;
        text-transform:none; margin-top:3px;
      }
      .sidebar-brand .subtitle { display:none; }

      .sidebar-progress-head {
        display:flex; align-items:center; justify-content:space-between;
        color:#472434; font-size:14px; font-weight:800; margin:5px 1px 5px;
      }
      .sidebar-progress-head span { color:var(--jcu-blue); font-size:13px; }
      .sidebar-progress-meta { color:#947382; font-size:11px; margin:4px 1px 13px; }
      [data-testid="stSidebar"] [data-testid="stProgress"] { margin-bottom:0; }
      [data-testid="stSidebar"] [data-testid="stProgress"] > div { background:#F3E7EC; height:6px; }
      [data-testid="stSidebar"] [data-testid="stProgress"] > div > div { background:var(--secondary); }

      .sidebar-workflow-title { color:#553342; font-size:13px; font-weight:800; margin:5px 1px 6px; }
      [data-testid="stSidebar"] [data-testid="stRadio"] > div {
        gap:0; position:relative; padding-left:1px;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label {
        background:transparent; border:0; border-radius:7px;
        padding:0.42rem 0.32rem; margin:0; min-height:0;
        transition:background-color .13s ease,color .13s ease;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background:#FBF3F7; border:0;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background:#FBEEF4; border:0; box-shadow:none;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
        color:var(--jcu-blue); font-weight:800;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child { display:none !important; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label p {
        color:#745261; font-size:12.5px; line-height:1.28; margin:0;
      }

      .sidebar-pathway {
        margin-top:14px; padding-top:11px; border-top:1px solid var(--line);
        color:#967182; font-size:11px; line-height:1.45;
      }
      .sidebar-pathway strong { display:block; color:#4A2636; font-size:12.5px; margin-top:2px; }
      .sidebar-status-inline {
        display:flex; gap:7px; align-items:flex-start; margin-top:8px;
        color:#745261; font-size:11px; line-height:1.38;
      }
      .sidebar-status-inline .dot {
        flex:0 0 auto; width:8px; height:8px; border-radius:50%; margin-top:4px; background:#B894A4;
      }
      .sidebar-status-inline.good .dot { background:var(--success); }
      .sidebar-status-inline.warn .dot { background:var(--warning-ui); }
      .sidebar-footer {
        border-top:0; margin-top:13px; padding:0 1px; color:#947B86;
        font-size:10.5px; line-height:1.45;
      }

      /* Consistent type hierarchy. */
      .app-header-title h1 { font-size:36px; }
      .page-heading .section-title { font-size:24px; }
      .page-heading .section-label {
        color:var(--jcu-blue); font-size:12px; font-weight:700; letter-spacing:0; text-transform:none;
      }
      .panel-heading, .apparatus-title { font-size:18px; }
      .page-heading .section-summary, .app-header-title p { font-size:14px; }
      .panel-subheading, .apparatus-caption, .small-note { font-size:12px; }

      /* Fewer boxes: use whitespace, tonal surfaces and accent edges. */
      .info { background:#FFEFF6; border:0; border-left:4px solid var(--secondary); color:#742448; }
      .hint, .good { background:#ECFDF3; border:0; border-left:4px solid var(--success); color:#17663A; }
      .warning { background:#FFF8EC; border:0; border-left:4px solid var(--warning-ui); color:#71440A; }
      .card { border:0; border-radius:10px; background:var(--neutral); box-shadow:none; }
      div[data-testid="stVerticalBlockBorderWrapper"] {
        border:0 !important; border-radius:14px !important; background:var(--neutral);
        box-shadow:none;
      }
      .start-id-note {
        background:transparent; border:0; border-left:3px solid var(--warning-ui);
        border-radius:0; padding:6px 10px; margin:3px 0 10px;
      }
      .mode-summary {
        background:#FCF2F6; border:0; border-left:3px solid var(--secondary); border-radius:7px;
      }
      .submission-summary {
        background:transparent; border:0; border-top:1px solid var(--line); border-radius:0;
        padding:11px 0 0; margin-top:15px;
      }
      .apparatus-badge { background:#F9EEF3; border:0; color:#664252; }
      .detail-box { background:#FFFFFF; border:0; box-shadow:0 1px 5px rgba(42,15,27,.04); }
      div[data-testid="stMetric"] { border:0; background:var(--neutral); box-shadow:none; }
      div[data-testid="stDataEditor"] { border:1px solid var(--line); box-shadow:none; }
      details[data-testid="stExpander"] { border:0 !important; background:var(--neutral); }

      /* Keep the first page spacious and visually prioritise data entry. */
      .student-form-intro { margin:0 0 15px; }
      .student-form-intro .title { color:#29202A; font-size:18px; font-weight:800; }
      .student-form-intro .text { color:#70616C; font-size:12px; line-height:1.5; margin-top:4px; }
      .apparatus-soft-note {
        color:#745261; font-size:11.5px; line-height:1.45; margin:0 0 8px;
      }

      @media (max-width:980px) {
        [data-testid="stSidebar"] { min-width:220px; max-width:232px; }
      }
    

      /* Reduce header-logo dominance while preserving JCU identity. */
      .header-logo img { max-width:176px !important; }
      .header-logo { min-height:68px; padding-right:20px; }

      /* Modern, compact sidebar. */
      [data-testid="stSidebar"] > div:first-child {
        padding:0.72rem 0.78rem 1rem;
      }
      .sidebar-brand { margin-bottom:4px; padding-bottom:7px; }
      .sidebar-brand .title { font-size:19px; }
      .sidebar-brand .course { font-size:10.5px; }

      .sidebar-progress-head { margin-top:3px; }
      [data-testid="stSidebar"] [data-testid="stProgress"] > div {
        height:7px;
        border-radius:999px;
        background:#F3E7EC;
        overflow:hidden;
      }
      [data-testid="stSidebar"] [data-testid="stProgress"] > div > div {
        border-radius:999px;
        background:linear-gradient(90deg,#A62C63 0%,#C34C83 100%);
        transition:width .45s ease;
      }
      .sidebar-progress-meta { margin-bottom:11px; }
      .sidebar-workflow-title { margin-top:2px; }

      [data-testid="stSidebar"] [data-testid="stRadio"] label {
        position:relative;
        border-left:3px solid transparent;
        border-radius:8px;
        padding:0.43rem 0.42rem 0.43rem 0.50rem;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background:#FBEAF2;
        border-left-color:#C34C83;
        box-shadow:0 2px 7px rgba(166,44,99,.07);
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
        color:#A62C63;
        font-weight:800;
      }

      .sidebar-pathway { margin-top:11px; padding-top:10px; }
      .sidebar-summary-card {
        margin-top:12px;
        padding:11px 11px 10px;
        border-radius:11px;
        background:#FCF8FA;
        box-shadow:0 2px 9px rgba(42,15,27,.045);
      }
      .sidebar-summary-title {
        color:#4A2536;
        font-size:12px;
        font-weight:800;
        margin-bottom:7px;
      }
      .sidebar-summary-row {
        display:grid;
        grid-template-columns:18px 1fr;
        gap:7px;
        align-items:start;
        color:#7A5A68;
        font-size:10.7px;
        line-height:1.35;
        margin:5px 0;
      }
      .sidebar-summary-row .icon { text-align:center; }
      .sidebar-summary-row b { color:#4A2636; font-weight:750; }
      .sidebar-footer { margin-top:11px; }

      /* Compact welcome dashboard below the page heading. */
      .welcome-dashboard {
        display:grid;
        grid-template-columns:minmax(0,1.15fr) minmax(330px,.85fr);
        gap:18px;
        align-items:center;
        margin:2px 0 18px;
        padding:16px 18px;
        border-radius:13px;
        background:linear-gradient(135deg,#FDF7FA 0%,#FFFFFF 65%);
        box-shadow:0 3px 14px rgba(42,15,27,.055);
      }
      .welcome-dashboard .eyebrow {
        color:#C34C83;
        font-size:11px;
        font-weight:800;
        margin-bottom:4px;
      }
      .welcome-dashboard .title {
        color:#29202A;
        font-size:20px;
        font-weight:800;
        line-height:1.2;
      }
      .welcome-dashboard .text {
        color:#836070;
        font-size:12.5px;
        line-height:1.48;
        margin-top:5px;
      }
      .welcome-list {
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:7px 12px;
      }
      .welcome-item {
        display:flex;
        align-items:flex-start;
        gap:7px;
        color:#664252;
        font-size:11.5px;
        line-height:1.35;
      }
      .welcome-item .check { color:#27AE60; font-weight:900; }
      .welcome-time {
        grid-column:1 / -1;
        margin-top:2px;
        color:#745261;
        font-size:11.5px;
        font-weight:700;
      }

      /* Stronger contrast for the apparatus panel. */
      div[data-testid="stVerticalBlockBorderWrapper"] {
        background:#FFFFFF !important;
        border:0 !important;
        box-shadow:0 5px 18px rgba(42,15,27,.07) !important;
      }
      .apparatus-soft-note { margin-bottom:5px; }

      /* Reduce density on the first page. */
      .student-form-intro { margin-bottom:10px; }
      .student-form-intro .text { max-width:520px; }
      .submission-summary { font-size:11.2px; line-height:1.42; }
      .mode-summary { font-size:11.5px; line-height:1.4; }

      @media (max-width:1100px) {
        .welcome-dashboard { grid-template-columns:1fr; }
        .welcome-list { grid-template-columns:1fr 1fr; }
      }
      @media (max-width:760px) {
        .welcome-list { grid-template-columns:1fr; }
        .welcome-time { grid-column:auto; }
        .header-logo img { max-width:190px !important; }
      }
    

      /* Keep the product name visually dominant over the institutional mark. */
      .app-header {
        grid-template-columns:185px minmax(0,1fr) 220px;
        gap:22px;
      }
      .header-logo {
        min-height:60px;
        padding:1px 18px 1px 0;
      }
      .header-logo img {
        width:auto !important;
        max-width:145px !important;
        max-height:58px;
        object-fit:contain;
      }

      /* Lift the welcome panel from the page without creating a heavy card. */
      .welcome-dashboard {
        position:relative;
        overflow:hidden;
        background:linear-gradient(135deg,#FFFFFF 0%,#FFF7FB 100%);
        border:1px solid #F5D9E6;
        box-shadow:0 8px 24px rgba(166,44,99,.075);
        padding:18px 20px;
      }
      .welcome-dashboard::before {
        content:"";
        position:absolute;
        top:0;
        left:0;
        right:0;
        height:3px;
        background:linear-gradient(90deg,#A62C63 0%,#C34C83 100%);
      }
      .welcome-dashboard .eyebrow {
        color:#A62C63;
        font-size:11px;
      }
      .welcome-dashboard .title {
        font-size:21px;
      }
      .welcome-dashboard .text {
        max-width:610px;
      }
      .welcome-list {
        border-left:1px solid #F3E2EA;
        padding-left:18px;
      }

      /* Make the current workflow stage unmistakable. */
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background:#F9DCE9;
        border-left:5px solid #A62C63;
        border-radius:8px;
        box-shadow:0 3px 10px rgba(166,44,99,.10);
        padding-left:0.54rem;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
        color:#A62C63;
        font-size:13px;
        font-weight:850;
      }

      /* Quiet, structured footer. */
      .sidebar-footer {
        margin-top:14px;
        padding:11px 1px 2px;
        border-top:1px solid #EDDCE4;
        color:#967A87;
        font-size:10.5px;
        line-height:1.48;
      }
      .sidebar-footer .footer-help {
        color:#70616C;
        margin-bottom:10px;
      }
      .sidebar-footer .footer-version {
        color:#5E3447;
        font-weight:800;
        margin-bottom:2px;
      }

      @media (max-width:980px) {
        .app-header { grid-template-columns:1fr; }
        .header-logo {
          min-height:auto;
          padding:0 0 12px;
        }
        .header-logo img { max-width:155px !important; }
        .welcome-list {
          border-left:0;
          border-top:1px solid #F3E2EA;
          padding:12px 0 0;
        }
      }
    

      /* Keep TrussLab as the primary visual anchor; the JCU mark is supporting identity. */
      .app-header {
        grid-template-columns:155px minmax(0,1fr) 205px;
        gap:20px;
      }
      .header-logo {
        min-height:52px;
        padding:0 15px 0 0;
      }
      .header-logo img {
        max-width:118px !important;
        max-height:47px;
      }

      /* Subtle welcome panel with vertically balanced content. */
      .welcome-dashboard {
        background:#FFFAFC;
        border:1px solid #F4E7ED;
        box-shadow:0 4px 12px rgba(0,0,0,.04);
        padding:18px 20px;
        align-items:center;
      }
      .welcome-dashboard::before {
        height:2px;
      }
      .welcome-dashboard > div:first-child,
      .welcome-dashboard .welcome-list {
        align-self:center;
      }
      .welcome-dashboard .welcome-list {
        align-content:center;
        min-height:100%;
      }

      /* Give progress enough visual weight without making the sidebar heavy. */
      [data-testid="stSidebar"] [data-testid="stProgress"] > div {
        height:10px;
        border-radius:999px;
      }
      [data-testid="stSidebar"] [data-testid="stProgress"] > div > div {
        border-radius:999px;
      }

      /* Make an unselected pathway impossible to overlook. */
      .pathway-choice-warning {
        background:#FFF8EC !important;
        border-left-color:#F2994A !important;
        color:#71440A !important;
      }
      .sidebar-pathway-alert {
        display:flex;
        gap:8px;
        align-items:flex-start;
        margin-top:12px;
        padding:9px 10px;
        border-radius:9px;
        background:#FFF8EC;
        border-left:4px solid #F2994A;
        color:#71440A;
        font-size:11px;
        line-height:1.35;
      }
      .sidebar-pathway-alert .alert-icon {
        flex:0 0 auto;
        font-size:13px;
        line-height:1.2;
      }
      .sidebar-pathway-alert strong {
        display:block;
        color:#71440A;
        font-size:11.5px;
        font-weight:800;
      }
      .sidebar-pathway-alert small {
        display:block;
        margin-top:2px;
        color:#8A5B1A;
        font-size:10.5px;
      }

      .sidebar-footer .footer-credit {
        margin-top:7px;
        color:#A38A95;
        font-size:10px;
      }

      @media (max-width:980px) {
        .header-logo img { max-width:126px !important; }
      }
    

      /* Slightly more compact apparatus reference card. */
      div[data-testid="stVerticalBlockBorderWrapper"] {
        padding:0.68rem 0.76rem 0.72rem !important;
      }
      div[data-testid="stVerticalBlockBorderWrapper"] .apparatus-topline {
        margin-bottom:-2px;
      }
      div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stImage"] {
        margin-top:-0.18rem;
        margin-bottom:-0.12rem;
      }
      div[data-testid="stVerticalBlockBorderWrapper"] .apparatus-legend {
        margin-top:-3px;
      }

      /* Improve workflow scanning without increasing sidebar weight. */
      [data-testid="stSidebar"] [data-testid="stRadio"] label p {
        font-size:13.5px;
        font-weight:500;
        letter-spacing:-0.005em;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
        font-size:13.5px;
        font-weight:800;
      }

      /* Premium progress treatment: thicker, rounded and subtly illuminated. */
      [data-testid="stSidebar"] [data-testid="stProgress"] > div {
        height:11px;
        border-radius:999px;
        background:#F4E6EC;
        box-shadow:inset 0 1px 2px rgba(42,15,27,.08);
        overflow:hidden;
      }
      [data-testid="stSidebar"] [data-testid="stProgress"] > div > div {
        border-radius:999px;
        background:linear-gradient(90deg,#A62C63 0%,#B13A72 52%,#C34C83 100%);
        box-shadow:0 1px 5px rgba(195,76,131,.28);
        transition:width .45s ease;
      }

      /* Explicit first action for students who are new to the practical. */
      .welcome-next-step {
        margin:-8px 2px 18px;
        color:#745261;
        font-size:13px;
        line-height:1.45;
      }
      .welcome-next-step b {
        color:#A62C63;
        font-weight:800;
      }

      @media (max-width:760px) {
        .welcome-next-step { margin-top:-6px; }
      }
    

      /* Reusable section dashboard: the same visual language as the first page. */
      .section-dashboard {
        display:grid;
        grid-template-columns:minmax(0,1.12fr) minmax(300px,.88fr);
        gap:20px;
        align-items:center;
        margin:2px 0 18px;
        padding:18px 20px;
        border-radius:13px;
        background:#FFFAFC;
        border:1px solid #F4E6EC;
        box-shadow:0 4px 12px rgba(0,0,0,.04);
        position:relative;
        overflow:hidden;
      }
      .section-dashboard::before {
        content:"";
        position:absolute;
        top:0;
        left:0;
        right:0;
        height:2px;
        background:linear-gradient(90deg,#A62C63 0%,#C34C83 100%);
      }
      .section-dashboard .eyebrow {
        color:#A62C63;
        font-size:11px;
        font-weight:800;
        margin-bottom:4px;
      }
      .section-dashboard .title {
        color:#29202A;
        font-size:20px;
        line-height:1.2;
        font-weight:800;
        letter-spacing:-0.015em;
      }
      .section-dashboard .description {
        color:#836070;
        font-size:12.5px;
        line-height:1.48;
        margin-top:5px;
        max-width:650px;
      }
      .section-dashboard .dashboard-list {
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:7px 12px;
        align-content:center;
        border-left:1px solid #F3E2EA;
        padding-left:18px;
      }
      .section-dashboard .dashboard-item {
        display:flex;
        align-items:flex-start;
        gap:7px;
        color:#664252;
        font-size:11.5px;
        line-height:1.36;
      }
      .section-dashboard .dashboard-item .check {
        color:#27AE60;
        font-weight:900;
        flex:0 0 auto;
      }
      .section-dashboard .dashboard-meta {
        grid-column:1 / -1;
        display:flex;
        flex-wrap:wrap;
        gap:7px;
        margin-top:3px;
      }
      .section-dashboard .meta-pill {
        display:inline-flex;
        align-items:center;
        gap:5px;
        padding:4px 8px;
        border-radius:999px;
        background:#FBEEF4;
        color:#733651;
        font-size:10.5px;
        font-weight:700;
      }
      .section-next-action {
        margin:-8px 2px 18px;
        color:#745261;
        font-size:13px;
        line-height:1.45;
      }
      .section-next-action b { color:#A62C63; font-weight:800; }

      /* Content hierarchy: fewer hard borders, more spacing and soft surfaces. */
      .content-heading { margin:0 0 11px; }
      .content-heading .title {
        color:#29202A;
        font-size:18px;
        font-weight:800;
        line-height:1.25;
      }
      .content-heading .text {
        color:#70616C;
        font-size:12px;
        line-height:1.48;
        margin-top:4px;
      }
      .soft-panel {
        background:#FFFFFF;
        border:1px solid #F3E7EC;
        border-radius:12px;
        padding:14px 15px;
        box-shadow:0 3px 12px rgba(42,15,27,.04);
        margin-bottom:13px;
      }
      .soft-panel.tint { background:#FEF8FB; }
      .soft-panel .panel-title {
        color:#441C2E;
        font-size:15px;
        font-weight:800;
        margin-bottom:5px;
      }
      .soft-panel .panel-text {
        color:#836070;
        font-size:11.5px;
        line-height:1.48;
      }
      .process-list {
        margin:7px 0 0;
        padding:0;
        list-style:none;
        counter-reset:steps;
      }
      .process-list li {
        counter-increment:steps;
        display:grid;
        grid-template-columns:23px 1fr;
        gap:8px;
        align-items:start;
        color:#6E4A5A;
        font-size:11.5px;
        line-height:1.46;
        margin:7px 0;
      }
      .process-list li::before {
        content:counter(steps);
        display:flex;
        align-items:center;
        justify-content:center;
        width:20px;
        height:20px;
        border-radius:50%;
        background:#FBEAF2;
        color:#A62C63;
        font-size:10px;
        font-weight:800;
      }
      .mini-rule { height:1px; background:#F3E7EC; margin:12px 0; }
      .status-strip {
        display:flex;
        align-items:flex-start;
        gap:9px;
        border-radius:10px;
        padding:10px 12px;
        margin:9px 0 14px;
        font-size:11.5px;
        line-height:1.43;
      }
      .status-strip.info { background:#FFEFF6; color:#742448; border:0; }
      .status-strip.success { background:#ECFDF3; color:#17663A; }
      .status-strip.warning { background:#FFF8EC; color:#71440A; }
      .status-strip .status-icon { flex:0 0 auto; font-size:14px; line-height:1.15; }
      .sign-convention {
        display:flex;
        gap:8px;
        flex-wrap:wrap;
        margin:4px 0 13px;
      }
      .sign-chip {
        padding:5px 9px;
        border-radius:999px;
        font-size:10.5px;
        font-weight:800;
      }
      .sign-chip.tension { background:#ECFDF3; color:#17663A; }
      .sign-chip.compression { background:#FFF1F2; color:#9F1239; }
      .report-note {
        background:#FCF8FA;
        border-left:4px solid #C34C83;
        border-radius:8px;
        padding:11px 13px;
        color:#745261;
        font-size:11.5px;
        line-height:1.5;
        margin:12px 0 2px;
      }
      .report-note b { color:#522338; }
      .checklist-grid {
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:8px;
        margin:11px 0;
      }
      .checklist-item {
        display:flex;
        align-items:center;
        gap:8px;
        padding:8px 9px;
        border-radius:8px;
        background:#FCF8FA;
        color:#745261;
        font-size:11px;
        line-height:1.35;
      }
      .checklist-item.done { background:#ECFDF3; color:#17663A; }
      .checklist-item .mark { font-weight:900; }

      /* Keep plots and tables visually contained without heavy frames. */
      .element-container:has(div[data-testid="stDataFrame"]),
      .element-container:has(div[data-testid="stDataEditor"]) {
        margin-bottom:0.55rem;
      }
      div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
        border-radius:11px;
        overflow:hidden;
      }

      @media (max-width:1050px) {
        .section-dashboard { grid-template-columns:1fr; }
        .section-dashboard .dashboard-list {
          border-left:0;
          border-top:1px solid #F3E2EA;
          padding:12px 0 0;
        }
      }
      @media (max-width:720px) {
        .section-dashboard .dashboard-list,
        .checklist-grid { grid-template-columns:1fr; }
      }
    

      :root {
        color-scheme: light !important;
        --trusslab-ink: #29202A;
        --trusslab-muted: #625360;
        --trusslab-surface: #FFFFFF;
        --trusslab-input: #FFFFFF;
      }

      html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: var(--trusslab-surface) !important;
        color: var(--trusslab-ink) !important;
      }

      /* Native Streamlit text and widget labels. */
      [data-testid="stAppViewContainer"] .stMarkdown,
      [data-testid="stAppViewContainer"] .stMarkdown p,
      [data-testid="stAppViewContainer"] .stMarkdown li,
      [data-testid="stAppViewContainer"] .stWidgetLabel,
      [data-testid="stAppViewContainer"] .stWidgetLabel p,
      [data-testid="stAppViewContainer"] [data-testid="stRadio"] label,
      [data-testid="stAppViewContainer"] [data-testid="stRadio"] label p,
      [data-testid="stAppViewContainer"] [data-testid="stCheckbox"] label,
      [data-testid="stAppViewContainer"] [data-testid="stCheckbox"] label p,
      [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] label,
      [data-testid="stAppViewContainer"] [data-testid="stNumberInput"] label,
      [data-testid="stAppViewContainer"] [data-testid="stTextInput"] label,
      [data-testid="stAppViewContainer"] [data-testid="stTextArea"] label {
        color: var(--trusslab-ink) !important;
        -webkit-text-fill-color: var(--trusslab-ink) !important;
        opacity: 1 !important;
      }

      /* Inputs and dropdowns stay light with dark, readable values. */
      [data-baseweb="input"] > div,
      [data-baseweb="textarea"] > div,
      [data-baseweb="select"] > div {
        background-color: var(--trusslab-input) !important;
        color: var(--trusslab-ink) !important;
      }
      [data-baseweb="input"] input,
      [data-baseweb="textarea"] textarea,
      [data-baseweb="select"] input,
      [data-baseweb="select"] span,
      [role="listbox"],
      [role="listbox"] * {
        color: var(--trusslab-ink) !important;
        -webkit-text-fill-color: var(--trusslab-ink) !important;
        opacity: 1 !important;
      }
      [role="listbox"] {
        background-color: #FFFFFF !important;
      }
      input::placeholder, textarea::placeholder {
        color: #70616C !important;
        -webkit-text-fill-color: #70616C !important;
        opacity: 1 !important;
      }

      /* Radio and checkbox controls must remain visible on white surfaces. */
      [data-testid="stRadio"] [role="radiogroup"] {
        color: var(--trusslab-ink) !important;
      }
      [data-testid="stRadio"] label > div:first-child,
      [data-testid="stCheckbox"] label > span:first-child {
        opacity: 1 !important;
      }

      /* Containers used by the practical questions and panels. */
      div[data-testid="stVerticalBlockBorderWrapper"],
      details[data-testid="stExpander"],
      div[data-testid="stMetric"],
      .soft-panel,
      .section-dashboard,
      .welcome-dashboard,
      .card,
      .detail-box {
        background-color: #FFFFFF !important;
        color: var(--trusslab-ink) !important;
      }

      /* Preserve intentional semantic colours while preventing washed-out text. */
      .content-heading .text,
      .page-heading .section-summary,
      .section-dashboard .description,
      .section-next-action,
      .panel-subheading,
      .apparatus-caption,
      .small-note,
      [data-testid="stCaptionContainer"],
      [data-testid="stCaptionContainer"] p {
        color: var(--trusslab-muted) !important;
        -webkit-text-fill-color: var(--trusslab-muted) !important;
        opacity: 1 !important;
      }
      .status-strip.info, .status-strip.info * {
        color: #742448 !important;
        -webkit-text-fill-color: #742448 !important;
      }
      .status-strip.success, .status-strip.success * {
        color: #17663A !important;
        -webkit-text-fill-color: #17663A !important;
      }
      .status-strip.warning, .status-strip.warning * {
        color: #71440A !important;
        -webkit-text-fill-color: #71440A !important;
      }

      /* Sidebar remains a fixed light interface in every OS/browser mode. */
      [data-testid="stSidebar"],
      [data-testid="stSidebar"] > div:first-child {
        background-color: #FFFFFF !important;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label p {
        color: #745261 !important;
        -webkit-text-fill-color: #745261 !important;
        opacity: 1 !important;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
        color: #A62C63 !important;
        -webkit-text-fill-color: #A62C63 !important;
        font-weight: 800 !important;
      }

      /* Buttons: keep primary buttons white-on-dark-pink and secondary dark-on-white. */
      .stButton > button[kind="primary"],
      .stDownloadButton > button[kind="primary"] {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
      }
      .stButton > button[kind="primary"] *,
      .stDownloadButton > button[kind="primary"] * {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
      }
      .stButton > button[kind="secondary"],
      .stButton > button[kind="secondary"] * {
        color: #5A3143 !important;
        -webkit-text-fill-color: #5A3143 !important;
      }

      /* Tables and metrics. */
      [data-testid="stMetricLabel"],
      [data-testid="stMetricLabel"] *,
      [data-testid="stMetricValue"],
      [data-testid="stMetricValue"] * {
        color: var(--trusslab-ink) !important;
        -webkit-text-fill-color: var(--trusslab-ink) !important;
      }
      [data-testid="stDataFrame"],
      [data-testid="stDataEditor"] {
        color: var(--trusslab-ink) !important;
        background-color: #FFFFFF !important;
      }

      /* Support Windows forced-colour/high-contrast mode rather than hiding controls. */
      @media (forced-colors: active) {
        [data-testid="stRadio"] label,
        [data-testid="stCheckbox"] label,
        input, textarea, button {
          forced-color-adjust: auto;
        }
      }
    

/* 2027 uses the 2026 interface with a dark pink accent. */
:root { --primary-color:#A62C63; --jcu-blue:#A62C63; --jcu-blue-dark:#7D1F49; --secondary:#C34C83; --trusslab-ink:#29202A; --trusslab-muted:#625360; }
[data-testid="stForm"] { border:0 !important; padding:0 !important; background:transparent !important; }
[data-testid="stFormSubmitButton"] > button { border-radius:9px; font-weight:700; }
[data-testid="stFormSubmitButton"] > button[kind="primary"], [data-testid="stBaseButton-primary"] { background:#A62C63 !important; border-color:#A62C63 !important; }
[data-testid="stFormSubmitButton"] > button[kind="primary"] *, [data-testid="stBaseButton-primary"] * { color:white !important; -webkit-text-fill-color:white !important; }
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover { background:#7D1F49 !important; border-color:#7D1F49 !important; }
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stFileUploaderDropzone"]:hover { border-color:#C34C83 !important; }
[data-testid="stProgress"] [role="progressbar"] > div, [data-testid="stProgress"] [role="progressbar"] > div > div { background:linear-gradient(90deg,#A62C63,#C34C83) !important; }
[data-testid="stSlider"] [role="slider"] { background:#A62C63 !important; border-color:#A62C63 !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="select"]:focus-within, [data-baseweb="textarea"]:focus-within { border-color:#C34C83 !important; }
[data-testid="stCheckbox"] input:checked + div, [data-testid="stToggle"] input:checked + div { background-color:#A62C63 !important; }
[data-testid="stRadio"] label:has(input:checked) > div:first-child { background-color:#A62C63 !important; border-color:#A62C63 !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:#F8E6EE !important; border-left-color:#A62C63 !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p { color:#A62C63 !important; -webkit-text-fill-color:#A62C63 !important; }
[data-testid="stFileUploaderDropzone"] { background:#FDF9FB; border:1px dashed #D5A7BC; border-radius:11px; }
[data-testid="stAlertContainer"]:has([data-testid="stInfo"]) { background:#FCF2F7; }
.app-header-meta .version { display:inline-block; margin-top:8px; padding:3px 9px; background:#F8E6EE; color:#A62C63; font-size:10.5px; font-weight:800; border-radius:999px; }
.apparatus-panel-intro { margin-bottom:7px; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary { font-size:11px; }
@media (max-width:720px) { .app-header-title h1 {font-size:30px;} .page-heading .section-title {font-size:22px;} }

/* Final readability rules apply in light/dark Streamlit and OS themes. */
:root { color-scheme:light !important; --trusslab-ink:#29202A; --trusslab-muted:#625360; }
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],[data-testid="stSidebar"],
[data-testid="stSidebarContent"],[data-testid="stPopoverBody"],[data-testid="stDialog"] { background-color:#FFFFFF !important; color:#29202A !important; }
[data-testid="stAppViewContainer"] input:not([type="checkbox"]):not([type="radio"]),
[data-testid="stAppViewContainer"] textarea,[data-testid="stAppViewContainer"] select,
[data-testid="stAppViewContainer"] [data-baseweb="input"],
[data-testid="stAppViewContainer"] [data-baseweb="base-input"],
[data-testid="stAppViewContainer"] [data-baseweb="select"] > div,
[data-testid="stAppViewContainer"] [data-baseweb="textarea"] {
 background-color:#FFFFFF !important; color:#29202A !important; -webkit-text-fill-color:#29202A !important; caret-color:#A62C63 !important; color-scheme:light !important;
}
[data-baseweb="popover"],[data-baseweb="menu"],[role="listbox"],[role="option"],
[data-testid="stTooltipContent"],[data-testid="stPopoverBody"] { background-color:#FFFFFF !important; color:#29202A !important; }
[role="option"] *,[data-testid="stPopoverBody"] p,[data-testid="stTooltipContent"] * { color:#29202A !important; -webkit-text-fill-color:#29202A !important; }
[data-testid="stAppViewContainer"] button[kind="secondary"],
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-secondary"],
[data-testid="stAppViewContainer"] button[kind="secondary"] *,
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-secondary"] * {
 background-color:#FFFFFF !important; color:#492C3B !important; -webkit-text-fill-color:#492C3B !important;
}
[data-testid="stAppViewContainer"] button[kind="primary"],
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-primary"] {
 background-color:#A62C63 !important; border-color:#A62C63 !important;
}
[data-testid="stAppViewContainer"] button[kind="primary"] *,
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-primary"] *,
[data-testid="stAppViewContainer"] button[kind="primary"],
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-primary"] {
 color:#FFFFFF !important; -webkit-text-fill-color:#FFFFFF !important;
}
[data-testid="stAppViewContainer"] button:disabled,
[data-testid="stAppViewContainer"] button:disabled * {
 background-color:#EEE7EC !important; border-color:#D7CAD2 !important; color:#65535F !important; -webkit-text-fill-color:#65535F !important; opacity:1 !important;
}
.sidebar-progress-meta,.sidebar-footer,.sidebar-footer *,.sidebar-summary-row,
.welcome-dashboard .text,.welcome-item,.welcome-time,.apparatus-caption,
.panel-subheading,.page-heading .section-summary,.section-dashboard .description {
 color:#625360 !important; -webkit-text-fill-color:#625360 !important;
}
[data-testid="stRadio"] label > div:first-child { display:flex !important; opacity:1 !important; }
[data-testid="stCheckbox"] label > span:first-child { display:inline-flex !important; opacity:1 !important; }
input::placeholder,textarea::placeholder { color:#70616C !important; -webkit-text-fill-color:#70616C !important; opacity:1 !important; }
@media (prefers-color-scheme:dark) {
 html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stSidebar"] { background-color:#FFFFFF !important; color:#29202A !important; }
}
@media (forced-colors:active) {
 [data-testid="stAppViewContainer"] button,[data-testid="stAppViewContainer"] button *,
 [data-testid="stAppViewContainer"] input,[data-testid="stAppViewContainer"] textarea {
 forced-color-adjust:auto !important; color:CanvasText !important; -webkit-text-fill-color:CanvasText !important; background:Canvas !important; border-color:ButtonText !important;
 }
}

</style>
"""



# Keep the apparatus drawing visually consistent with the 2026 reference.
# Force-state colours retain their physical meaning.
from matplotlib.figure import Figure
from matplotlib.patches import Circle, FancyArrowPatch, Polygon

UI_COLORS = {"member":"#334155", "joint":"#111827", "ring":"#A62C63", "load":"#C62828"}

def _ui_member_colour(force):
    return "#2E7D32" if force > 1e-7 else "#C62828" if force < -1e-7 else "#64748B"

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

def _reference_figure(mass_kg: float = 0.0, show_force_colours: bool = False, title: str | None = None):
    points = {"A": (0.0, 0.0), "B": (2.0, 0.0), "C": (4.0, 0.0), "F": (0.0, 2.0), "E": (2.0, 2.0), "D": (4.0, 2.0)}
    pairs = [
        ("A", "F", "AF"), ("F", "E", "FE"), ("E", "D", "ED"), ("D", "C", "DC"),
        ("A", "B", "AB"), ("B", "C", "BC"), ("A", "E", "AE"), ("E", "C", "EC"), ("E", "B", "EB"),
    ]
    member_label_offsets = {
        "AF": (-0.24, 0.0), "FE": (0.0, 0.24), "ED": (0.0, 0.24), "DC": (0.24, 0.0),
        "AB": (0.0, -0.24), "BC": (0.0, -0.24), "AE": (-0.18, 0.22), "EC": (0.18, 0.22), "EB": (0.24, 0.0),
    }
    forces = core.theory(mass_kg)
    fig = Figure(figsize=(9.7, 5.0), dpi=160)
    ax = fig.subplots()
    for start_pt, end_pt, name in pairs:
        state_colour = _ui_member_colour(forces[name])
        colour = state_colour if show_force_colours else UI_COLORS["member"]
        ax.plot([points[start_pt][0], points[end_pt][0]], [points[start_pt][1], points[end_pt][1]], color=colour, linewidth=4, solid_capstyle="round", zorder=2)
        mx = (points[start_pt][0] + points[end_pt][0]) / 2
        my = (points[start_pt][1] + points[end_pt][1]) / 2
        ox, oy = member_label_offsets[name]
        label_colour = state_colour if show_force_colours else "#A62C63"
        ax.text(mx + ox, my + oy, name, fontsize=10, fontweight="bold", color=label_colour,
                bbox=dict(facecolor="white", edgecolor=label_colour, boxstyle="round,pad=0.18", alpha=0.96), zorder=8)
        if name in core.MEMBERS:
            ax.add_patch(Circle((mx, my), 0.16, facecolor="white", edgecolor=UI_COLORS["ring"], linewidth=3, zorder=4))
            ax.add_patch(Circle((mx, my), 0.052, facecolor="white", edgecolor=UI_COLORS["ring"], linewidth=1.8, zorder=5))
    offsets = {"A": (-0.20, -0.16), "B": (-0.05, -0.36), "C": (0.15, -0.16), "F": (-0.20, 0.20), "E": (-0.02, 0.28), "D": (0.15, 0.20)}
    joint_colours = {"A": "#7C3AED", "B": "#D97706", "C": "#0891B2", "D": "#2563EB", "E": "#16A34A", "F": "#DC2626"}
    for label, (x, y) in points.items():
        ax.scatter([x], [y], s=75, color=UI_COLORS["joint"], zorder=7)
        ox, oy = offsets[label]
        ax.text(x + ox, y + oy, label, fontsize=12, fontweight="bold", color=joint_colours[label],
                bbox=dict(facecolor="white", edgecolor=joint_colours[label], boxstyle="round,pad=0.16", alpha=0.96), zorder=9)
    add_supports(ax)
    if mass_kg > 0:
        ax.add_patch(FancyArrowPatch((2.0, -0.04), (2.0, -0.78), arrowstyle="-|>", mutation_scale=20, color=UI_COLORS["load"], linewidth=2.8))
        ax.text(2.20, -0.65, f"{mass_kg:g} kg ({mass_kg * 9.81:.1f} N)", fontsize=12, color="#991B1B",
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

def reference_diagram(mass=30):
    figure=_reference_figure(float(mass))
    output=io.BytesIO()
    figure.savefig(output,format="png",dpi=160)
    return output.getvalue()


SECTION_GUIDANCE = (
    ("Student details and practical pathway", "Enter the details from your JCU enrolment and select your practical pathway.", "Welcome to TrussLab", "A guided practical from setup to submission", "Follow the workflow and complete each section. Your 2027 entries and working photographs are saved together.", ("Analyse a pin-jointed truss", "Collect five member readings", "Show handwritten calculations", "Explain and report your results"), "enter your student details and select your practical pathway.", ("Save your full name, eight-digit student ID and practical group.", "Select the physical or simulated pathway confirmed by your lecturer.", "Add a short aim and procedure in the report-writing expander.")),
    ("Pre-lab preparation and member predictions", "Inspect the supports, central load and instrumented members before recording your predictions.", "Prepare before testing", "Read the truss and explain your predictions", "Use joint equilibrium and the load path to support your initial reasoning.", ("Identify both supports", "Convert mass to force", "Classify five members", "Give two brief reasons"), "complete the responses and record your prediction attempt.", ("Identify the support at A and at C and calculate the weight of 10 kg.", "Predict tension, compression or zero force for each instrumented member.", "Explain your zero-force and AE predictions, then record the attempt.")),
    ("Practical preparation and safety", "Prepare for the selected practical pathway and follow the demonstrator's instructions.", "Prepare to collect data", "Check the apparatus before applying a load", "Physical sessions require the laboratory safety acknowledgement before measurements can be recorded.", ("Receive the briefing", "Inspect the apparatus", "Follow the load limit", "Record the acknowledgement"), "complete the safety items for the physical pathway, or continue with the simulation.", ("Confirm your selected pathway in Student details.", "For a physical session, read and acknowledge every laboratory instruction.", "Follow the approved loading and emergency procedures.")),
    ("Apparatus and data collection", "Collect signed proving-ring dial readings using your physical or simulated pathway.", "Collect evidence", "Build a complete measurement record", "Record the initial zero, the three loaded cases and the final unloaded reading for each member.", ("Record the initial offset", "Apply 10, 20 and 30 kg", "Record five dial readings", "Check unloaded drift"), "record all 25 readings before moving to the calculation sections.", ("Follow the physical loading procedure or capture each simulated measurement.", "Use signed readings in mm; a recorded zero is different from a blank cell.", "Record the initial and final unloaded readings so zero correction and drift can be considered.")),
    ("Theoretical calculations", "Calculate reactions and selected member forces for the 30 kg load case.", "Apply equilibrium", "Solve the truss and show how you obtained each answer", "Use free-body diagrams, equations, units and a clear tension/compression interpretation.", ("Draw the whole truss", "Calculate support reactions", "Analyse joints A and B", "Upload H1 and H2 working"), "enter your final answers, upload your working and record the theoretical attempt.", ("Use g = 9.81 m/s² and show the external forces and support reactions.", "Justify the zero-force members and solve joints A and B.", "Upload legible H1 and H2 photographs and record your typed results.")),
    ("Experimental calculations", "Convert selected ring-dial readings to force before viewing the calculated comparison.", "Work from your readings", "Connect the measurements to member forces", "Show the initial zero correction and calibration conversion, then compare AE with your own theoretical result.", ("Correct the initial offset", "Calculate AE and AB", "Calculate AE discrepancy", "Upload H3 working"), "record your experimental calculation attempt to unlock the results comparison.", ("Subtract the initial unloaded reading from the loaded dial reading.", "Convert AE and AB to force using the supplied calibration factors.", "Calculate AE's percentage discrepancy and upload the handwritten H3 working.")),
    ("Results and explanations", "Interpret agreement, proportionality and data quality using your own measurements.", "Interpret the evidence", "Explain what your results show", "Use specific numerical comparisons and propose a check that could test your explanation.", ("Compare measured forces", "Inspect the load response", "Consider zero-force residuals", "Complete Q1, Q2 and Q3"), "complete the three short explanations using evidence from your tables and graph.", ("Review the calculated experimental values alongside your own theoretical answers.", "Use numbers to assess agreement and proportionality.", "Identify a data-quality limitation and propose a practical way to investigate it.")),
    ("Safe-load engineering challenge", "Compare the tensile and compressive capacity limits and defend the governing case.", "Make an engineering decision", "Calculate the capacity before exploring the model", "Separate the theoretical limiting mass, a permitted 0.1 kg increment and the approved physical test mass.", ("Derive both mass limits", "Identify the governing member", "Upload H4 working", "Explain your decision in Q4"), "record the capacity calculation attempt, then use the model to review your decision.", ("Derive the tensile and compressive limiting masses from equilibrium and the given allowables.", "Choose the lower limit and an operating increment that does not exceed it.", "Upload H4 working, record the attempt and complete Q4.")),
    ("Review and report submission", "Review the complete practical before generating the files for LearnJCU submission.", "Prepare your submission", "Bring your calculations and explanations together", "The generated report contains the answers, written responses and photographs recorded in the app.", ("Review all typed answers", "Check working photographs", "Complete the conclusion", "Download the submission files"), "resolve any missing items, review the declaration and generate the complete report.", ("Check that every required calculation, photograph and written response is present.", "Confirm that the typed results correspond to your uploaded working.", "Generate and review the PDF report, then submit the report and answer file as instructed.")),
)


def render_brand_header(root):
    logo=root/"assets"/"jcu_logo.png"
    logo_html=(f'<img src="data:image/png;base64,{base64.b64encode(logo.read_bytes()).decode()}" alt="James Cook University Australia">'
               if logo.exists() else '<strong>JCU</strong>')
    st.markdown(f'''<div class="app-header">
      <div class="header-logo">{logo_html}</div>
      <div class="app-header-title"><div class="kicker">EG1011 · Statics and Dynamics</div>
        <h1>TrussLab</h1><p>Guided plane-truss testing, member-force analysis and structured report preparation for physical or online completion.</p></div>
      <div class="app-header-meta"><div class="label">Practical</div><div class="title">Forces in a Plane Truss</div><span class="version">2027 practical</span></div>
      </div><div class="app-divider"></div>''',unsafe_allow_html=True)


def render_section_guidance(index):
    title,summary,eyebrow,headline,description,items,next_action,steps=SECTION_GUIDANCE[index]
    heading_col,help_col=st.columns([.86,.14],gap="small")
    with heading_col:
        st.markdown(f'<div class="page-heading"><div class="section-label">Section {index+1}</div><div class="section-title">{escape(title)}</div><div class="section-summary">{escape(summary)}</div></div>',unsafe_allow_html=True)
    with help_col:
        with st.popover("❓ Help"):
            st.markdown("#### What to do")
            for number,step in enumerate(steps,1):st.markdown(f"**{number}.** {step}")
            st.markdown('<div class="help-completion"><b>Before moving on</b><br>'+escape(next_action[0].upper()+next_action[1:])+'</div>',unsafe_allow_html=True)
    if index==0:
        item_html="".join(f'<div class="welcome-item"><span class="check">✓</span><span>{escape(item)}</span></div>' for item in items)
        st.markdown(f'<div class="welcome-dashboard"><div><div class="eyebrow">{escape(eyebrow)}</div><div class="title">{escape(headline)}</div><div class="text">{escape(description)}</div></div><div class="welcome-list">{item_html}<div class="welcome-time">✎ Handwritten working · Four short explanations</div></div></div><div class="welcome-next-step"><b>Start here:</b> {escape(next_action)}</div>',unsafe_allow_html=True)
    else:
        item_html="".join(f'<div class="dashboard-item"><span class="check">✓</span><span>{escape(item)}</span></div>' for item in items)
        st.markdown(f'<div class="section-dashboard"><div><div class="eyebrow">{escape(eyebrow)}</div><div class="title">{escape(headline)}</div><div class="description">{escape(description)}</div></div><div class="dashboard-list">{item_html}<div class="dashboard-meta"><span class="meta-pill">2027 practical</span><span class="meta-pill">Step {index+1} of 9</span></div></div></div><div class="section-next-action"><b>Next:</b> {escape(next_action)}</div>',unsafe_allow_html=True)


def stage_completion(current):
    return [core.identity_complete(current),core.recorded(current,"predictions"),core.safety_complete(current),core.readings_complete(current),
            core.recorded(current,"theory"),core.recorded(current,"experimental"),all(current["explanations"][key].strip() for key in ("Q1","Q2","Q3")),
            core.recorded(current,"capacity") and bool(current["explanations"]["Q4"].strip()),not core.validation_issues(current)]


LOCAL_PROGRESS_HTML = r'''<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;height:0;overflow:hidden"><script>
// Runs locally in the component iframe. No external scripts or services.
(() => {
  const DB = "TrussLab2027LocalProgress", STORE = "progress";
  const draftPrefix = "TrussLab2027:pending:";
  let database, active, lastReply = "", chain = Promise.resolve(), parentDocument;
  function message(type, extra = {}) {
    window.parent.postMessage({isStreamlitMessage:true, type, ...extra}, "*");
  }
  function reply(value) {
    const key = JSON.stringify(value);
    if (key !== lastReply) {
      lastReply = key;
      message("streamlit:setComponentValue", {value, dataType:"json"});
    }
  }
  function db() {
    if (!database) database = new Promise((resolve,reject) => {
      const request = indexedDB.open(DB, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE, {keyPath:"key"});
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || Error("Local storage unavailable"));
      request.onblocked = () => reject(Error("Local storage is blocked"));
    });
    return database;
  }
  async function read(key) {
    const database = await db();
    return new Promise((resolve,reject) => {
      const tx=database.transaction(STORE,"readonly"), request=tx.objectStore(STORE).get(key);
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(request.error);
    });
  }
  async function write(records) {
    const database = await db();
    return new Promise((resolve,reject) => {
      const tx=database.transaction(STORE,"readwrite");
      for (const record of records) tx.objectStore(STORE).put(record);
      tx.oncomplete=()=>resolve();
      tx.onerror=()=>reject(tx.error || Error("Could not save locally"));
      tx.onabort=()=>reject(tx.error || Error("Local save was interrupted"));
    });
  }
  function draft(token) {
    try {return JSON.parse(localStorage.getItem(draftPrefix+token) || '{"fields":{}}');}
    catch {return {fields:{}};}
  }
  function storeDraft(token,value) {
    try {
      if (Object.keys(value.fields).length) localStorage.setItem(draftPrefix+token,JSON.stringify(value));
      else localStorage.removeItem(draftPrefix+token);
    } catch { /* Full IndexedDB/server saving still operates. */ }
  }
  function get(object,path) {return path.reduce((value,key)=>value == null ? undefined : value[key],object);}
  function put(object,path,value) {
    const parent=path.slice(0,-1).reduce((value,key)=>value && value[key],object);
    if (parent && Object.prototype.hasOwnProperty.call(parent,path[path.length-1])) parent[path[path.length-1]]=value;
  }
  function equal(a,b) {return a===b || (typeof a==="string" && typeof b==="string" && a.trim()===b.trim());}
  function capture(event) {
    if (!active || !event.target || !event.target.closest) return;
    const owner=event.target.closest('[class*="st-key-_tl27_"]');
    if (!owner) return;
    const key=Array.from(owner.classList).find(key=>key.startsWith("st-key-_tl27_"));
    const binding=active.bindings[key && key.slice(7)];
    if (!binding) return; // Never capture passwords, staff notes or unrelated fields.
    let value=event.target.value;
    if (typeof value!=="string") return;
    if (binding.kind==="number") {
      value=value.trim()==="" ? null : Number(value);
      if (value!==null && !Number.isFinite(value)) return;
    } else value=value.slice(0,binding.path[0]==="student" ? 200 : 3000);
    const pending=draft(active.token);
    pending.fields[binding.path.join(".")]={path:binding.path,value};
    pending.edited_at=Date.now();
    storeDraft(active.token,pending);
  }
  try {
    parentDocument=window.parent.document;
    parentDocument.addEventListener("input",capture,true);
    window.addEventListener("unload",()=>parentDocument.removeEventListener("input",capture,true));
  } catch { /* Committed fields still save through the component protocol. */ }
  async function sync(a) {
    active=a;
    const identity=/^\d{8}$/.test(a.student_id) ? "student:"+a.student_id : "";
    const sessionKey="session:"+a.token;
    const record=(identity && await read(identity)) || await read(sessionKey);
    const pending=draft(a.token);
    for (const [key,field] of Object.entries(pending.fields)) {
      if (equal(get(a.payload,field.path),field.value)) delete pending.fields[key];
    }
    storeDraft(a.token,pending);
    const canRestore=a.policy!=="sync";
    const sameIdentity=record && (record.payload.student.id===a.student_id || (!a.student_id && record.token===a.token));
    const preferred=canRestore && sameIdentity &&
      (a.policy==="lookup" || a.policy==="recover" || record.revision>a.revision);
    let restored=preferred ? JSON.parse(JSON.stringify(record.payload)) : JSON.parse(JSON.stringify(a.payload));
    let changed=preferred && record.hash!==a.hash, candidateId="", identityFromDraft=false;
    if (canRestore) for (const field of Object.values(pending.fields)) {
      if (field.path.join(".")==="student.id") {
        if (!/^\d{8}$/.test(String(field.value)) || (restored.student.id && restored.student.id!==field.value)) {
          candidateId=String(field.value); continue;
        }
        if (!restored.student.id) identityFromDraft=true;
      }
      if (!equal(get(restored,field.path),field.value)) {put(restored,field.path,field.value);changed=true;}
    }
    if (canRestore && (changed || candidateId)) {
      reply({action:"restore",request_id:a.request_id,base_hash:a.hash,
        payload:restored,token:preferred ? record.token : a.token,
        revision:Math.max(a.revision,preferred ? record.revision : 0)+1,
        section:preferred ? record.section : a.section,candidate_id:candidateId,identity_from_draft:identityFromDraft});
      return; // Never overwrite the recoverable record with a blank first render.
    }
    const saved={payload:a.payload,token:a.token,revision:a.revision,section:a.section,hash:a.hash};
    const records=[{key:sessionKey,...saved}];
    if (identity) records.push({key:identity,...saved});
    await write(records);
    reply({action:"saved",request_id:a.request_id,base_hash:a.hash,revision:a.revision});
  }
  window.addEventListener("message",event=>{
    if (event.source!==window.parent || !event.data || event.data.type!=="streamlit:render") return;
    const args=event.data.args;
    if (!args || args.schema!=="trusslab-browser-progress-v1") return;
    chain=chain.then(()=>sync(args)).catch(error=>reply({action:"unavailable",request_id:args.request_id,base_hash:args.hash,message:String(error)}));
  });
  message("streamlit:componentReady",{apiVersion:1});
  message("streamlit:setFrameHeight",{height:0});
})();
</script></body></html>'''


def _progress_meta_path(root,token):
    if not re.fullmatch(r"[a-f0-9]{48}",token):raise ValueError("Invalid private resume key")
    return Path(root)/"student_saves"/"2027"/(token+".state.json")


def _set_browser_request(policy):
    st.session_state["_tl27_browser_request"]={"id":core.new_token(),"policy":policy}
    st.session_state["_tl27_browser_status"]="pending"
    st.session_state.pop("_tl27_browser_ack_hash",None)


def _save_current_progress(root):
    current=model();token=st.session_state["_tl27_token"]
    section=st.session_state.get("_tl27_navigation",SECTIONS[0])
    state_hash=core.digest({"model":current,"section":section})
    if st.session_state.get("_tl27_saved_state_hash")!=state_hash:
        revision=max(time.time_ns()//1_000_000,st.session_state.get("_tl27_revision",0)+1)
        core.save_progress(root,token,current)
        meta={"revision":revision,"section":section,"model_hash":core.digest(current)}
        target=_progress_meta_path(root,token)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=target.parent,suffix=".tmp",delete=False) as stream:
                temporary=Path(stream.name);json.dump(meta,stream)
            temporary.replace(target)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
        st.session_state["_tl27_revision"]=revision
        st.session_state["_tl27_saved_state_hash"]=state_hash


def _apply_browser_restore():
    pending=st.session_state.pop("_tl27_pending_browser_restore",None)
    if not pending:return
    restored=core.validate_model(pending["payload"])
    st.session_state["_tl27_model"]=restored
    token=pending.get("token","")
    st.session_state["_tl27_token"]=token if re.fullmatch(r"[a-f0-9]{48}",token) else core.new_token()
    st.session_state["_tl27_revision"]=int(pending.get("revision",0))
    clear_widgets()
    section=pending.get("section",SECTIONS[0])
    st.session_state["_tl27_navigation"]=section if section in SECTIONS else SECTIONS[0]
    candidate=pending.get("candidate_id","")
    if candidate:
        st.session_state["_tl27_identity_id"]=candidate
    st.session_state.pop("_tl27_saved_state_hash",None)
    st.session_state.pop("_tl27_details_error",None)
    st.session_state["_tl27_restored_notice"]=True
    st.query_params["work"]=st.session_state["_tl27_token"]
    if re.fullmatch(r"\d{8}",candidate) and candidate!=restored["student"]["id"]:
        # A refresh during an ID edit must not attach the previous student's
        # calculations to the newly typed number.
        _save_current_progress(Path(st.session_state["_tl27_root"]))
        fresh=core.fresh_model(restored["settings"])
        fresh["student"]["id"]=candidate
        st.session_state["_tl27_model"]=fresh
        st.session_state["_tl27_token"]=core.new_token()
        st.session_state["_tl27_navigation"]=SECTIONS[0]
        st.session_state.pop("_tl27_saved_state_hash",None)
        st.query_params["work"]=st.session_state["_tl27_token"]
        _set_browser_request("lookup")
    else:_set_browser_request("lookup" if pending.get("identity_from_draft") else "sync")


def initialise(root):
    st.session_state["_tl27_root"]=str(root)
    if "_tl27_model" not in st.session_state:
        settings,warnings=core.load_settings(root)
        token=st.query_params.get("work","")
        try:saved=core.load_progress(root,token) if token else None
        except (ValueError,OSError,TypeError,KeyError):saved=None
        if saved is None:
            token=core.new_token();saved=core.fresh_model(settings)
        st.session_state["_tl27_model"]=saved
        st.session_state["_tl27_token"]=token
        st.session_state["_tl27_warnings"]=warnings
        st.session_state["_tl27_had_server_progress"]=bool(saved["student"]["id"])
    if "_tl27_revision" not in st.session_state:
        token=st.session_state["_tl27_token"]
        current=st.session_state["_tl27_model"]
        try:
            meta=json.loads(_progress_meta_path(root,token).read_text())
            if meta.get("model_hash")!=core.digest(current):raise ValueError("Changed progress")
            st.session_state["_tl27_revision"]=int(meta["revision"])
            if meta.get("section") in SECTIONS:st.session_state.setdefault("_tl27_navigation",meta["section"])
            st.session_state["_tl27_saved_state_hash"]=core.digest({"model":current,"section":meta["section"]})
        except (OSError,ValueError,TypeError,KeyError):
            path=Path(root)/"student_saves"/"2027"/(token+".json")
            st.session_state["_tl27_revision"]=int(path.stat().st_mtime*1000) if path.exists() else 0
        _set_browser_request("latest" if current["student"]["id"] else "recover")
    _apply_browser_restore()
    st.query_params["work"]=st.session_state["_tl27_token"]


def preserve_student_widgets():
    for key in list(st.session_state):
        if key.startswith(("_tl27_input_","_tl27_identity_","_tl27_predict_")) or key in ("_tl27_navigation","_tl27_declaration","_tl27_online_stage","_tl27_capacity_slider"):
            st.session_state[key]=st.session_state[key]


def browser_progress(root):
    import streamlit.components.v1 as components
    folder=Path(root)/"student_saves"/"2027"/"_local_progress_component"
    folder.mkdir(parents=True,exist_ok=True)
    index=folder/"index.html"
    if not index.exists() or index.read_text(encoding="utf-8")!=LOCAL_PROGRESS_HTML:
        index.write_text(LOCAL_PROGRESS_HTML,encoding="utf-8")
    component=components.declare_component("trusslab_2027_local_progress",path=str(folder.resolve()))
    current=model();model_hash=core.digest(current)
    request=st.session_state["_tl27_browser_request"]
    bindings={}
    for section in ("theory","experimental","capacity","explanations","prelab"):
        for key,value in current[section].items():
            if key=="predictions" or isinstance(value,(dict,list)):continue
            kind="text" if isinstance(value,str) or (section in ("explanations","prelab") and key!="weight10") else "number"
            bindings[f"_tl27_input_{section}_{key}"]={"path":[section,key],"kind":kind}
    for key in ("name","id","group"):
        bindings[f"_tl27_identity_{key}"]={"path":["student",key],"kind":"text"}
    response=component(schema="trusslab-browser-progress-v1",payload=current,hash=model_hash,
        student_id=current["student"]["id"],token=st.session_state["_tl27_token"],
        revision=st.session_state["_tl27_revision"],section=st.session_state.get("_tl27_navigation",SECTIONS[0]),
        request_id=request["id"],policy=request["policy"],bindings=bindings,
        key="_tl27_browser_storage",default=None)
    if not isinstance(response,dict) or response.get("request_id")!=request["id"] or response.get("base_hash")!=model_hash:return
    action=response.get("action")
    if action=="restore":
        restored=core.validate_model(response["payload"])
        if current["student"]["id"] and restored["student"]["id"]!=current["student"]["id"]:
            return
        st.session_state["_tl27_pending_browser_restore"]=response
        st.rerun()
    elif action=="saved":
        st.session_state["_tl27_browser_status"]="saved"
        st.session_state["_tl27_browser_ack_hash"]=model_hash
        request["policy"]="sync"
    elif action=="unavailable":
        st.session_state["_tl27_browser_status"]="unavailable"


def model():return st.session_state["_tl27_model"]


def _persist_soon():
    try:_save_current_progress(Path(st.session_state["_tl27_root"]))
    except (OSError,ValueError,TypeError):pass


def sync(section,key,widget):
    model()[section][key]=st.session_state[widget]
    _persist_soon()


def identity_text_changed(key):
    model()["student"][key]=st.session_state[f"_tl27_identity_{key}"].strip()
    _persist_soon()


def identity_id_changed():
    sid=st.session_state["_tl27_identity_id"].strip()
    if not re.fullmatch(r"\d{8}",sid):
        st.session_state["_tl27_details_error"]="Enter the full eight-digit JCU student ID. Your existing saved work has been kept."
        return
    st.session_state.pop("_tl27_details_error",None)
    current=model()
    if sid!=current["student"]["id"]:
        if current["student"]["id"]:
            _persist_soon()
            st.session_state["_tl27_model"]=core.fresh_model(current["settings"])
            st.session_state["_tl27_token"]=core.new_token()
            clear_widgets()
            st.session_state["_tl27_identity_id"]=sid
        model()["student"]["id"]=sid
        st.session_state.pop("_tl27_saved_state_hash",None)
        _set_browser_request("lookup")
        st.query_params["work"]=st.session_state["_tl27_token"]
    _persist_soon()


def identity_mode_changed():
    new=st.session_state["_tl27_identity_mode"]
    current=model();old=current["student"]["mode"]
    if new not in (core.PHYSICAL,core.ONLINE):return
    if old and new!=old:
        if not st.session_state.get("_tl27_restart_mode",False):
            st.session_state["_tl27_identity_mode"]=old
            st.session_state["_tl27_details_error"]="To change an existing pathway, tick the fresh-start option first. Existing readings and calculations have been kept."
            return
        _persist_soon()
        student=dict(current["student"])
        st.session_state["_tl27_model"]=core.fresh_model(current["settings"])
        model()["student"]=student
        st.session_state["_tl27_token"]=core.new_token()
        clear_widgets()
        st.session_state["_tl27_identity_mode"]=new
        st.session_state.pop("_tl27_saved_state_hash",None)
        _set_browser_request("sync")
        st.query_params["work"]=st.session_state["_tl27_token"]
    model()["student"]["mode"]=new
    st.session_state.pop("_tl27_details_error",None)
    _persist_soon()


def number(section,key,label,minimum=None,step=.01):
    widget=f"_tl27_input_{section}_{key}"
    st.session_state.setdefault(widget,model()[section].get(key))
    st.number_input(label,min_value=minimum,value=None,step=step,format="%.3f",
                    key=widget,on_change=sync,args=(section,key,widget))


def text(section,key,label,height=120,help=None):
    widget=f"_tl27_input_{section}_{key}"
    st.session_state.setdefault(widget,model()[section].get(key,""))
    st.text_area(label,height=height,max_chars=3000,key=widget,on_change=sync,
                 args=(section,key,widget),help=help)
    words=len(model()[section].get(key,"").split())
    if key in core.QUESTIONS:st.caption(f"{words} words · aim for about 50–80 words, with numerical evidence.")


def choice(section,key,label,options):
    widget=f"_tl27_input_{section}_{key}"
    current=model()[section].get(key)
    st.session_state.setdefault(widget,current if current in options else None)
    st.selectbox(label,options,index=None,placeholder="Select a response…",key=widget,on_change=sync,args=(section,key,widget))


def checkbox(section,key,label):
    widget=f"_tl27_input_{section}_{key}"
    st.session_state.setdefault(widget,model()[section].get(key,False))
    st.checkbox(label,key=widget,on_change=sync,args=(section,key,widget))


def upload_working(key):
    st.markdown(f"**{key} · {core.EVIDENCE_TITLES[key]}**")
    st.caption("JPG/JPEG or PNG · up to 3 images per task · maximum 10 MB and 30 megapixels per image.")
    with st.expander("Image upload instructions"):
        st.markdown("""
- Photograph one sheet at a time, in the order you want it to appear. Use up to three images for each H task.
- Crop out the desk and empty borders, while keeping every equation, unit and diagram. Use dark writing, even lighting and a steady camera held directly above the page.
- For a full handwritten page, aim for at least **1500 pixels on the long edge**. Check that small subscripts and numbers are readable before uploading.
- Upload **JPG/JPEG or PNG**, at most **10 MB and 30 megapixels per image**. Export HEIC or PDF files as JPG/PNG first. Resize or compress files above these limits.
- The app corrects phone orientation when rotation information is present, reduces large accepted photos and compresses the saved copy. Transparent backgrounds become white.
- In the PDF and Word reports, each photo is **centred and fitted inside the page margins**, with its proportions preserved and no automatic cropping. It moves to the next page when needed, together with its caption.
- A small image may trigger a warning. Enlarging it cannot restore missing detail: retake a blurry photo or use two or three closer photographs of the working.
- Open the saved-photo preview, then check the generated report at **100% zoom** before submitting. Check the processed copy as well as the original.
""")
    generation=st.session_state.get(f"_tl27_upload_generation_{key}",0)
    widget=f"_tl27_upload_{key}_{generation}"
    # Keep compatibility with Streamlit 1.50 while using its per-widget limit
    # on newer installations. Core validation enforces 10 MB on every version.
    upload_options={"max_upload_size":10} if "max_upload_size" in inspect.signature(st.file_uploader).parameters else {}
    uploads=st.file_uploader("Add or replace working photographs",type=["jpg","jpeg","png"],accept_multiple_files=True,
                             key=widget,help="Up to three JPG/PNG images per task, at most 10 MB and 30 megapixels each. Photos are centred and fitted in the report without cropping. Check the saved preview for readable handwriting.",**upload_options)
    if uploads:
        try:
            if len(uploads)>3:raise ValueError("Use at most three photographs per task")
            upload_hash=core.digest([hashlib.sha256(f.getvalue()).hexdigest() for f in uploads])
            cache=f"_tl27_uploaded_hash_{key}"
            if st.session_state.get(cache)!=upload_hash:
                converted=[]
                for file in uploads:
                    try:converted.append(core.normalise_image(file.getvalue(),file.name))
                    except ValueError as exc:raise ValueError(f"{file.name}: {exc}") from exc
                model()["evidence"][key]=converted
                st.session_state[cache]=upload_hash
        except Exception as exc:
            st.error(f"Photographs were not replaced: {exc}")
    if model()["evidence"][key]:
        st.caption(f"{len(model()['evidence'][key])} photograph(s) saved with this practical.")
        for item in model()["evidence"][key]:
            width,height=core.image_dimensions(item)
            if max(width,height)<core.LOW_RESOLUTION_EDGE:
                st.warning(f"{item['name']}: low resolution ({width} × {height} pixels). The photo is saved, but it may look blurry when enlarged in the report. Retake it at a higher resolution if any handwriting is unclear.")
            if max(width,height)>3.5*min(width,height):
                st.warning(f"{item['name']}: unusually tall or wide image ({width} × {height} pixels). It will shrink to fit the report page. Check readability; crop unused borders or split long working across up to three photographs.")
        with st.expander(f"Review saved {key} photographs"):
            for item in model()["evidence"][key]:
                width,height=core.image_dimensions(item)
                st.image(core.evidence_bytes(item),caption=f"{item['name']} · saved copy {width} × {height} pixels",width="stretch")
        if st.button(f"Remove saved {key} photographs",key=f"_tl27_remove_{key}"):
            model()["evidence"][key]=[]
            st.session_state.pop(f"_tl27_uploaded_hash_{key}",None)
            st.session_state[f"_tl27_upload_generation_{key}"]=generation+1
            st.rerun()
    else:st.caption("A working photograph is required before recording this calculation attempt.")


def gate(require_readings=False):
    m=model()
    if not core.identity_complete(m):st.info("Complete Section 1 before continuing.");return False
    if not core.predictions_complete(m) or not core.recorded(m,"predictions"):
        st.info("Record the pre-lab responses and predictions in Section 2 before collecting data or calculating results.");return False
    if not core.safety_complete(m):st.info("Complete the physical safety acknowledgement in Section 3 before proceeding.");return False
    if require_readings and not core.readings_complete(m):st.info("Complete all measurements in Section 4 before continuing.");return False
    return True


def record_button(scope,complete,label):
    if st.button(label,type="primary",disabled=not complete,key=f"_tl27_record_{scope}"):
        core.record_attempt(model(),scope)
    if core.recorded(model(),scope):st.success("Your current attempt is recorded. This confirms completion, not correctness.")
    elif not complete:st.caption("Complete the required responses and working photographs to record this attempt.")
    else:st.info("Record this attempt after reviewing the entries. Changes require the attempt to be recorded again.")


def page_details(root):
    m=model();s=m["student"]
    left,right=st.columns([2.2,1],gap="large")
    with left:
        st.markdown('<div class="student-form-intro"><div class="title">Your details</div><div class="text">Enter the details from your JCU enrolment.</div></div>',unsafe_allow_html=True)
        for key in ("name","id","group","mode"):
            st.session_state.setdefault(f"_tl27_identity_{key}",s[key] or (None if key=="mode" else ""))
        st.text_input("Full name",max_chars=120,key="_tl27_identity_name",on_change=identity_text_changed,args=("name",))
        st.text_input("JCU student ID (8 digits)",max_chars=8,key="_tl27_identity_id",on_change=identity_id_changed,
                      help="Use your official student ID. Work saved on this browser for that ID is restored automatically.")
        st.text_input("Practical/tutorial group",max_chars=120,key="_tl27_identity_group",on_change=identity_text_changed,args=("group",))
        st.checkbox("Start fresh calculations and readings if I change an existing pathway",key="_tl27_restart_mode")
        st.selectbox("Practical pathway",[core.PHYSICAL,core.ONLINE],index=None,key="_tl27_identity_mode",
                     placeholder="Choose the pathway confirmed by your lecturer",on_change=identity_mode_changed)
        if st.button("Save student details",type="primary",key="_tl27_check_details"):
            if core.identity_complete(model()):st.success("Student details saved. Continue to Section 2.")
            else:st.error("Enter your name, eight-digit JCU ID, group and pathway.")
        st.caption("Your entries are saved automatically as you work; pressing Save is optional.")
        if st.session_state.get("_tl27_details_error"):st.error(st.session_state["_tl27_details_error"])
        selected=model()["student"]["mode"]
        if selected:
            st.markdown(f'<div class="mode-summary"><b>{escape(selected)}</b><br>'+('Attend the scheduled session, complete the safety acknowledgement and enter the apparatus readings.' if selected==core.PHYSICAL else 'The app creates reproducible 2027 simulated readings from your official JCU student ID.')+'</div>',unsafe_allow_html=True)
        else:
            st.markdown('<div class="mode-summary"><b>Select a pathway</b><br>Choose the option confirmed by your lecturer or demonstrator before continuing.</div>',unsafe_allow_html=True)
        st.markdown('<div class="submission-summary"><b>What you submit</b><br>Your completed report includes recorded measurements, typed numerical answers, handwritten calculation photographs and short explanations. Review the generated PDF and submit through LearnJCU as instructed.</div>',unsafe_allow_html=True)
        with st.expander("Aim and procedure for your report"):
            text("explanations","aim","Aim: what will you investigate?",height=90,help="Two or three sentences are sufficient.")
            text("explanations","method","Procedure: summarise what you actually did",height=110,help="Describe the selected physical or simulated pathway and how the readings were obtained.")
    with right:
        with st.container(border=True):
            st.markdown('<div class="apparatus-soft-note">Identify the supports, central load and five instrumented members.</div><div class="apparatus-topline"><div><div class="apparatus-title">Plane-truss apparatus</div><div class="apparatus-caption">A central load is applied at joint B while five proving-ring members provide signed dial readings.</div></div><div class="apparatus-badges"><span class="apparatus-badge">Pin at A</span><span class="apparatus-badge">Roller at C</span><span class="apparatus-badge">5 gauges</span></div></div>',unsafe_allow_html=True)
            st.image(reference_diagram(),width="stretch")
            st.markdown('<div class="apparatus-legend"><span><span class="legend-dot" style="background:#A62C63"></span>Instrumented member</span><span><span class="legend-dot" style="background:#C62828"></span>Applied load</span><span><span class="legend-dot" style="background:#334155"></span>Truss member</span></div>',unsafe_allow_html=True)
            with st.expander("Apparatus details and practical workflow"):
                st.write("Loads of 10, 20 and 30 kg are applied at joint B. AF, FE, AE, AB and EB contain the five proving-ring gauges. The two equal bays and diagonals at 45° define the calculation geometry.")
                st.write("Complete predictions, collect measurements, show your handwritten working, explain the results and generate your complete report. Include diagrams, equations, substitutions, units and sign interpretations in the uploaded working.")
    with st.expander("Restore a downloaded 2027 progress backup"):
        backup=st.file_uploader("2027 progress JSON",type=["json"],key="_tl27_restore")
        if st.button("Restore progress",disabled=backup is None,key="_tl27_restore_button"):
            try:
                restored=core.parse_progress(backup.getvalue())
                st.session_state["_tl27_model"]=restored
                clear_widgets()
                st.session_state.pop("_tl27_saved_state_hash",None)
                _set_browser_request("sync")
                st.rerun()
            except Exception as exc:st.error(f"Could not restore progress: {exc}")


def clear_widgets():
    for key in list(st.session_state):
        if key.startswith(("_tl27_input_","_tl27_identity_","_tl27_upload_","_tl27_uploaded_hash_","_tl27_editor","_tl27_predict_")):
            del st.session_state[key]
    st.session_state.pop("_tl27_restart_mode",None)
    st.session_state.pop("_tl27_declaration",None)
    st.session_state.pop("_tl27_bundle",None)
    st.session_state.pop("_tl27_bundle_signature",None)


def page_predictions(root):
    if not core.identity_complete(model()):st.info("Save your student details in Section 1 first.");return
    st.subheader("Predict before measuring")
    st.caption("Give your initial reasoning. Later corrections are part of learning; recording an attempt is not an authorship check.")
    left,right=st.columns(2)
    with left:
        choice("prelab","support_a","Support at A",["Pin support","Roller support","Fixed support"])
        choice("prelab","support_c","Support at C",["Pin support","Roller support","Fixed support"])
        number("prelab","weight10","Weight produced by 10 kg (N)",minimum=0.)
        for member in core.MEMBERS:
            widget=f"_tl27_predict_{member}"
            st.session_state.setdefault(widget,model()["prelab"]["predictions"][member])
            def store_prediction(member=member,widget=widget):model()["prelab"]["predictions"][member]=st.session_state[widget]
            st.selectbox(f"Predicted state of {member}",core.STATES,index=None,key=widget,on_change=store_prediction)
    with right:
        st.image(reference_diagram(),width="stretch")
        text("prelab","reason_zero","Identify a zero-force member and explain the joint rule that supports your prediction.")
        text("prelab","reason_ae","Explain your prediction for AE using the load path or joint equilibrium.")
    record_button("predictions",core.predictions_complete(model()),"Record pre-lab responses and predictions")


def page_safety(root):
    m=model()
    if not core.identity_complete(m):st.info("Select your pathway in Section 1 first.");return
    st.subheader("Practical preparation and safety")
    if m["student"]["mode"]==core.ONLINE:
        st.info("You are using the simulated pathway. The physical apparatus acknowledgement is not required. Continue to Data collection.")
        return
    limit=m["settings"]["approved_mass"]
    st.markdown("Follow the demonstrator's briefing and the laboratory's approved procedures. Stop and ask for assistance if the equipment or loading appears unsafe.")
    for key,label in (
        ("briefing","I am attending the physical session and have received the demonstrator's briefing."),
        ("ppe","I have the required footwear/clothing and have secured loose items."),
        ("inspection","The apparatus, supports, gauges and load hanger have been checked with the demonstrator."),
        ("loading",f"I will load and unload under supervision, keep hands clear and never exceed the approved {limit:g} kg physical load."),
        ("emergency","I know how to stop the activity and report an issue or emergency."),
        ("confirmed","I confirm that I understand the physical laboratory instructions.")):
        checkbox("safety",key,label)
    if core.safety_complete(m):st.success("Safety acknowledgement complete.")


def readings_frame():
    return pd.DataFrame([{"Member":m,**model()["readings"][m]} for m in core.MEMBERS])


def editor_changed():
    base=st.session_state["_tl27_editor_base"].copy(deep=True)
    edits=st.session_state.get("_tl27_editor",{}).get("edited_rows",{})
    for row,changes in edits.items():
        for key,value in changes.items():
            if key in core.READING_KEYS:base.at[int(row),key]=value
    for _,row in base.iterrows():
        model()["readings"][row["Member"]]={key:None if pd.isna(row[key]) else float(row[key]) for key in core.READING_KEYS}


def page_data(root):
    if not gate():return
    m=model()
    st.subheader("Record the proving-ring dial readings")
    st.markdown("Record the initial unloaded reading, then 10, 20 and 30 kg readings, and finally the unloaded reading after the test. Use signed mm: positive for tension, negative for compression. The gauges measure proving-ring response.")
    if m["student"]["mode"]==core.PHYSICAL:
        if m["settings"]["approved_mass"]<30:
            st.error("The configured approved mass is below the required 30 kg case. Ask the lecturer to resolve the practical settings; do not apply 30 kg.");return
        st.info(f"Zero the gauges as instructed, then record any remaining initial offset. Never exceed the approved {m['settings']['approved_mass']:g} kg physical load.")
        if "_tl27_editor" not in st.session_state:
            st.session_state["_tl27_editor_base"]=readings_frame()
        st.data_editor(st.session_state["_tl27_editor_base"],hide_index=True,num_rows="fixed",disabled=["Member"],width="stretch",
            column_config={"start":st.column_config.NumberColumn("Initial 0 kg",format="%.3f",step=.001),
                           **{str(k):st.column_config.NumberColumn(f"{k} kg",format="%.3f",step=.001) for k in core.LOADS},
                           "return":st.column_config.NumberColumn("Final 0 kg",format="%.3f",step=.001)},
            key="_tl27_editor",on_change=editor_changed)
        st.caption("Press Enter or Tab to commit an edited cell. A blank cell is missing; 0.000 is a recorded zero.")
    else:
        generated=core.simulation(m["student"]["id"],m["settings"])
        options=["Initial 0 kg","10 kg","20 kg","30 kg","Final 0 kg"]
        stage=st.select_slider("Simulated measurement",options=options,key="_tl27_online_stage")
        key=core.READING_KEYS[options.index(stage)]
        st.dataframe(pd.DataFrame({"Member":core.MEMBERS,"Raw dial (mm)":[generated[member][key] for member in core.MEMBERS]}),hide_index=True,width="stretch")
        can_record=(key=="start" or "start" in m["captured"]) and (key!="return" or all(str(k) in m["captured"] for k in core.LOADS))
        if st.button(f"Record {stage}",type="primary",disabled=not can_record,key="_tl27_capture"):
            for member in core.MEMBERS:m["readings"][member][key]=generated[member][key]
            if key not in m["captured"]:m["captured"].append(key)
            st.success(f"Recorded {stage}.")
        st.caption("Record the initial unloaded case first and the final unloaded case after all three loaded cases. The same ID produces the same 2027 simulation.")
        st.dataframe(readings_frame().rename(columns={"start":"Initial 0 kg","return":"Final 0 kg"}),hide_index=True,width="stretch")
    count=sum(core.finite(m["readings"][member][key]) for member in core.MEMBERS for key in core.READING_KEYS)
    st.caption(f"{count} / 25 readings recorded.")
    if core.readings_complete(m):st.success("All measurements recorded. Continue to Theoretical calculations.")
    with st.expander("Calibration factors and zero correction"):
        st.dataframe(pd.DataFrame({"Member":core.MEMBERS,"Calibration (N/mm)":[m["settings"]["calibration"][member] for member in core.MEMBERS]}),hide_index=True)
        st.write("Use F = k × (loaded reading − initial unloaded reading). The final unloaded reading is an observation of drift; it is not used as a replacement initial reference.")
        for warning in st.session_state["_tl27_warnings"]:st.caption(warning)


def page_theory(root):
    if not gate(require_readings=True):return
    st.subheader("Calculate the 30 kg case")
    st.markdown("Use g = 9.81 m/s². Draw the whole-truss free-body diagram, solve the support reactions, justify the zero-force members and analyse joints A and B. Assume member forces act in tension when drawing each joint; interpret a negative answer as compression.")
    left,right=st.columns([1,1.15])
    with left:
        for key,label in core.THEORY_LABELS.items():number("theory",key,label)
        st.caption("Type the final answers from your handwritten work. The app records the answers without marking them.")
    with right:
        st.image(reference_diagram(),width="stretch")
        upload_working("H1")
        upload_working("H2")
    record_button("theory",core.theory_complete(model()),"Record theoretical calculation attempt")


def page_experimental(root):
    if not gate(require_readings=True):return
    m=model()
    if not core.recorded(m,"theory"):st.info("Record your theoretical calculation attempt in Section 5 first.");return
    st.subheader("Calculate before viewing the comparison table")
    st.markdown("On paper, convert the corrected 30 kg readings for AE and AB into force. Then calculate the percentage discrepancy for AE using your own theoretical AE value from Section 5. Show units, sign and substitutions.")
    data=[]
    for member in ("AE","AB"):
        r=m["readings"][member]
        data.append({"Member":member,"Initial (mm)":r["start"],"30 kg (mm)":r["30"],"Calibration (N/mm)":m["settings"]["calibration"][member]})
    st.dataframe(pd.DataFrame(data),hide_index=True,width="stretch")
    st.latex(r"F = k\,(D_{30}-D_0),\qquad \text{discrepancy} = \frac{|F_{\rm exp}-F_{\rm theory}|}{|F_{\rm theory}|}\,100\%")
    st.caption("For a theoretical zero, quote an absolute residual in N rather than a percentage.")
    left,right=st.columns(2)
    with left:
        for key,label in core.EXPERIMENTAL_LABELS.items():number("experimental",key,label)
    with right:upload_working("H3")
    record_button("experimental",core.experimental_complete(m),"Record experimental calculation attempt")


def page_results(root):
    if not gate(require_readings=True):return
    m=model()
    if not core.recorded(m,"theory") or not core.recorded(m,"experimental"):
        st.info("Record your theoretical and experimental calculations with H1–H3 working before viewing the calculated comparison.");return
    st.subheader("Interpret your measurements")
    st.dataframe(pd.DataFrame(core.comparison_rows(m)),hide_index=True,width="stretch")
    st.caption("Experimental forces are calculated from your recorded measurements. The theoretical column uses your answers, not a lecturer solution. Large differences are evidence to investigate, not a reason to alter readings.")
    st.image(readings_plot_png(m),width="stretch")
    with st.expander("Unloaded drift observations"):
        st.dataframe(pd.DataFrame([{"Member":member,"Final minus initial (mm)":m["readings"][member]["return"]-m["readings"][member]["start"]} for member in core.MEMBERS]),hide_index=True)
    for key in ("Q1","Q2","Q3"):text("explanations",key,key+" · "+core.QUESTIONS[key],height=140)


def page_capacity(root):
    if not gate(require_readings=True):return
    m=model();settings=m["settings"]
    if not core.recorded(m,"theory") or not core.recorded(m,"experimental"):
        st.info("Record Sections 5 and 6 first. Capacity visualisation appears after your handwritten capacity attempt.");return
    st.subheader("Determine and defend the limiting mass")
    cols=st.columns(3)
    cols[0].metric("Allowable tension",f"{settings['tension']:g} N")
    cols[1].metric("Allowable compression",f"{settings['compression']:g} N")
    cols[2].metric("Approved physical mass",f"{settings['approved_mass']:g} kg")
    st.markdown("Using equilibrium, express the critical tensile and compressive member forces in terms of the applied mass. Derive both limiting masses, choose the lower one, and state the largest 0.1 kg increment that does not exceed it. Use the given allowable forces directly; do not apply an additional safety factor.")
    st.caption("A theoretical model capacity does not authorise exceeding the approved laboratory mass. Report sufficient precision before choosing an operating increment.")
    left,right=st.columns(2)
    with left:
        for key in ("tension_mass","compression_mass","limiting_mass","operating_mass"):
            number("capacity",key,core.CAPACITY_LABELS[key],minimum=0.)
        choice("capacity","member","Governing member",["EB","AE/EC","AB/BC","AF/FE","EB and AE/EC"])
        choice("capacity","type","Governing force type",["Tension","Compression","Both"])
    with right:upload_working("H4")
    record_button("capacity",core.capacity_complete(m),"Record capacity calculation attempt")
    if core.recorded(m,"capacity"):
        st.markdown("**Explore the model after recording your attempt**")
        st.session_state.setdefault("_tl27_capacity_slider",30.0)
        mass=st.slider("Model mass only (kg)",min_value=0.,max_value=40.,step=.1,key="_tl27_capacity_slider")
        forces=core.theory(mass,settings["g"])
        tension=forces["EB"]/settings["tension"]
        compression=abs(forces["AE"])/settings["compression"]
        cols=st.columns(3)
        cols[0].metric("Tension utilisation",f"{tension:.3f}")
        cols[1].metric("Compression utilisation",f"{compression:.3f}")
        cols[2].metric("Model check","Within allowables" if max(tension,compression)<=1+1e-9 else "Capacity exceeded")
        st.image(diagram_png(mass,True,settings),width="stretch")
        text("explanations","Q4","Q4 · "+core.QUESTIONS["Q4"],height=150)


def page_submission(root):
    m=model()
    if not gate():return
    st.subheader("Review and generate your complete submission")
    text("explanations","conclusion","Conclusion: state the main finding, one supporting result and the most useful improvement.",height=120)
    st.session_state.setdefault("_tl27_declaration",m["declaration"])
    m["declaration"]=st.checkbox("I reviewed the readings, typed answers, working photographs and explanations. My typed results correspond to my working, and this submission follows the subject instructions on assistance and collaboration.",key="_tl27_declaration")
    issues=core.validation_issues(m)
    if issues:
        st.info("Complete the following before generating the report:")
        for issue in issues:st.write("• "+issue)
    else:st.success("All required components are present. This is a completeness check; your marker assesses correctness and reasoning.")
    if st.button("Generate complete report and submission files",type="primary",disabled=bool(issues),key="_tl27_generate"):
        try:
            with st.spinner("Building the report with your working photographs…"):
                st.session_state["_tl27_bundle"]=build_bundle(m,root)
                st.session_state["_tl27_bundle_signature"]=core.digest({"model":m,"report_layout":REPORT_LAYOUT_VERSION})
        except Exception as exc:st.error(f"Report generation failed: {exc}")
    bundle=st.session_state.get("_tl27_bundle")
    if bundle and st.session_state.get("_tl27_bundle_signature")==core.digest({"model":m,"report_layout":REPORT_LAYOUT_VERSION}):
        st.download_button("Download submission ZIP",bundle["zip"],file_name=bundle["stem"]+"_submission.zip",mime="application/zip",type="primary",key="_tl27_zip",on_click="ignore")
        cols=st.columns(3)
        for col,kind,label,mime in ((cols[0],"pdf","PDF report","application/pdf"),(cols[1],"docx","Word report","application/vnd.openxmlformats-officedocument.wordprocessingml.document"),(cols[2],"json","Answer file","application/json")):
            col.download_button(label,bundle[kind],file_name=bundle["stem"]+("_answers.json" if kind=="json" else "_report."+kind),mime=mime,on_click="ignore",key="_tl27_download_"+kind)
        st.markdown("Submit through LearnJCU as instructed by your lecturer. The ZIP contains the complete PDF and Word reports plus the answer file for numerical checking. If separate files are required, submit the PDF and answer JSON together. Review the PDF before submitting; changes made to the Word copy will not update the answer file.")


def staff_password():
    try:return str(st.secrets.get("TRUSSLAB_STAFF_PASSWORD",os.environ.get("TRUSSLAB_STAFF_PASSWORD","")))
    except Exception:return os.environ.get("TRUSSLAB_STAFF_PASSWORD","")


def staff_access():
    password=staff_password()
    if not password:
        st.info('Enable the staff workspace in Streamlit Secrets by setting TRUSSLAB_STAFF_PASSWORD = "your-private-password". Keep this value out of GitHub.')
        return False
    proof=hmac.new(password.encode(),b"TrussLab 2027 staff access",hashlib.sha256).hexdigest()
    if hmac.compare_digest(str(st.session_state.get("_tl27_staff_auth","")),proof):return True
    with st.form("_tl27_staff_login"):
        entered=st.text_input("Staff password",type="password")
        login=st.form_submit_button("Open staff checks")
    if login:
        if hmac.compare_digest(entered.encode(),password.encode()):
            st.session_state["_tl27_staff_auth"]=proof
            st.rerun()
        else:st.error("Password not recognised.")
    return False


def staff_workspace(root):
    st.subheader("2027 staff numerical checks")
    if not staff_access():return
    if st.button("Sign out of staff checks",key="_tl27_staff_logout"):
        for key in list(st.session_state):
            if key.startswith("_tl27_staff_"):del st.session_state[key]
        st.rerun()
    st.caption("Checks support your review. They do not assign grades or assess authorship. No submission is sent to an AI service.")
    uploads=st.file_uploader("Upload student submission ZIPs or answer JSON files",type=["zip","json"],accept_multiple_files=True,key="_tl27_staff_uploads")
    settings,warnings=core.load_settings(root)
    with st.expander("Reference settings for this marking session"):
        st.json(settings)
        for warning in warnings:st.caption(warning)
    if not uploads:return
    batch_signature=core.digest({"files":[(f.name,hashlib.sha256(f.getvalue()).hexdigest()) for f in uploads],"settings":settings})
    if st.session_state.get("_tl27_staff_batch_signature")!=batch_signature:
        results=[];all_rows=[];errors=[]
        for upload in uploads:
            try:
                m,notices,files=read_bundle(upload.getvalue())
                rows=core.check_submission(m,settings)
                for issue in core.validation_issues(m):notices.append("Completeness: "+issue)
                results.append({"name":upload.name,"model":m,"notices":notices,"files":files,"rows":rows})
                for row in rows:all_rows.append({"File":upload.name,"Student ID":m["student"]["id"],**row})
            except Exception as exc:errors.append(f"{upload.name}: could not check this file. {exc}")
        # Session-only caching avoids re-reading a whole class of photographs
        # every time the marker changes a selected comment. Never global-cache
        # student submissions across browser sessions.
        st.session_state["_tl27_staff_batch"]=(results,all_rows,errors)
        st.session_state["_tl27_staff_batch_signature"]=batch_signature
    results,all_rows,errors=st.session_state["_tl27_staff_batch"]
    for error in errors:st.error(error)
    if not results:return
    summary=[]
    for result in results:
        m=result["model"];rows=result["rows"]
        summary.append({"File":result["name"],"Student ID":m["student"]["id"],"Student":m["student"]["name"],
                        "Numerical differences":sum(r["Check"]=="Difference detected" for r in rows),
                        "Missing":sum(r["Check"]=="Missing" for r in rows),"Notices":len(result["notices"])})
    st.dataframe(pd.DataFrame(summary),hide_index=True,width="stretch")
    st.download_button("Download batch checks CSV",core.csv_bytes(all_rows),"TrussLab_2027_staff_checks.csv","text/csv",key="_tl27_staff_csv")
    index=st.selectbox("Review a submission",range(len(results)),format_func=lambda i:results[i]["name"],key="_tl27_staff_selected")
    selected=results[index];m=selected["model"]
    st.markdown(f"**{m['student']['name']} · {m['student']['id']} · {m['student']['mode']}**")
    for notice in selected["notices"]:st.warning(notice)
    display=pd.DataFrame(selected["rows"])
    for column in ("Submitted","Reference"):
        display[column]=display[column].map(lambda value:"" if value is None else str(value))
    st.dataframe(display,hide_index=True,width="stretch")
    for name,raw in selected["files"].items():
        st.download_button("Open submitted "+name.rsplit(".",1)[-1].upper(),raw,file_name=name,key="_tl27_staff_file_"+name)
    with st.expander("Review handwritten method and explanations"):
        for key,title in core.EVIDENCE_TITLES.items():
            st.markdown(f"**{key} · {title}**")
            for item in m["evidence"][key]:st.image(core.evidence_bytes(item),width="stretch")
        for key in core.QUESTIONS:
            st.markdown("**"+key+"**")
            st.write(m["explanations"][key])
    st.markdown("**Prepare feedback from your own review**")
    st.caption("Use institutional Copilot to draft feedback from your deidentified marker notes. Retain the grading decision and review the feedback before release; do not upload the actual submission to AI.")
    options=["Free-body diagrams and force directions are clear.","Equilibrium equations are set up correctly.",
             "A force component or sign needs correction.","Calculation working is incomplete or does not support the typed answer.",
             "Experimental conversion is consistent with the recorded readings.","Initial zero offset needs to be handled correctly.",
             "Percentage discrepancy or zero-force residual needs correction.","Discussion uses specific numerical evidence effectively.",
             "Discussion needs numerical evidence and a testable explanation.","Capacity reasoning correctly compares tension and compression.",
             "Capacity rounding produces an increment above the calculated limit.","The governing member or force type needs correction."]
    suffix=hashlib.sha256((selected["name"]+m["student"]["id"]).encode()).hexdigest()[:12]
    findings=st.multiselect("Select findings you have verified",options,key="_tl27_staff_findings_"+suffix)
    own=st.text_area("Additional deidentified marker notes",key="_tl27_staff_notes_"+suffix)
    if findings or own.strip():
        notes="\n".join(findings+([own.strip()] if own.strip() else []))
        prompt="Draft concise, constructive feedback for a first-year engineering practical using only the marker's verified notes below. Begin with a specific strength if one is recorded. Explain the identified gaps and one practical next step. Do not invent observations, infer AI use, or decide marks. Keep the feedback under 120 words.\n\nMarker notes:\n"+notes
        st.code(prompt,language=None)


def apply_theme():
    """Send CSS exclusively through the HTML renderer, never Markdown.

    Flattening the style also prevents indentation from being interpreted as a
    Markdown code block if a caller accidentally changes the rendering API.
    """
    stylesheet=re.sub(r"</?style\b[^>]*>","",CSS,flags=re.IGNORECASE)
    stylesheet=re.sub(r"/\*.*?\*/","",stylesheet,flags=re.DOTALL)
    stylesheet=" ".join(line.strip() for line in stylesheet.splitlines() if line.strip())
    st.html("<style>"+stylesheet+"</style>")


def main(root:Path):
    initialise(root)
    preserve_student_widgets()
    apply_theme()
    render_brand_header(root)
    if st.session_state.pop("_tl27_restored_notice",False):
        st.success("Your saved 2027 work has been restored on this browser.")
    m=model()
    completed=stage_completion(m)
    st.sidebar.markdown('<div class="sidebar-brand"><div class="title">TrussLab</div><div class="course">EG1011 · Statics and Dynamics</div></div>',unsafe_allow_html=True)
    progress_head_slot=st.sidebar.empty()
    progress_slot=st.sidebar.empty()
    progress_meta_slot=st.sidebar.empty()
    st.sidebar.markdown('<div class="sidebar-workflow-title">Practical workflow</div>',unsafe_allow_html=True)
    short_names=("Student details","Pre-lab & predictions","Safety","Data collection","Calculations","Experimental forces","Analysis","Challenge","Submission")
    current_page=st.session_state.get("_tl27_navigation",SECTIONS[0])
    def timeline_label(item):
        index=SECTIONS.index(item)
        marker="●" if item==current_page else "✅" if completed[index] else "○"
        return f"{marker}  {short_names[index]}"
    section=st.sidebar.radio("Section",SECTIONS,key="_tl27_navigation",label_visibility="collapsed",format_func=timeline_label)
    if m["student"]["mode"]:
        st.sidebar.markdown('<div class="sidebar-pathway">Current pathway<strong>'+escape(m["student"]["mode"])+"</strong></div>",unsafe_allow_html=True)
    else:
        st.sidebar.markdown('<div class="sidebar-pathway-alert"><span class="alert-icon">⚠</span><span><strong>Pathway not selected</strong><small>Choose a practical pathway to continue.</small></span></div>',unsafe_allow_html=True)
    save_slot=st.sidebar.empty()
    st.sidebar.markdown('<div class="sidebar-summary-card"><div class="sidebar-summary-title">Practical summary</div><div class="sidebar-summary-row"><span class="icon">✎</span><span><b>Evidence</b><br>Four handwritten working tasks</span></div><div class="sidebar-summary-row"><span class="icon">📄</span><span><b>Report</b><br>Complete PDF and Word report</span></div><div class="sidebar-summary-row"><span class="icon">📊</span><span><b>Dataset</b><br>Physical or simulated readings</span></div><div class="sidebar-summary-row"><span class="icon">🎯</span><span><b>Objective</b><br>Member-force analysis</span></div></div>',unsafe_allow_html=True)
    backup_slot=st.sidebar.empty()
    with st.sidebar.expander("Progress and backups"):
        st.caption("Work is saved on this browser by student ID and separately on the app server using your private resume URL. Keep a downloaded backup for another device or if browser storage is cleared.")
    st.sidebar.markdown('<div class="sidebar-footer"><div class="footer-help">Use the ❓ Help control on any page for guidance.</div><div class="footer-version">TrussLab · 2027.5</div><div>James Cook University</div><div>Mechanical Engineering</div><div class="footer-credit">Designed by Dr Mehdi Khatamifar</div></div>',unsafe_allow_html=True)
    with st.sidebar.expander("Staff tools"):
        staff=st.toggle("Staff checking workspace",value=False,key="_tl27_staff_workspace")
    if staff:
        staff_workspace(root)
        return
    render_section_guidance(SECTIONS.index(section))
    pages=(page_details,page_predictions,page_safety,page_data,page_theory,page_experimental,page_results,page_capacity,page_submission)
    try:pages[SECTIONS.index(section)](root)
    finally:
        current=model()
        completed=stage_completion(current)
        progress_head_slot.markdown(f'<div class="sidebar-progress-head"><div>Progress</div><span>{round(sum(completed)/len(completed)*100)}%</span></div>',unsafe_allow_html=True)
        progress_slot.progress(sum(completed)/len(completed))
        progress_meta_slot.markdown(f'<div class="sidebar-progress-meta">Stage {SECTIONS.index(section)+1} of 9 · {sum(completed)} complete</div>',unsafe_allow_html=True)
        with backup_slot.container():
            st.download_button("Download progress backup",core.progress_bytes(current),file_name=f"TrussLab_2027_{current['student']['id'] or 'progress'}_backup.json",mime="application/json",on_click="ignore",key="_tl27_backup")
        try:
            _save_current_progress(root)
            saved_on_server=True
        except Exception:
            saved_on_server=False
        try:browser_progress(root)
        except Exception:
            st.session_state["_tl27_browser_status"]="unavailable"
        local_status=st.session_state.get("_tl27_browser_status","pending")
        if local_status=="saved" and st.session_state.get("_tl27_browser_ack_hash")==core.digest(current):
            save_slot.markdown('<div class="sidebar-status-inline good"><span class="dot"></span><span>Progress saved on this browser'+(' and app server' if saved_on_server else '')+'</span></div>',unsafe_allow_html=True)
        elif saved_on_server:
            save_slot.markdown('<div class="sidebar-status-inline good"><span class="dot"></span><span>Progress saved on the app server</span></div>',unsafe_allow_html=True)
        else:
            save_slot.markdown('<div class="sidebar-status-inline warn"><span class="dot"></span><span>Download a progress backup before leaving.</span></div>',unsafe_allow_html=True)
