"""Consistent PDF/DOCX reports and portable student submission bundles."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from trusslab_2027_core import (
    CAPACITY_LABELS, EVIDENCE_TITLES, EXPERIMENTAL_LABELS, MEMBERS,
    QUESTIONS, READING_KEYS, THEORY_LABELS, capacity, comparison_rows,
    digest, evidence_bytes, now, parse_progress, progress_bytes, theory,
    validation_issues,
)

SHORT_QUESTIONS = {
    "Q1": "Agreement with theory", "Q2": "Proportionality with load",
    "Q3": "Data quality and a proposed check", "Q4": "Governing capacity and operating limit",
}


def fmt(value, digits=2):
    if value is None: return "Not entered"
    if isinstance(value, (int, float)) and not isinstance(value, bool): return f"{value:.{digits}f}"
    return str(value)


def diagram_png(mass=30, show_forces=False, settings=None):
    from matplotlib.figure import Figure
    from matplotlib.patches import Polygon
    fig = Figure(figsize=(8, 4.1), dpi=160)
    ax = fig.subplots()
    points = {"A": (0, 0), "B": (2, 0), "C": (4, 0), "F": (0, 2), "E": (2, 2), "D": (4, 2)}
    forces = theory(float(mass), settings["g"] if settings else 9.81)
    for member in ("AF", "FE", "ED", "DC", "AB", "BC", "AE", "EC", "EB"):
        a, b = points[member[0]], points[member[1]]
        force = forces[member]
        colour = "#167647" if show_forces and force > 0 else "#b73535" if show_forces and force < 0 else "#445469"
        ax.plot([a[0], b[0]], [a[1], b[1]], color=colour, linewidth=2.7)
        label = f"{member}\n{force:+.1f} N" if show_forces else member
        ax.text((a[0]+b[0])/2, (a[1]+b[1])/2 + .07, label, ha="center", va="bottom", fontsize=8,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": .94, "pad": 1.8})
    for label, (x,y) in points.items():
        ax.plot(x, y, "o", color="#172b45", markersize=5)
        ax.text(x+.06, y+.12, label, fontsize=11, fontweight="bold", color="#0b4f8a")
    for x in (0,4):
        ax.add_patch(Polygon([[x, -.02],[x-.19,-.25],[x+.19,-.25]], closed=True, facecolor="white", edgecolor="#172b45"))
    ax.plot([-.25,.25],[-.28,-.28],color="#172b45")
    ax.plot([3.75,4.25],[-.37,-.37],color="#172b45")
    ax.plot([3.9,4.1],[-.3,-.3],"o",color="#172b45",markersize=4)
    if mass:
        ax.annotate("", xy=(2,-.68), xytext=(2,-.02), arrowprops={"arrowstyle":"-|>","color":"#c62828","lw":2})
        ax.text(2.13,-.59,f"{mass:g} kg", color="#b73535",fontsize=10)
    ax.set(xlim=(-.45,4.5),ylim=(-.8,2.45),aspect="equal")
    ax.axis("off")
    fig.tight_layout(pad=.5)
    output = io.BytesIO()
    fig.savefig(output,format="png",dpi=160)
    return output.getvalue()


def readings_plot_png(model):
    from matplotlib.figure import Figure
    fig = Figure(figsize=(8,3.7),dpi=160)
    ax = fig.subplots()
    for member, colour in zip(MEMBERS,("#475569","#bd8122","#bc3636","#087b87","#7145a1")):
        row = model["readings"][member]
        if row["start"] is None: continue
        vals = [None if row[str(m)] is None else row[str(m)] - row["start"] for m in (10,20,30)]
        ax.plot((10,20,30),vals,"o-",label=member,color=colour,linewidth=1.6,markersize=4)
    ax.set(xlabel="Applied mass (kg)",ylabel="Corrected proving-ring dial reading (mm)",xticks=[10,20,30])
    ax.grid(alpha=.2)
    ax.legend(ncol=5,fontsize=8)
    fig.tight_layout()
    output=io.BytesIO()
    fig.savefig(output,format="png",dpi=160)
    return output.getvalue()


def report_blocks(model, root):
    """One content sequence feeds both report formats."""
    student, settings = model["student"], model["settings"]
    sid = model.get("submission",{}).get("id",digest(model))
    blocks=[]
    def heading(text): blocks.append(("heading",text))
    def text(value): blocks.append(("text",str(value)))
    def table(headers,rows): blocks.append(("table",(headers,rows)))
    def page(): blocks.append(("page",None))
    def image(raw,caption): blocks.append(("image",(raw,caption)))
    def working(key):
        heading(f"{key} {EVIDENCE_TITLES[key]}")
        for i,item in enumerate(model["evidence"][key],1): image(evidence_bytes(item),f"{key} handwritten working {i}")
    logo=Path(root)/"assets"/"jcu_logo.png"
    if logo.exists(): blocks.append(("logo",logo.read_bytes()))
    blocks.append(("title","Forces in a Plane Truss"))
    text("EG1011 Statics and Dynamics | 2027 practical report")
    text("TrussLab practical app designed by Dr Mehdi Khatamifar")
    table(["Student details","Recorded value"],[("Name",student["name"]),("Student ID",student["id"]),("Group",student["group"]),("Pathway",student["mode"]),("Generated",model.get("submission",{}).get("generated_at",now())),("Submission reference",sid[:16])])
    heading("1 Aim and procedure")
    text(model["explanations"]["aim"])
    text(model["explanations"]["method"])
    image(diagram_png(),"Reference geometry: central load at B, pin at A, roller at C and 45-degree diagonals. Diagram not to scale.")
    text("Positive member force denotes tension; negative denotes compression. Dial readings measure proving-ring response, rather than direct member extension.")
    page()
    heading("2 Pre-lab responses and predictions")
    p=model["prelab"]
    table(["Question","Student response"],[("Support at A",p["support_a"]),("Support at C",p["support_c"]),("Weight of 10 kg (N)",fmt(p["weight10"]))]+[(f"Prediction {m}",p["predictions"][m]) for m in MEMBERS])
    text("Zero-force reasoning: "+p["reason_zero"])
    text("AE reasoning: "+p["reason_ae"])
    text("Physical safety acknowledgement: "+("Completed" if all(model["safety"].values()) else "Not applicable to the simulated pathway"))
    heading("3 Recorded measurements")
    table(["Member","Initial 0 kg","10 kg","20 kg","30 kg","Final 0 kg"],[(m,)+tuple(fmt(model["readings"][m][k],3) for k in READING_KEYS) for m in MEMBERS])
    text("All dial readings are in mm. Corrected loaded reading = loaded dial reading - initial unloaded reading. Final unloaded readings record drift and are not substituted for the initial reference.")
    table(["Member","Calibration N/mm"],[(m,fmt(settings["calibration"][m],1)) for m in MEMBERS])
    text("Calibration source: "+settings["calibration_source"])
    page()
    heading("4 Theoretical calculations at 30 kg")
    table(["Quantity","Student answer"],[(label,fmt(model["theory"][key])) for key,label in THEORY_LABELS.items()])
    text("These are student-entered results. Recording an answer or generating this report does not establish that it is correct.")
    working("H1")
    page()
    working("H2")
    page()
    heading("5 Experimental calculations")
    table(["Quantity","Student answer"],[(label,fmt(model["experimental"][key])) for key,label in EXPERIMENTAL_LABELS.items()])
    text("F = k(D_loaded - D_initial). Percentage discrepancy = 100 |F_experimental - F_theoretical| / |F_theoretical|. A theoretical zero requires an absolute residual in N.")
    working("H3")
    page()
    heading("6 Results and interpretation")
    rows=comparison_rows(model)
    table(["Member","Measured N","Own theory N","Comparison"],[(r["Member"],fmt(r["Experimental force (N)"]),fmt(r["Your theoretical force (N)"]),r["Comparison"]) for r in rows])
    text("Measured values above are calculated from recorded readings; the theoretical column uses the student's own answers.")
    image(readings_plot_png(model),"Load response after subtraction of the initial unloaded reading.")
    for key in ("Q1","Q2","Q3"):
        heading(key+" "+SHORT_QUESTIONS[key])
        text(model["explanations"][key])
    page()
    heading("7 Capacity calculations and decision")
    text(f"Model allowable tension {settings['tension']:g} N; allowable compression {settings['compression']:g} N. Approved physical laboratory mass {settings['approved_mass']:g} kg. These model limits do not authorise a higher physical test load.")
    table(["Quantity","Student answer"],[(label,fmt(model["capacity"][key],3) if key.endswith("mass") else fmt(model["capacity"][key])) for key,label in CAPACITY_LABELS.items()])
    working("H4")
    page()
    heading("Q4 "+SHORT_QUESTIONS["Q4"])
    text(model["explanations"]["Q4"])
    heading("8 Conclusion")
    text(model["explanations"]["conclusion"])
    heading("9 Review declaration")
    text("The student confirmed that the typed results correspond to the uploaded working, that the recorded physical or simulated readings are represented accurately, and that the submission follows the subject's instructions on assistance and collaboration.")
    text("Full submission reference: "+sid)
    return blocks


def build_pdf(model,root):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,KeepTogether,Flowable
    from matplotlib import get_data_path
    for name,file in (("TLSans","DejaVuSans.ttf"),("TLSans-Bold","DejaVuSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont(name,str(Path(get_data_path())/"fonts"/"ttf"/file)))
    pdfmetrics.registerFontFamily("TLSans",normal="TLSans",bold="TLSans-Bold",italic="TLSans",boldItalic="TLSans-Bold")
    styles=getSampleStyleSheet()
    body=ParagraphStyle("TLBody",fontName="TLSans",fontSize=9.4,leading=13,spaceAfter=8)
    heading=ParagraphStyle("TLHeading",parent=body,fontName="TLSans-Bold",fontSize=11,leading=14,spaceBefore=10,spaceAfter=7,keepWithNext=True)
    title=ParagraphStyle("TLTitle",parent=heading,fontSize=21,leading=25,spaceAfter=12)
    caption=ParagraphStyle("TLCaption",parent=body,fontSize=8,leading=10,textColor=colors.HexColor("#526278"),alignment=TA_CENTER,spaceAfter=10)
    cell=ParagraphStyle("TLCell",parent=body,fontSize=8.1,leading=11,spaceAfter=0)
    def para(value,style=body): return Paragraph(escape(str(value)).replace("\n","<br/>"),style)
    class WorkingImage(Flowable):
        def __init__(self,raw,description):
            super().__init__()
            self.reader=ImageReader(io.BytesIO(raw))
            self.iw,self.ih=self.reader.getSize()
            self.caption=para(description,caption)
        def wrap(self,available_width,available_height):
            self.caption_width,self.caption_height=self.caption.wrap(available_width,100)
            maximum=min(490,available_height-self.caption_height-10)
            if maximum<280:
                self.width,self.height=available_width,510
                return self.width,self.height
            scale=min(available_width/self.iw,maximum/self.ih)
            self.image_width,self.image_height=self.iw*scale,self.ih*scale
            self.width,self.height=available_width,self.image_height+self.caption_height+10
            return self.width,self.height
        def draw(self):
            self.canv.drawImage(self.reader,(self.width-self.image_width)/2,self.caption_height+10,width=self.image_width,height=self.image_height,mask="auto")
            self.caption.drawOn(self.canv,0,0)
    output=io.BytesIO()
    document=SimpleDocTemplate(output,pagesize=letter,rightMargin=44,leftMargin=44,topMargin=43,bottomMargin=43,
                               title="TrussLab 2027 practical report",author=model["student"]["name"])
    story=[]
    width=letter[0]-88
    for kind,value in report_blocks(model,root):
        if kind=="title": story.append(para(value,title))
        elif kind=="heading":
            style=ParagraphStyle("WorkingHeading",parent=heading,keepWithNext=False) if value.startswith(tuple(EVIDENCE_TITLES)) else heading
            story.append(para(value,style))
        elif kind=="text": story.append(para(value))
        elif kind=="page": story.append(PageBreak())
        elif kind=="logo":
            reader=ImageReader(io.BytesIO(value));w,h=reader.getSize()
            im=Image(io.BytesIO(value),width=108,height=108*h/w);im.hAlign="LEFT"
            story.extend((im,Spacer(1,12)))
        elif kind=="table":
            headers,rows=value
            values=[[para(v,cell) for v in headers]]+[[para(v,cell) for v in row] for row in rows]
            if len(headers)==2: widths=[width*.48,width*.52]
            elif len(headers)==6: widths=[width*.14]+[width*.172]*5
            else: widths=[width/len(headers)]*len(headers)
            table=Table(values,colWidths=widths,repeatRows=1,hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dce9f3")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f4f7fa")]),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#d9d9d9")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
            story.extend((table,Spacer(1,8)))
        elif kind=="image":
            raw,description=value
            reader=ImageReader(io.BytesIO(raw));w,h=reader.getSize()
            if description.startswith("H"):
                # Keep the photograph with its caption and fit the space left
                # below the typed result table. Never crop working.
                story.append(WorkingImage(raw,description))
                continue
            max_height=190
            scale=min(width/w,max_height/h)
            im=Image(io.BytesIO(raw),width=w*scale,height=h*scale)
            story.append(KeepTogether([im,para(description,caption)]))
    ref=model.get("submission",{}).get("id","")[:12]
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont("TLSans",7);canvas.setFillColor(colors.HexColor("#526278"))
        canvas.drawString(44,22,f"EG1011 | TrussLab 2027 | {ref}")
        canvas.drawRightString(letter[0]-44,22,f"Page {doc.page}");canvas.restoreState()
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()


def build_docx(model,root):
    from docx import Document
    from docx.shared import Inches,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from PIL import Image
    document=Document()
    section=document.sections[0]
    section.page_width=Inches(8.5);section.page_height=Inches(11)
    section.left_margin=section.right_margin=Inches(.65)
    section.top_margin=section.bottom_margin=Inches(.6)
    for name in ("Normal","Title","Heading 1"):
        style=document.styles[name];style.font.name="Calibri";style.font.color.rgb=RGBColor(0,0,0)
        style.font.size=Pt(10 if name=="Normal" else 23 if name=="Title" else 12)
        style.paragraph_format.space_after=Pt(7)
    for style in document.styles:
        for border in style.element.xpath(".//w:pBdr"):
            border.getparent().remove(border)
    document.styles["Normal"].paragraph_format.line_spacing=1.08
    pending_page=False
    for kind,value in report_blocks(model,root):
        if kind=="page":
            pending_page=True
            continue
        if kind in ("title","heading","text"):
            paragraph=document.add_heading(value,level=1) if kind=="heading" else document.add_paragraph(value,"Title" if kind=="title" else None)
            if pending_page:paragraph.paragraph_format.page_break_before=True
            pending_page=False
        elif kind=="logo": document.add_picture(io.BytesIO(value),width=Inches(1.5))
        elif kind=="table":
            headers,rows=value
            table=document.add_table(rows=1,cols=len(headers));table.style="Table Grid"
            borders=OxmlElement("w:tblBorders")
            for edge in ("top","left","bottom","right","insideH","insideV"):
                node=OxmlElement("w:"+edge);node.set(qn("w:val"),"single");node.set(qn("w:sz"),"4");node.set(qn("w:color"),"D9D9D9");borders.append(node)
            table._tbl.tblPr.append(borders)
            for i,text in enumerate(headers):
                cell=table.rows[0].cells[i];cell.text=str(text)
                shading=OxmlElement("w:shd");shading.set(qn("w:fill"),"DCE9F3");cell._tc.get_or_add_tcPr().append(shading)
            header=OxmlElement("w:tblHeader");table.rows[0]._tr.get_or_add_trPr().append(header)
            for row in rows:
                cells=table.add_row().cells
                for i,text in enumerate(row): cells[i].text=str(text)
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for run in p.runs: run.font.size=Pt(8.5)
            document.add_paragraph()
        elif kind=="image":
            raw,description=value
            with Image.open(io.BytesIO(raw)) as im: w,h=im.size
            max_height=(5.2 if description.startswith("H1") else 5.8 if description.startswith("H3") else 4.7 if description.startswith("H4") else 6.7) if description.startswith("H") else 2.65
            scale=min(7.1/w,max_height/h)
            p=document.add_paragraph();p.paragraph_format.keep_with_next=True
            p.add_run().add_picture(io.BytesIO(raw),width=Inches(w*scale))
            cap=document.add_paragraph(description);cap.paragraph_format.space_after=Pt(9)
            for run in cap.runs:run.font.size=Pt(8)
    footer=section.footer.paragraphs[0]
    footer.text=f"EG1011 | TrussLab 2027 | {model.get('submission',{}).get('id','')[:12]} | Page "
    field=OxmlElement("w:fldSimple");field.set(qn("w:instr"),"PAGE");footer._p.append(field)
    output=io.BytesIO();document.save(output)
    return output.getvalue()


def build_bundle(model,root):
    issues=validation_issues(model)
    if issues: raise ValueError(" ".join(issues))
    payload=copy.deepcopy(model)
    payload["submission"]={"id":digest({k:v for k,v in model.items() if k!="submission"}),"generated_at":now()}
    stem=f"EG1011_Truss_2027_{model['student']['id']}"
    files={stem+"_answers.json":progress_bytes(payload),stem+"_report.pdf":build_pdf(payload,root),stem+"_report.docx":build_docx(payload,root)}
    manifest={"year":2027,"submission_id":payload["submission"]["id"],"sha256":{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in files.items():archive.writestr(name,raw)
        archive.writestr("checksums.json",json.dumps(manifest,indent=2))
    return {"zip":output.getvalue(),"pdf":files[stem+"_report.pdf"],"docx":files[stem+"_report.docx"],"json":files[stem+"_answers.json"],"stem":stem}


def read_bundle(raw):
    """Read without extracting uploaded paths or executing uploaded code."""
    if len(raw)>50*1024*1024:raise ValueError("Submission exceeds 50 MB")
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        model=parse_progress(raw)
        return model,["Answer file only: compare the checked data with the submitted report."],{}
    warnings=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist()
        if len(entries)>12 or sum(i.file_size for i in entries)>80*1024*1024:
            raise ValueError("Submission archive has too many files or is too large")
        names=[i.filename for i in entries]
        if len(set(names))!=len(names) or any("/" in name or "\\" in name for name in names):
            raise ValueError("Use the original TrussLab submission ZIP with files at its top level")
        answers=[name for name in names if name.endswith("_answers.json")]
        if len(answers)!=1:raise ValueError("Expected exactly one 2027 answer file")
        model=parse_progress(archive.read(answers[0]))
        if "checksums.json" in names:
            manifest=json.loads(archive.read("checksums.json"))
            for name,expected in manifest.get("sha256",{}).items():
                if name not in names or hashlib.sha256(archive.read(name)).hexdigest()!=expected:
                    warnings.append(f"Checksum mismatch: {name}. Compare the report and answer file manually.")
        else:warnings.append("No checksum file; compare the report and answer file manually.")
        files={name:archive.read(name) for name in names if name.endswith((".pdf",".docx"))}
    return model,warnings,files
