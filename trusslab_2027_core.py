"""Pure calculations, progress files and staff checks for the 2027 practical.

No AI services are contacted. Reference values are recomputed independently of
the student's theoretical answers. The geometry is the original symmetric,
45-degree, pin-jointed truss with its vertical load applied at joint B.
"""
from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
import json
import math
import random
import re
import secrets
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

YEAR = 2027
SCHEMA = "trusslab-2027-v1"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 30_000_000
MAX_STORED_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_BOUNDS = (2000, 2600)
LOW_RESOLUTION_EDGE = 1200
MEMBERS = ("AF", "FE", "AE", "AB", "EB")
ALL_MEMBERS = ("AF", "FE", "ED", "DC", "AB", "BC", "AE", "EC", "EB")
LOADS = (10, 20, 30)
READING_KEYS = ("start", "10", "20", "30", "return")
PHYSICAL = "Physical laboratory"
ONLINE = "Online simulated practical"
STATES = ("Tension", "Compression", "Zero force")
EVIDENCE_TITLES = {
    "H1": "Whole-truss free-body diagram and support reactions",
    "H2": "Zero-force reasoning and joint A and B calculations",
    "H3": "Experimental force conversions and percentage discrepancy",
    "H4": "Tensile and compressive capacity calculations",
}
THEORY_LABELS = {
    "W": "Applied load W (N)", "Ax": "Horizontal reaction Ax (N)",
    "Ay": "Vertical reaction Ay (N)", "Cy": "Vertical reaction Cy (N)",
    "AE": "Member AE (N)", "AB": "Member AB (N)", "EB": "Member EB (N)",
}
EXPERIMENTAL_LABELS = {
    "AE": "Experimental AE force at 30 kg (N)",
    "AB": "Experimental AB force at 30 kg (N)",
    "AE_percent": "AE discrepancy relative to your theoretical AE (%)",
}
CAPACITY_LABELS = {
    "tension_mass": "Tension-controlled mass (kg)",
    "compression_mass": "Compression-controlled mass (kg)",
    "limiting_mass": "Theoretical limiting mass (kg)",
    "operating_mass": "Largest 0.1 kg increment within the theoretical capacity (kg)",
    "member": "Governing member", "type": "Governing force type",
}
QUESTIONS = {
    "Q1": "Among AE, AB and EB, which has the smallest percentage discrepancy at 30 kg? Quote its measured force, your theoretical force and discrepancy. Consider AF and FE separately using residuals in N.",
    "Q2": "Use two or three recorded load cases for one member to test proportionality. Show a numerical ratio, increment or prediction and explain what the comparison indicates.",
    "Q3": "Identify the most significant pattern or limitation in your own data. Quote numerical evidence, explain one plausible cause and propose a specific measurement or check that could test it. For simulated data, distinguish the model's imposed variation from observations of a physical rig.",
    "Q4": "Compare your tensile and compressive limiting masses. Explain the governing member and force type, distinguish a rounded capacity from an operating increment, and explain how the approved laboratory mass relates to your result.",
}
DEFAULT_CALIBRATION = {"AF": 420.0, "FE": 405.0, "AE": 395.0, "AB": 410.0, "EB": 385.0}


def now():
    return datetime.now(ZoneInfo("Australia/Brisbane")).isoformat(timespec="seconds")


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_settings(root: Path):
    settings = {"g": 9.81, "tension": 300.0, "compression": 220.0,
                "approved_mass": 30.0, "calibration": dict(DEFAULT_CALIBRATION),
                "calibration_source": "Demonstration defaults"}
    warnings = []
    config_path = root / "app_config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            for source, target in (("allowed_tension_N", "tension"), ("allowed_compression_N", "compression"), ("approved_max_mass_kg", "approved_mass")):
                value = config.get(source, settings[target])
                if not finite(value) or value <= 0:
                    raise ValueError(f"{source} must be a positive finite number")
                settings[target] = float(value)
        except (ValueError, TypeError, OSError) as exc:
            raise ValueError(f"Check app_config.json: {exc}") from exc
    try:
        with (root / "calibration.csv").open(newline="", encoding="utf-8-sig") as stream:
            values = {row["member"].strip().upper(): float(row["factor_N_per_mm"]) for row in csv.DictReader(stream)}
        if any(not finite(values.get(member)) or values[member] <= 0 for member in MEMBERS):
            raise ValueError("All five factors must be finite and positive")
        settings["calibration"] = {member: values[member] for member in MEMBERS}
        settings["calibration_source"] = "calibration.csv"
    except (OSError, ValueError, KeyError, TypeError):
        warnings.append("Demonstration calibration factors are active. Confirm apparatus-specific factors before assessing physical measurements.")
    if settings["calibration"] == DEFAULT_CALIBRATION and not warnings:
        warnings.append("The calibration file contains the original default factors. The lecturer should confirm that these factors apply to the physical apparatus.")
    return settings, warnings


