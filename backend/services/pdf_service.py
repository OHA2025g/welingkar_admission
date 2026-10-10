from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core import inr, ist_str, now_utc

CRIMSON = colors.HexColor("#8A1C1C")
INK = colors.HexColor("#1A1A1A")
LINE = colors.HexColor("#D9D3C7")
_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Title"], alignment=0, fontSize=18, textColor=INK, spaceAfter=2)
EYEBROW = ParagraphStyle("eb", parent=_ss["Normal"], fontSize=8, textColor=CRIMSON, leading=10)
H2 = ParagraphStyle("h2", parent=_ss["Heading3"], fontSize=11, textColor=CRIMSON, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("b", parent=_ss["Normal"], fontSize=9, leading=12, textColor=INK)
SMALL = ParagraphStyle("s", parent=_ss["Normal"], fontSize=7.5, leading=10, textColor=colors.HexColor("#666666"))


def _kv(rows):
    t = Table([[Paragraph(f"<b>{k}</b>", BODY), Paragraph(str(v if v not in (None, "") else "-"), BODY)] for k, v in rows],
              colWidths=[55 * mm, 115 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _grid(header, rows, widths):
    t = Table([[Paragraph(f"<b>{h}</b>", BODY) for h in header]] +
              [[Paragraph(str(c), BODY) for c in r] for r in rows], colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F1EA")),
                           ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _header(title: str, ref: str):
    return [Paragraph("WELINGKAR INSTITUTE OF MANAGEMENT DEVELOPMENT &amp; RESEARCH (WeSchool)", EYEBROW),
            Paragraph(title, H1), Paragraph(f"Reference: {ref} &nbsp;&nbsp;|&nbsp;&nbsp; Generated: {ist_str(now_utc())}", SMALL),
            Spacer(1, 6)]


def _footer(note: str):
    return [Spacer(1, 14), Paragraph(note, SMALL),
            Paragraph("Phase 0 proof-of-concept template. Final wording, numbering, taxes, logos and signatures "
                      "are subject to institute approval.", SMALL)]


def _build(story, title) -> bytes:
    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                      bottomMargin=18 * mm, title=title, author="WeSchool Admissions").build(story)
    return buf.getvalue()


def application_summary_pdf(a: dict) -> bytes:
    story = _header("Application Summary", f"{a['application_ref']} (v{a['snapshot_version']})")
    story += [Paragraph("Candidate", H2), _kv([
        ("Full name", a["candidate_name"]), ("Email", a["email"]), ("Mobile (WhatsApp)", a["mobile"]),
        ("Date of birth", a["dob"]), ("Gender", a["gender"]), ("Category", a["category"]),
        ("Correspondence address", a["address"])])]
    story += [Paragraph("Programme", H2), _kv([
        ("Programme", a["program"]), ("Specialisation preference", ", ".join(a["specialisations"])),
        ("Admission cycle", a["cycle"]), ("Application status", a["status"].title()),
        ("Submitted at", ist_str(a.get("submitted_at")))])]
    story += [Paragraph("Education", H2), _grid(["Level", "Board / University", "Year", "Score"],
                                                [[e["level"], e["board"], e["year"], e["score"]] for e in a["education"]],
                                                [35 * mm, 75 * mm, 25 * mm, 35 * mm])]
    story += [Paragraph("Work experience", H2), _grid(["Organisation", "Role", "Months"],
                                                      [[w["org"], w["role"], w["months"]] for w in a["work"]] or [["-", "-", "-"]],
                                                      [75 * mm, 65 * mm, 30 * mm])]
    story += [Paragraph("Entrance examinations", H2), _grid(["Exam", "Year", "Percentile / Score"],
                                                            [[x["exam"], x["year"], x["score"]] for x in a["exams"]],
                                                            [75 * mm, 30 * mm, 65 * mm])]
    story += _footer("This summary reflects the submitted snapshot stored on the server at the time of generation.")
    return _build(story, f"Application Summary {a['application_ref']}")


def receipt_pdf(o: dict, refunds: list[dict]) -> bytes:
    story = _header("Payment Receipt", o["order_ref"])
    story += [Paragraph("Payer", H2), _kv([
        ("Candidate name", o["candidate_name"]), ("Email", o["candidate_email"]),
        ("Application reference", o.get("application_ref"))])]
    story += [Paragraph("Payment", H2), _kv([
        ("Description", o["description"]), ("Amount paid", inr(o["amount_paise"])), ("Currency", o["currency"]),
        *([("Mode", f"Offline · {(o.get('offline_mode') or '').upper()}"), ("Transaction ref", o.get("txn_ref")),
           ("Transaction date", o.get("txn_date"))] if o.get("origin") == "offline" else
          [("Gateway", f"{o['provider'].title()} (test mode)"), ("Gateway session", o.get("provider_session_id")),
           ("Gateway payment ID", o.get("provider_payment_intent"))]),
        ("Verified via", o.get("verified_via")),
        ("Paid at", ist_str(o.get("paid_at"))), ("Status", o["status"].upper())])]
    done = [r for r in refunds if r["status"] == "succeeded"]
    if refunds:
        story += [Paragraph("Refunds", H2), _grid(["Refund ref", "Amount", "Status", "Date"],
                                                  [[r["refund_ref"], inr(r["amount_paise"]), r["status"], ist_str(r["created_at"])]
                                                   for r in refunds], [50 * mm, 40 * mm, 35 * mm, 45 * mm])]
    net = o["amount_paise"] - sum(r["amount_paise"] for r in done)
    story += [Spacer(1, 6), _kv([("Total refunded", inr(o["amount_paise"] - net)), ("Net amount retained", inr(net))])]
    story += _footer("Receipt issued only for payments verified with the gateway. Client redirects are not proof of payment.")
    return _build(story, f"Receipt {o['order_ref']}")


def _img(data, w, h):
    from reportlab.platypus import Image as RLImage
    return RLImage(BytesIO(data), width=w, height=h, kind="proportional") if data else Paragraph("Not uploaded", SMALL)


def application_pdf(snap: dict, version: int, submitted_at, photo: bytes | None, signature: bytes | None) -> bytes:
    s, c = snap["sections"], snap["candidate"]
    p, f, ct, e = s.get("personal", {}), s.get("family", {}), s.get("contact", {}), s.get("education", {})
    story = _header("Application Form (Submitted)", f"{snap['application_ref']} · version {version}")
    top = Table([[_kv([("Candidate", p.get("full_name") or c["name"]), ("Candidate ID", c.get("candidate_ref")),
                       ("Cycle", snap["cycle_code"]), ("Submitted at", ist_str(submitted_at)),
                       ("Email", c.get("email")), ("Mobile", c.get("mobile"))]), _img(photo, 30 * mm, 38 * mm)]],
                colWidths=[135 * mm, 35 * mm])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [top, Paragraph("Personal details", H2), _kv([
        ("Date of birth", p.get("dob")), ("Gender", p.get("gender")), ("Category", p.get("category")),
        ("Nationality", p.get("nationality")), ("Person with disability", "Yes" if p.get("pwd") else "No")])]
    story += [Paragraph("Family", H2), _kv([
        ("Father", f"{f.get('father_name', '')} ({f.get('father_occupation', '')})"),
        ("Mother", f"{f.get('mother_name', '')} ({f.get('mother_occupation', '')})"),
        ("Annual family income", inr(int((f.get("annual_family_income_inr") or 0) * 100))),
        ("Siblings", ", ".join(f"{x['name']} ({x['relation']})" for x in f.get("siblings", [])) or "None")])]
    story += [Paragraph("Contact", H2), _kv([
        ("Address", ", ".join(filter(None, [ct.get("address_line1"), ct.get("address_line2"), ct.get("city"),
                                            ct.get("state"), ct.get("pincode")]))),
        ("Emergency contact", f"{ct.get('emergency_contact_name', '')} · {ct.get('emergency_contact_mobile', '')}")])]
    g = e.get("graduation", {})
    story += [Paragraph("Education", H2), _grid(["Level", "Board / University", "Year", "Score"], [
        ["Class X", e.get("class_x", {}).get("board"), e.get("class_x", {}).get("year"), f"{e.get('class_x', {}).get('percentage')}%"],
        ["Class XII", e.get("class_xii", {}).get("board"), e.get("class_xii", {}).get("year"), f"{e.get('class_xii', {}).get('percentage')}%"],
        [f"{g.get('degree', '')} {g.get('discipline', '')}", g.get("university"), f"{g.get('year')} ({g.get('status', '').replace('_', ' ')})",
         f"{g.get('score')} {'%' if g.get('score_type') == 'percentage' else 'CGPA'}"]], [45 * mm, 65 * mm, 30 * mm, 30 * mm])]
    w = s.get("work", {})
    story += [Paragraph("Work experience", H2), _grid(["Organisation", "Designation", "Sector", "From – To"],
              [[x["organization"], x["designation"], x["sector"], f"{x['start']} – {x['end'] or 'present'}"]
               for x in w.get("experiences", [])] or [["No work experience", "", "", ""]], [55 * mm, 45 * mm, 35 * mm, 35 * mm])]
    story += [Paragraph("Entrance examinations", H2), _grid(["Exam", "Year", "Roll no.", "Status", "Score / Percentile"],
              [[x["exam"], x["year"], x["roll_number"], x["status"].replace("_", " "),
                f"{x.get('score') or '-'} / {x.get('percentile') or '-'}"] for x in s.get("exams", {}).get("exams", [])],
              [25 * mm, 20 * mm, 45 * mm, 35 * mm, 45 * mm])]
    story += [Paragraph("Programme preferences (ranked)", H2),
              _grid(["Rank", "Programme"], [[i + 1, n] for i, n in enumerate(snap.get("preference_names", []))], [20 * mm, 150 * mm])]
    story += [Spacer(1, 10), Paragraph("Signature", H2), _img(signature, 50 * mm, 18 * mm)]
    story += _footer("This document reflects the immutable submitted version stored on the server. Drafts are never printed as submissions.")
    return _build(story, f"Application {snap['application_ref']}")


def hall_ticket_pdf(c: dict, items: list[dict], ticket_no: str) -> bytes:
    story = _header("Interview Hall Ticket", ticket_no)
    story += [_kv([("Candidate", c["name"]), ("Candidate ID", c.get("candidate_ref")), ("Application", c["application_ref"])])]
    for it in items:
        s = it["session"]
        story += [Paragraph(s["type_label"], H2), _kv([
            ("Date", s["date"]), ("Session time", f"{s['start']} - {s['end']} IST"), ("Reporting time", f"30 minutes before {s['start']} IST"),
            ("Venue", f"{s['location']}, {s.get('address') or ''}"), ("Room", s["room"]),
            ("Booking version", f"v{it['version']}" + (f" (rescheduled {it['reschedules']}x)" if it.get("reschedules") else ""))])]
    story += [Paragraph("Instructions", H2), Paragraph(
        "Carry this hall ticket and a government photo ID. Mobile phones must be switched off during the assessment. "
        "Only the latest booking version shown in the portal is valid; any earlier hall ticket is void.", BODY)]
    story += _footer(f"Ticket {ticket_no}. Regenerated automatically after every authorised reschedule.")
    return _build(story, f"Hall ticket {ticket_no}")


def result_pdf(c: dict, rows: list[dict], version: int, published_at) -> bytes:
    story = _header("Admission Result", f"{c.get('candidate_ref')} · published result v{version}")
    story += [_kv([("Candidate", c["name"]), ("Candidate ID", c.get("candidate_ref")), ("Published", ist_str(published_at))])]
    story += [Paragraph("Programme outcomes", H2), _grid(
        ["Choice", "Programme", "Outcome", "Merit rank", "TFW"],
        [[r["choice"], r["program_name"], r["outcome_label"], r["rank"] or "-",
          f"{r['tfw_outcome_label']} (rank {r['tfw_rank']})" if r.get("tfw_rank") else "-"] for r in rows],
        [16 * mm, 60 * mm, 44 * mm, 20 * mm, 30 * mm])]
    story += _footer("This result reflects the approved and published result version only. Generated drafts never change it.")
    return _build(story, "WeSchool admission result")


def ga_batch_pdf(s: dict, rubric: list[dict], rows: list[dict]) -> bytes:
    story = _header("GA Batch Report", f"{s['date']} {s['start']}-{s['end']} · {s['location']} · {s['room']}")
    story += [Paragraph("Panelists: " + ", ".join(p["name"] for p in s.get("panelists", [])), BODY)]
    head = ["Candidate", "Panelist"] + [c["label"] for c in rubric] + ["Total", "Status"]
    w = 170 / len(head)
    story += [Spacer(1, 6), _grid(head, [[f"{r['candidate_name']} ({r['candidate_ref']})", r["panelist_name"]] +
                                         [r["scores"].get(c["key"], "-") for c in rubric] + [f"{r['total']:g}/{r['max_total']}", r["status"]]
                                         for r in rows] or [["No scores yet"] + [""] * (len(head) - 1)], [w * mm] * len(head))]
    story += _footer("Printable batch report. Scores reflect the current score version; corrections are audited.")
    return _build(story, "GA batch report")


def cancellation_receipt_pdf(c: dict, x: dict, ref: str) -> bytes:
    q = x.get("quote") or {}
    story = _header("Seat Cancellation Receipt", ref)
    story += [_kv([("Candidate", c["name"]), ("Candidate ID", c.get("candidate_ref")), ("Application", c["application_ref"])])]
    story += [Paragraph("Cancellation", H2), _kv([
        ("Programme", x["program_code"]), ("Status", x["status"].replace("_", " ").title()), ("Reason", x["reason"]),
        ("Requested at", ist_str(x["created_at"])), ("Reviewed at", ist_str(x.get("reviewed_at"))),
        ("Seat released", "Yes" if x.get("seat_released") else "No")])]
    story += [Paragraph("Refund computation", H2), _kv([
        ("Refund policy", f"v{q.get('policy_version')} · {q.get('tier')}"), ("Days before programme start", q.get("days_before_start")),
        ("Admission fee paid", inr(q.get("paid_paise", 0))), ("Processing fee", inr(q.get("processing_fee_paise", 0))),
        ("Total deduction", inr(q.get("deduction_paise", 0))), ("Already refunded", inr(q.get("already_refunded_paise", 0))),
        ("Refund due", inr(q.get("refund_paise", 0))),
        ("Refund status", (x.get("refund_status") or "pending").upper()),
        ("Bank", f"{x['bank']['bank_name']} · {x['bank']['number']} · {x['bank']['ifsc']}")])]
    story += _footer("Refunds are executed by Accounts to the registered bank account. Gateway refund execution in this build is MOCKED.")
    return _build(story, f"Cancellation receipt {ref}")


def allotment_receipt_pdf(c: dict, a: dict, ref: str) -> bytes:
    story = _header("Seat Allotment Receipt", ref)
    story += [_kv([("Candidate", c["name"]), ("Candidate ID", c.get("candidate_ref")), ("Application", c["application_ref"])])]
    story += [Paragraph("Allotment", H2), _kv([
        ("Programme", f"{a['program_name']} ({a['program_code']})"), ("Campus", a.get("campus")), ("Round", a["batch_name"]),
        ("Allotment status", a["status"].replace("_", " ").title()), ("Committed at", ist_str(a["committed_at"])),
        ("Allotment version", f"v{a['version']}"), ("Receipt version", f"r{a['receipt_version']}")])]
    story += [Paragraph("Next steps", H2), Paragraph(
        "Upload your admission documents and complete the admission fee payment within the published timeline. "
        "A provisional allotment is subject to completion of document verification.", BODY)]
    story += _footer("Only the latest receipt version shown in the portal is valid. A betterment or cancellation voids this receipt.")
    return _build(story, f"Allotment receipt {ref}")
