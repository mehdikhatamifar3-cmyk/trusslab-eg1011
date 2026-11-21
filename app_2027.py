"""Guided 2027 practical and password-protected staff checking workspace."""
from __future__ import annotations

import copy
import hashlib
import hmac
import io
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

import trusslab_2027_core as core
from trusslab_2027_reports import build_bundle, diagram_png, read_bundle, readings_plot_png

SECTIONS = (
    "1 Student details", "2 Pre-lab and predictions", "3 Safety",
    "4 Data collection", "5 Theoretical calculations", "6 Experimental calculations",
    "7 Results and explanations", "8 Capacity challenge", "9 Review and submission",
)
CSS = """
<style>
.block-container{max-width:1440px;padding-top:2rem;padding-bottom:3rem}
h1,h2,h3{color:#143654;letter-spacing:-.02em}
[data-testid="stSidebar"]{background:#f5f8fc}
.tl-header{display:flex;align-items:center;gap:24px;border-bottom:1px solid #cbd8e6;padding-bottom:18px;margin-bottom:22px}
.tl-header h1{font-size:2.7rem;margin:0}.tl-kicker{color:#0b4f8a;font-size:.8rem;font-weight:700;letter-spacing:.12em}
.tl-subtitle{color:#526278;margin-top:4px}.tl-year{display:inline-block;background:#e6f0fb;color:#0b4f8a;border-radius:20px;padding:5px 14px;font-weight:700}
.tl-note{border-left:4px solid #087ad1;background:#f0f6fc;padding:14px 18px;border-radius:4px;margin:12px 0}
[data-testid="stMetric"]{border:1px solid #dae3ed;border-radius:10px;padding:12px;background:#fff}
div.stButton>button[kind="primary"]{background:#0b4f8a;border-color:#0b4f8a}
</style>
"""


def initialise(root):
    if "_tl27_model" in st.session_state:return
    settings,warnings=core.load_settings(root)
    token=st.query_params.get("work","")
    try: saved=core.load_progress(root,token) if token else None
    except (ValueError,OSError,TypeError,KeyError): saved=None
    if saved is None:
        token=core.new_token()
        saved=core.fresh_model(settings)
    st.session_state["_tl27_model"]=saved
    st.session_state["_tl27_token"]=token
    st.session_state["_tl27_warnings"]=warnings
    st.query_params["work"]=token


def model():return st.session_state["_tl27_model"]


def sync(section,key,widget):
    model()[section][key]=st.session_state[widget]


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
    generation=st.session_state.get(f"_tl27_upload_generation_{key}",0)
    widget=f"_tl27_upload_{key}_{generation}"
    uploads=st.file_uploader("Add or replace working photographs",type=["jpg","jpeg","png"],accept_multiple_files=True,
                             key=widget,help="Use up to three clear photographs per task. Each file may be up to 10 MB. Crop to the page and keep equations readable.")
    if uploads:
        try:
            if len(uploads)>3:raise ValueError("Use at most three photographs per task")
            upload_hash=core.digest([hashlib.sha256(f.getvalue()).hexdigest() for f in uploads])
            cache=f"_tl27_uploaded_hash_{key}"
            if st.session_state.get(cache)!=upload_hash:
                converted=[core.normalise_image(f.getvalue(),f.name) for f in uploads]
                model()["evidence"][key]=converted
                st.session_state[cache]=upload_hash
        except Exception as exc:
            st.error(f"Photographs were not replaced: {exc}")
    if model()["evidence"][key]:
        st.caption(f"{len(model()['evidence'][key])} photograph(s) saved with this practical.")
        with st.expander(f"Review saved {key} photographs"):
            for item in model()["evidence"][key]:st.image(core.evidence_bytes(item),caption=item["name"],width="stretch")
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
    left,right=st.columns([1.25,1])
    with left:
        st.subheader("Your details and practical pathway")
        with st.form("_tl27_details"):
            name=st.text_input("Full name",value=s["name"],max_chars=120)
            sid=st.text_input("JCU student ID (8 digits)",value=s["id"],max_chars=8)
            group=st.text_input("Practical/tutorial group",value=s["group"],max_chars=120)
            modes=[core.PHYSICAL,core.ONLINE]
            mode=st.selectbox("Practical pathway",modes,index=modes.index(s["mode"]) if s["mode"] in modes else None,
                              placeholder="Choose the pathway confirmed by your lecturer")
            restart=st.checkbox("Start fresh calculations and readings if I change an existing student ID or pathway")
            submitted=st.form_submit_button("Save student details",type="primary")
        if submitted:
            import re
            if not name.strip() or not re.fullmatch(r"\d{8}",sid.strip()) or not group.strip() or mode not in modes:
                st.error("Enter your name, eight-digit JCU ID, group and pathway.")
            else:
                changed=bool(s["id"] and (s["id"]!=sid.strip() or s["mode"]!=mode))
                if changed and not restart:st.error("Changing an existing ID or pathway starts a fresh practical. Download a progress backup first, then tick the fresh-start option.")
                else:
                    if changed:
                        st.session_state["_tl27_model"]=core.fresh_model(m["settings"])
                        clear_widgets()
                    model()["student"]={"name":name.strip(),"id":sid.strip(),"group":group.strip(),"mode":mode}
                    st.success("Student details saved. Continue to Section 2.")
        text("explanations","aim","Aim: what will you investigate?",height=90,help="Two or three sentences are sufficient.")
        text("explanations","method","Procedure: summarise what you actually did",height=110,help="Describe the selected physical or simulated pathway and how the readings were obtained.")
    with right:
        st.image(diagram_png(),caption="Pin at A · roller at C · load at B · 45-degree diagonals",width="stretch")
        st.markdown("**What you will submit**\n\nA complete report containing your measurements, typed answers, four sets of handwritten working and short explanations based on your results.")
        st.info("Write calculations on paper or with a digital pen. Include diagrams, equations, substitutions, units and the meaning of each sign. Follow the subject instructions on permitted assistance.")
    with st.expander("Restore a downloaded 2027 progress backup"):
        backup=st.file_uploader("2027 progress JSON",type=["json"],key="_tl27_restore")
        if st.button("Restore progress",disabled=backup is None,key="_tl27_restore_button"):
            try:
                restored=core.parse_progress(backup.getvalue())
                st.session_state["_tl27_model"]=restored
                clear_widgets()
                st.rerun()
            except Exception as exc:st.error(f"Could not restore progress: {exc}")