def fresh_model(settings):
    return {
        "schema": SCHEMA, "year": YEAR, "created_at": now(),
        "student": {"name": "", "id": "", "group": "", "mode": ""},
        "settings": copy.deepcopy(settings),
        "prelab": {"support_a": None, "support_c": None, "weight10": None,
                   "reason_zero": "", "reason_ae": "", "predictions": {m: None for m in MEMBERS}},
        "safety": {"briefing": False, "ppe": False, "inspection": False,
                   "loading": False, "emergency": False, "confirmed": False},
        "readings": {m: {k: None for k in READING_KEYS} for m in MEMBERS},
        "theory": {k: None for k in THEORY_LABELS},
        "experimental": {k: None for k in EXPERIMENTAL_LABELS},
        "capacity": {k: None for k in CAPACITY_LABELS},
        "explanations": {k: "" for k in ("aim", "method", "Q1", "Q2", "Q3", "Q4", "conclusion")},
        "evidence": {k: [] for k in EVIDENCE_TITLES},
        "attempts": {}, "captured": [], "declaration": False,
    }


def theory(mass, g=9.81):
    if not finite(mass) or mass < 0 or not finite(g) or g <= 0:
        raise ValueError("Mass must be nonnegative and gravity positive")
    w = mass * g
    return {"W": w, "Ax": 0.0, "Ay": w / 2, "Cy": w / 2,
            "AF": 0.0, "FE": 0.0, "ED": 0.0, "DC": 0.0,
            "AE": -w / math.sqrt(2), "EC": -w / math.sqrt(2),
            "AB": w / 2, "BC": w / 2, "EB": w}


def capacity(settings):
    mt = settings["tension"] / settings["g"]
    mc = math.sqrt(2) * settings["compression"] / settings["g"]
    limiting = min(mt, mc)
    tied = math.isclose(mt, mc, rel_tol=1e-10)
    return {"tension_mass": mt, "compression_mass": mc,
            "limiting_mass": limiting,
            "operating_mass": math.floor((limiting + 1e-10) * 10) / 10,
            "member": "EB and AE/EC" if tied else "EB" if mt < mc else "AE/EC",
            "type": "Both" if tied else "Tension" if mt < mc else "Compression"}


def simulation(student_id, settings):
    if not re.fullmatch(r"\d{8}", student_id):
        raise ValueError("Use an eight-digit JCU student ID")
    rng = random.Random(int(hashlib.sha256(f"TRUSSLAB|2027|{student_id}".encode()).hexdigest(), 16))
    readings = {}
    for member in MEMBERS:
        initial = round(rng.uniform(-0.002, 0.002), 3)
        bias = rng.uniform(-0.035, 0.035)
        residual_slope = rng.uniform(-0.0001, 0.0001) if member in ("AF", "FE") else 0
        row = {"start": initial}
        for mass in LOADS:
            displacement = theory(mass, settings["g"])[member] / settings["calibration"][member]
            row[str(mass)] = round(initial + displacement * (1 + bias) + residual_slope * mass + rng.uniform(-0.001, 0.001), 3)
        row["return"] = round(initial + rng.uniform(-0.002, 0.002), 3)
        readings[member] = row
    return readings


def measured_force(model, member, mass=30):
    row = model["readings"][member]
    loaded, initial = row.get(str(mass)), row.get("start")
    if not finite(loaded) or not finite(initial):
        return None
    return (loaded - initial) * model["settings"]["calibration"][member]


def discrepancy(experimental, theoretical):
    if not finite(experimental) or not finite(theoretical) or abs(theoretical) < 1e-9:
        return None
    return 100 * abs(experimental - theoretical) / abs(theoretical)


def comparison_rows(model):
    rows = []
    for member in MEMBERS:
        force = measured_force(model, member)
        predicted = model["prelab"]["predictions"][member]
        entered = model["theory"].get(member) if member in ("AE", "AB", "EB") else (0.0 if predicted == "Zero force" else None)
        percent = discrepancy(force, entered)
        rows.append({"Member": member, "Corrected dial (mm)": None if force is None else force / model["settings"]["calibration"][member],
                     "Calibration (N/mm)": model["settings"]["calibration"][member],
                     "Experimental force (N)": force, "Your theoretical force (N)": entered,
                     "Comparison": f"{percent:.1f}%" if percent is not None else f"{abs(force):.2f} N residual" if force is not None and entered == 0 else "Not defined",
                     "Your prediction": predicted or "Not entered"})
    return rows


def normalise_image(raw: bytes, filename: str):
    """Validate a photo, correct orientation and save a bounded, portable copy.

    Small sources are not resampled upward: report sizing cannot recover detail.
    The stored byte cap also keeps all twelve allowed photographs within the
    existing 40 MB progress-file limit, including their base64 representation.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not raw:
        raise ValueError("The image is empty; choose a JPG or PNG photograph")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Each photograph must be no larger than 10 MB; resize or compress it and try again")
    try:
        with Image.open(io.BytesIO(raw)) as original:
            if original.format not in ("JPEG", "PNG"):
                raise ValueError("Use a JPG, JPEG or PNG image; export HEIC, PDF or other formats as JPG/PNG first")
            if original.width * original.height > MAX_IMAGE_PIXELS:
                raise ValueError("Photograph exceeds 30 megapixels; resize it and upload the smaller copy")
            image = ImageOps.exif_transpose(original)
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, "white")
                image = Image.alpha_composite(background, rgba).convert("RGB")
            else:
                image = image.convert("RGB")
            image.thumbnail(IMAGE_BOUNDS, Image.Resampling.LANCZOS)
            def encode(quality):
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=quality, optimize=True)
                return output.getvalue()
            # Handwritten pages normally fit at quality 90. Noisy photographs
            # may need more compression or a smaller copy for reliable backups.
            for quality in (90, 85, 80, 75):
                data = encode(quality)
                if len(data) <= MAX_STORED_IMAGE_BYTES:
                    break
            while len(data) > MAX_STORED_IMAGE_BYTES:
                image = image.resize((max(1, round(image.width * .85)),
                                      max(1, round(image.height * .85))), Image.Resampling.LANCZOS)
                data = encode(80)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("This image cannot be read safely; export a fresh JPG/PNG or take a new photograph") from exc
    return {"name": Path(filename).name[:120], "data": base64.b64encode(data).decode(),
            "sha256": hashlib.sha256(data).hexdigest()}


def evidence_bytes(item):
    raw = base64.b64decode(item["data"], validate=True)
    if hashlib.sha256(raw).hexdigest() != item["sha256"]:
        raise ValueError("A working photograph has changed; upload it again")
    return raw


def image_dimensions(item):
    """Read the saved photo's dimensions, including photographs in old backups."""
    from PIL import Image
    with Image.open(io.BytesIO(evidence_bytes(item))) as image:
        return image.size


def attempt_signature(model, scope):
    payload = {"identity": {k: model["student"][k] for k in ("id", "mode")}}
    evidence = model["evidence"]
    if scope == "predictions":
        payload["prelab"] = model["prelab"]
    elif scope == "theory":
        payload.update(theory=model["theory"], g=model["settings"]["g"],
                       evidence={k: [v["sha256"] for v in evidence[k]] for k in ("H1", "H2")})
    elif scope == "experimental":
        payload.update(experimental=model["experimental"], readings=model["readings"],
                       calibration=model["settings"]["calibration"], own_theory=model["theory"],
                       evidence=[v["sha256"] for v in evidence["H3"]])
    elif scope == "capacity":
        payload.update(capacity=model["capacity"], settings=model["settings"],
                       evidence=[v["sha256"] for v in evidence["H4"]])
    else:
        raise ValueError("Unknown calculation stage")
    return digest(payload)


def recorded(model, scope):
    return model["attempts"].get(scope, {}).get("signature") == attempt_signature(model, scope)


def record_attempt(model, scope):
    previous = model["attempts"].get(scope, {})
    section = {"predictions": "prelab", "theory": "theory", "experimental": "experimental", "capacity": "capacity"}[scope]
    model["attempts"][scope] = {
        "signature": attempt_signature(model, scope), "recorded_at": now(),
        "first_recorded_at": previous.get("first_recorded_at", now()),
        "first_answers": previous.get("first_answers", copy.deepcopy(model[section])),
    }