def clear_widgets():
    for key in list(st.session_state):
        if key.startswith(("_tl27_input_","_tl27_upload_","_tl27_uploaded_hash_","_tl27_editor","_tl27_predict_")):
            del st.session_state[key]
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
        st.image(diagram_png(),width="stretch")
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
        st.image(diagram_png(),width="stretch")
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
        mass=st.slider("Model mass only (kg)",0.,40.,30.,.1,key="_tl27_capacity_slider")
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
                st.session_state["_tl27_bundle_signature"]=core.digest(m)
        except Exception as exc:st.error(f"Report generation failed: {exc}")
    bundle=st.session_state.get("_tl27_bundle")
    if bundle and st.session_state.get("_tl27_bundle_signature")==core.digest(m):
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


def main(root:Path):
    initialise(root)
    st.markdown(CSS,unsafe_allow_html=True)
    left,right=st.columns([.18,1])
    logo=root/"assets"/"jcu_logo.png"
    if logo.exists():left.image(str(logo),width=140)
    right.markdown('<div class="tl-kicker">EG1011 · STATICS AND DYNAMICS</div><div class="tl-header"><div><h1>TrussLab</h1><div class="tl-subtitle">Forces in a Plane Truss · calculations, evidence and engineering decisions</div></div><span class="tl-year">2027</span></div>',unsafe_allow_html=True)
    staff=st.sidebar.toggle("Staff checking workspace",value=False,key="_tl27_staff_workspace")
    if staff:
        staff_workspace(root)
        return
    m=model()
    st.sidebar.markdown("**Practical workflow**")
    progress_slot=st.sidebar.empty()
    section=st.sidebar.radio("Section",SECTIONS,key="_tl27_navigation",label_visibility="collapsed")
    st.sidebar.caption("Your calculations are recorded before the corresponding calculated comparisons are displayed.")
    backup_slot=st.sidebar.empty()
    st.sidebar.caption("Progress is saved separately for 2027. Keep your private resume URL and a downloaded backup; server storage can be cleared when the app restarts. Use the backup for another device.")
    st.subheader(section)
    pages=(page_details,page_predictions,page_safety,page_data,page_theory,page_experimental,page_results,page_capacity,page_submission)
    try:pages[SECTIONS.index(section)](root)
    finally:
        current=model()
        completed=[core.identity_complete(current),core.recorded(current,"predictions"),core.safety_complete(current),core.readings_complete(current),
                   core.recorded(current,"theory"),core.recorded(current,"experimental"),all(current["explanations"][k].strip() for k in ("Q1","Q2","Q3")),
                   core.recorded(current,"capacity") and bool(current["explanations"]["Q4"].strip()),not core.validation_issues(current)]
        progress_slot.progress(sum(completed)/len(completed),text=f"{sum(completed)} of {len(completed)} stages complete")
        with backup_slot.container():
            st.download_button("Download progress backup",core.progress_bytes(current),file_name=f"TrussLab_2027_{current['student']['id'] or 'progress'}_backup.json",mime="application/json",on_click="ignore",key="_tl27_backup")
        try:
            fingerprint=core.digest(model())
            if st.session_state.get("_tl27_last_saved")!=fingerprint:
                core.save_progress(root,st.session_state["_tl27_token"],model())
                st.session_state["_tl27_last_saved"]=fingerprint
            st.sidebar.caption("Progress saved for this private resume URL.")
        except Exception:
            st.sidebar.warning("Server save unavailable. Download a progress backup before leaving.")