def identity_complete(model):
    student = model["student"]
    return bool(student["name"].strip() and re.fullmatch(r"\d{8}", student["id"])
                and student["group"].strip() and student["mode"] in (PHYSICAL, ONLINE))


def predictions_complete(model):
    p = model["prelab"]
    return bool(p["support_a"] and p["support_c"] and finite(p["weight10"])
                and p["reason_zero"].strip() and p["reason_ae"].strip()
                and all(p["predictions"][m] in STATES for m in MEMBERS))


def safety_complete(model):
    return model["student"]["mode"] == ONLINE or all(model["safety"].values())


def readings_complete(model):
    return all(finite(model["readings"][m][k]) for m in MEMBERS for k in READING_KEYS)


def theory_complete(model):
    return all(finite(v) for v in model["theory"].values()) and all(model["evidence"][k] for k in ("H1", "H2"))


def experimental_complete(model):
    return all(finite(v) for v in model["experimental"].values()) and bool(model["evidence"]["H3"])


def capacity_complete(model):
    c = model["capacity"]
    return all(finite(c[k]) and c[k] >= 0 for k in ("tension_mass", "compression_mass", "limiting_mass", "operating_mass")) and bool(c["member"] and c["type"] and model["evidence"]["H4"])


def validation_issues(model):
    issues = []
    if not identity_complete(model): issues.append("Complete student details and select a pathway.")
    if not predictions_complete(model) or not recorded(model, "predictions"): issues.append("Record your pre-lab responses and predictions in Section 2.")
    if not safety_complete(model): issues.append("Complete the physical laboratory safety acknowledgement in Section 3.")
    if not readings_complete(model): issues.append("Record all initial, loaded and final unloaded readings in Section 4.")
    if not theory_complete(model) or not recorded(model, "theory"): issues.append("Record all theoretical answers and H1/H2 photographs in Section 5.")
    if not experimental_complete(model) or not recorded(model, "experimental"): issues.append("Record both force conversions, the discrepancy and H3 working in Section 6.")
    if not capacity_complete(model) or not recorded(model, "capacity"): issues.append("Record both capacity limits, the decision and H4 working in Section 8.")
    for key in ("aim", "method", "Q1", "Q2", "Q3", "Q4", "conclusion"):
        if not model["explanations"].get(key, "").strip(): issues.append(f"Complete the {key} written response.")
    if not model["declaration"]: issues.append("Confirm the final review declaration in Section 9.")
    return issues


def validate_model(model):
    if not isinstance(model, dict) or model.get("schema") != SCHEMA or model.get("year") != YEAR:
        raise ValueError("This file is not a TrussLab 2027 progress or answer file")
    template = fresh_model(model.get("settings", {}))
    for key in template:
        if key not in model or not isinstance(model[key], type(template[key])):
            raise ValueError(f"Missing or invalid section: {key}")
    settings = model["settings"]
    for key in ("g", "tension", "compression", "approved_mass"):
        if not finite(settings.get(key)) or settings[key] <= 0:
            raise ValueError(f"Invalid setting: {key}")
    if settings["g"] != 9.81:
        raise ValueError("This practical uses g = 9.81 m/s^2")
    if not isinstance(settings.get("calibration_source"),str):raise ValueError("Invalid calibration source")
    if not isinstance(settings.get("calibration"), dict) or any(not finite(settings["calibration"].get(m)) or settings["calibration"][m] <= 0 for m in MEMBERS):
        raise ValueError("Invalid calibration table")
    for section in ("student", "prelab", "safety", "readings", "theory", "experimental", "capacity", "explanations", "evidence"):
        if not set(template[section]).issubset(model[section]):
            raise ValueError(f"Incomplete section: {section}")
    p=model["prelab"]
    if not isinstance(p["predictions"],dict) or not set(MEMBERS).issubset(p["predictions"]):
        raise ValueError("Invalid prediction table")
    if any(p["predictions"][m] not in (None,)+STATES for m in MEMBERS):raise ValueError("Invalid predicted state")
    if any(p[key] not in (None,"Pin support","Roller support","Fixed support") for key in ("support_a","support_c")):
        raise ValueError("Invalid support response")
    if p["weight10"] is not None and not finite(p["weight10"]):raise ValueError("Invalid pre-lab weight")
    if any(not isinstance(p[key],str) or len(p[key])>6000 for key in ("reason_zero","reason_ae")):
        raise ValueError("Invalid pre-lab explanation")
    if any(not isinstance(v,bool) for v in model["safety"].values()):raise ValueError("Invalid safety acknowledgement")
    if any(v not in READING_KEYS for v in model["captured"]):raise ValueError("Invalid captured load")
    for key in ("tension_mass","compression_mass","limiting_mass","operating_mass"):
        if model["capacity"][key] is not None and not finite(model["capacity"][key]):raise ValueError("Invalid capacity answer")
    if model["capacity"]["member"] not in (None,"EB","AE/EC","AB/BC","AF/FE","EB and AE/EC") or model["capacity"]["type"] not in (None,"Tension","Compression","Both"):
        raise ValueError("Invalid capacity classification")
    for scope,attempt in model["attempts"].items():
        if scope not in ("predictions","theory","experimental","capacity") or not isinstance(attempt,dict) or not re.fullmatch(r"[a-f0-9]{64}",str(attempt.get("signature",""))):
            raise ValueError("Invalid recorded attempt")
    for member in MEMBERS:
        if not isinstance(model["readings"][member], dict) or not set(READING_KEYS).issubset(model["readings"][member]):
            raise ValueError("Invalid dial reading table")
        for value in model["readings"][member].values():
            if value is not None and not finite(value): raise ValueError("Readings must be finite numbers or blank")
    for section in ("theory", "experimental"):
        if any(v is not None and not finite(v) for v in model[section].values()): raise ValueError("Calculation entries must be finite numbers or blank")
    if any(not isinstance(v, str) or len(v) > 6000 for v in model["explanations"].values()):
        raise ValueError("Invalid written response")
    if any(not isinstance(v, str) or len(v) > 200 for v in model["student"].values()):
        raise ValueError("Invalid student details")
    if model["student"]["mode"] not in ("",PHYSICAL,ONLINE) or (model["student"]["id"] and not re.fullmatch(r"\d{8}",model["student"]["id"])):
        raise ValueError("Invalid student ID or pathway")
    for key in EVIDENCE_TITLES:
        items = model["evidence"][key]
        if not isinstance(items, list) or len(items) > 3: raise ValueError("Use no more than three photographs per task")
        for item in items:
            if not isinstance(item, dict) or not {"name", "data", "sha256"}.issubset(item): raise ValueError("Invalid photograph")
            if not isinstance(item["name"],str) or len(item["name"])>200 or not isinstance(item["data"],str) or not re.fullmatch(r"[a-f0-9]{64}",str(item["sha256"])):
                raise ValueError("Invalid photograph metadata")
            raw = evidence_bytes(item)
            if len(raw) > 5_000_000: raise ValueError("Working photograph is too large")
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as image:
                if image.width*image.height>30_000_000:raise ValueError("Photograph resolution is too large")
                image.verify()
    # Reject NaN and Infinity anywhere, including nested metadata.
    json.dumps(model, allow_nan=False)
    return model


def progress_bytes(model):
    return json.dumps(model, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")


def parse_progress(data):
    if len(data) > 40 * 1024 * 1024: raise ValueError("Progress file is too large")
    return validate_model(json.loads(data))


def save_progress(root, token, model):
    if not re.fullmatch(r"[a-f0-9]{48}", token): raise ValueError("Invalid private progress key")
    folder = Path(root) / "student_saves" / "2027"
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(progress_bytes(model))
        temporary.replace(folder / f"{token}.json")
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def load_progress(root, token):
    if not re.fullmatch(r"[a-f0-9]{48}", token): return None
    path = Path(root) / "student_saves" / "2027" / f"{token}.json"
    return parse_progress(path.read_bytes()) if path.exists() else None


def new_token():
    return secrets.token_hex(24)


def check_submission(model, reference_settings=None):
    """Return evidence checks, never grades. Tolerances cover normal rounding."""
    validate_model(model)
    rows = []
    settings = reference_settings or model["settings"]
    ref = theory(30, settings["g"])

    def add(question, submitted, expected, unit="", atol=0.15, rtol=0.002, note=""):
        if expected is None:
            status = "Needs review"
        elif isinstance(expected, str):
            status = "Matches" if submitted == expected else "Difference detected"
        else:
            status = "Missing" if submitted is None else "Within tolerance" if finite(submitted) and math.isclose(submitted, expected, abs_tol=atol, rel_tol=rtol) else "Difference detected"
        rows.append({"Question": question, "Submitted": submitted, "Reference": expected,
                     "Unit": unit, "Check": status, "Marker note": note})

    for key, expected in (("support_a", "Pin support"), ("support_c", "Roller support")):
        add(f"Pre-lab {key}", model["prelab"][key], expected)
    add("Pre-lab weight10", model["prelab"]["weight10"], 10 * settings["g"], "N")
    for member in MEMBERS:
        expected = "Zero force" if ref[member] == 0 else "Tension" if ref[member] > 0 else "Compression"
        add(f"Prediction {member}", model["prelab"]["predictions"][member], expected)
    for key, label in THEORY_LABELS.items(): add(f"Theory {key}", model["theory"][key], ref[key], "N")
    for member in ("AE", "AB"):
        add(f"Experimental {member}", model["experimental"][member], measured_force(model, member), "N", atol=0.15, rtol=0.001,
            note="Computed from recorded readings; a large discrepancy with ideal theory is not itself a marking error.")
    ae = measured_force(model, "AE")
    add("AE percentage using own theory", model["experimental"]["AE_percent"], discrepancy(ae, model["theory"]["AE"]), "%", atol=0.15, rtol=0.005,
        note="Allows follow-through from the student's own theoretical AE. Check the original theory error separately.")
    own_ae, own_ab, own_eb, ax, ay, cy = (model["theory"][k] for k in ("AE", "AB", "EB", "Ax", "Ay", "Cy"))
    if all(finite(v) for v in (own_ae, own_ab, own_eb, ax, ay, cy)):
        add("Support vertical equilibrium residual", ay + cy - ref["W"], 0.0, "N", atol=0.4)
        add("Joint A horizontal residual", ax + own_ab + own_ae / math.sqrt(2), 0.0, "N", atol=0.4)
        add("Joint A vertical residual", ay + own_ae / math.sqrt(2), 0.0, "N", atol=0.4)
        add("Joint B vertical residual", own_eb - ref["W"], 0.0, "N", atol=0.4)
    limits = capacity(settings)
    for key in CAPACITY_LABELS:
        add(f"Capacity {key}", model["capacity"][key], limits[key], "kg" if key.endswith("mass") else "",
            atol=0.000001 if key == "operating_mass" else 0.03, rtol=0)
    mass = model["capacity"]["operating_mass"]
    if finite(mass) and mass > limits["limiting_mass"] + 1e-9:
        rows.append({"Question": "Capacity rounding", "Submitted": mass, "Reference": limits["limiting_mass"], "Unit": "kg",
                     "Check": "Difference detected", "Marker note": "The stated operating increment exceeds the unrounded theoretical capacity."})
    for key in EVIDENCE_TITLES:
        add(f"{key} working", "Uploaded" if model["evidence"][key] else None, "Uploaded", note="Review method, diagrams, units and correspondence with typed answers manually.")
    for key in QUESTIONS:
        rows.append({"Question": key, "Submitted": model["explanations"][key], "Reference": None, "Unit": "", "Check": "Needs review",
                     "Marker note": "Judge numerical evidence, explanation and engineering reasoning against the rubric."})
    if model["student"]["mode"]==ONLINE and re.fullmatch(r"\d{8}",model["student"]["id"]):
        expected_data=simulation(model["student"]["id"],model["settings"])
        changed=[f"{member}/{key}" for member in MEMBERS for key in READING_KEYS if model["readings"][member][key]!=expected_data[member][key]]
        if changed:
            rows.append({"Question":"Simulated dataset","Submitted":", ".join(changed),"Reference":"Reproduced from the 2027 ID and recorded settings","Unit":"","Check":"Needs review",
                         "Marker note":"Some readings differ from the assigned simulation. Check transcription and file provenance; this is not an authorship determination."})
    if reference_settings and model["settings"] != reference_settings:
        rows.append({"Question": "Configuration", "Submitted": "Settings in submission", "Reference": "Current staff settings", "Unit": "", "Check": "Needs review",
                     "Marker note": "Configuration differs. Verify the applicable calibration/capacities before interpreting checks; do not automatically deduct marks."})
    return rows


def csv_bytes(rows):
    if not rows: return b""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            # Prevent spreadsheet formula evaluation of uploaded text.
            safe[key] = "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
        writer.writerow(safe)
    return output.getvalue().encode("utf-8-sig")
