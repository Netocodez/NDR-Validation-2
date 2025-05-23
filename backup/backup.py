# ndr_validator.py
from flask import Flask, request, render_template_string
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import ParseError
from datetime import datetime
import os
import tempfile

app = Flask(__name__)

HTML_FORM = """
<!doctype html>
<title>NDR XML Validator</title>
<h2>NDR XML File Validator</h2>
<p><strong>Based on the Nigerian National Data Repository (NDR) validation rules – May 2025</strong></p>

<h3>Critical Rules</h3>
<ul>
  <li>Upload a <code>.xml</code> file (not zipped) that is well-formed and conforms to the NDR schema.</li>
  <li>Every <code>HIVEncounter</code> requires <em>VisitDate</em> and <em>ARVDrugRegimen/Code</em>.</li>
  <li><em>ARTStartDate</em> must not be later than any encounter date.</li>
  <li>
    <em>TBStatus</em> interpretation (per NDR):
    <ul>
      <li>0 = No signs/symptoms → IPT (INH) must be recorded on or after that date.</li>
      <li>1 = Presumptive TB → No IPT expected (patient under investigation).</li>
      <li>2 / 3 = Confirmed TB (Pulmonary / Extra-pulmonary) → TB treatment — IPT must NOT be given.</li>
      <li>4 = On TB treatment → IPT must NOT be given.</li>
    </ul>
  </li>
  <li>Each <code>LaboratoryReport</code> needs <em>LaboratoryTestIdentifier</em> and <em>CollectionDate</em>.</li>
  <li>If <em>PrescribedRegimenDuration</em> &gt; 30 days, <em>MultiMonthDispensing</em> (MMD) is mandatory.</li>
  <li>ARV codes in encounters must match the prescribed ART regimen for the same visit date.</li>
  <li>Reported patient age must agree with <em>DateOfBirth</em> and <em>DateOfLastReport</em> (±1 year).</li>
</ul>

<form method="post" enctype="multipart/form-data">
  <input type="file" name="file" accept=".xml" required>
  <input type="submit" value="Validate">
</form>

{% if error_message %}
  <p style="color:red;"><strong>{{ error_message }}</strong></p>
{% endif %}

{% if issues is not none %}
  <h3>Validation Report</h3>
  {% if issues %}
    <ul>
    {% for issue in issues %}
      <li>{{ issue }}</li>
    {% endfor %}
    </ul>
  {% else %}
    <p style="color:green;"><strong>No blocking issues found – file passes core NDR checks.</strong></p>
  {% endif %}
{% endif %}
"""

# ---------------------------------------------------------------------------
# Helper: extract all relevant pieces into a dictionary for easier validation
# ---------------------------------------------------------------------------
def extract_services(xml_path: str) -> dict:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    data = {
        "encounters": {},      # {date: {"arv": code, "tb": tb_status}}
        "regimens": {},        # {date: {...}}
        "labs": {},            # {date: {...}}
        "patient": {},         # dob, age, report_date
        "art_start": None
    }

    # Patient demographics
    demo = root.find(".//PatientDemographics")
    if demo is not None:
        data["patient"]["dob"] = demo.findtext("PatientDateOfBirth")

    common = root.find(".//CommonQuestions")
    if common is not None:
        data["patient"]["age"] = common.findtext("PatientAge")
        data["patient"]["report_date"] = common.findtext("DateOfLastReport")

    hiv_q = root.find(".//HIVQuestions")
    if hiv_q is not None:
        art_start = hiv_q.findtext("ARTStartDate")
        if art_start:
            try:
                data["art_start"] = datetime.strptime(art_start, "%Y-%m-%d")
            except ValueError:
                pass  # leave None if malformed

    # Regimens
    for reg in root.findall(".//Regimen"):
        date = reg.findtext("VisitDate") or "Unknown"
        data["regimens"][date] = {
            "code": reg.findtext("PrescribedRegimen/Code") or "",
            "type": reg.findtext("PrescribedRegimenTypeCode"),
            "duration": reg.findtext("PrescribedRegimenDuration"),
            "mmd": reg.findtext("MultiMonthDispensing")
        }

    # Encounters
    for enc in root.findall(".//HIVEncounter"):
        date = enc.findtext("VisitDate") or "Unknown"
        data["encounters"][date] = {
            "arv": enc.findtext("ARVDrugRegimen/Code"),
            "tb": enc.findtext("TBStatus")
        }

    # Labs
    for lab in root.findall(".//LaboratoryReport"):
        date = lab.findtext("VisitDate") or "Unknown"
        data["labs"][date] = {
            "test_id": lab.findtext("LaboratoryTestIdentifier"),
            "collected": lab.findtext("CollectionDate")
        }

    return data

# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------
def validate_ndr(data: dict) -> list:
    issues = []

    # --- convenience collections -------------------------------------------
    ipt_dates = {
        d for d, r in data["regimens"].items()
        if "INH" in (r["code"] or "").upper()
    }

    # --- encounter-level checks --------------------------------------------
    for date, enc in data["encounters"].items():

        if date == "Unknown":
            issues.append("❌ Encounter missing VisitDate.")
            continue

        # ARV presence
        if not enc["arv"]:
            issues.append(f"❌ {date}: ARVDrugRegimen/Code is missing.")

        # ART chronology
        art_start = data["art_start"]
        try:
            visit_dt = datetime.strptime(date, "%Y-%m-%d")
            if art_start and visit_dt < art_start:
                issues.append(f"❌ {date}: Encounter precedes ARTStartDate ({art_start.date()}).")
        except ValueError:
            issues.append(f"⚠️ {date}: VisitDate has invalid format.")

        # TB/IPT logic
        tb = enc["tb"]
        if tb is None:
            issues.append(f"❌ {date}: TBStatus is missing.")
        else:
            # convert dates to datetime for comparisons once
            try:
                visit_dt = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                visit_dt = None

            if tb == "0":           # No signs of TB → IPT required
                has_ipt = any(
                    datetime.strptime(d, "%Y-%m-%d") >= visit_dt
                    if visit_dt else False
                    for d in ipt_dates
                )
                if not has_ipt:
                    issues.append(f"❌ {date}: TBStatus 0 but no IPT (INH) regimen on/after this date.")
            elif tb in {"2", "3", "4"}:
                # IPT should NOT be given for confirmed/on-treatment TB
                conflicting_ipt = any(
                    datetime.strptime(d, "%Y-%m-%d") >= visit_dt
                    if visit_dt else True
                    for d in ipt_dates
                )
                if conflicting_ipt:
                    issues.append(f"❌ {date}: IPT recorded for a patient with TBStatus {tb} (should receive TB treatment, not IPT).")

    # --- regimen-level checks ----------------------------------------------
    for date, reg in data["regimens"].items():
        # Duration vs MMD
        try:
            dur = int(reg["duration"] or 0)
            if dur > 30 and not reg["mmd"]:
                issues.append(f"❌ {date}: Regimen duration >30 days but MultiMonthDispensing not specified.")
        except ValueError:
            issues.append(f"⚠️ {date}: Regimen duration is not numeric.")

    # --- encounter vs regimen ARV match ------------------------------------
    for date, enc in data["encounters"].items():
        reg = data["regimens"].get(date)
        if reg and reg["type"] == "ART":
            enc_arv = enc["arv"]
            reg_arv = reg["code"]
            if enc_arv and reg_arv and enc_arv != reg_arv:
                issues.append(
                    f"❌ {date}: ARV code mismatch (Encounter={enc_arv}, Regimen={reg_arv})."
                )

    # --- laboratory report completeness ------------------------------------
    for date, lab in data["labs"].items():
        if not lab["test_id"] or not lab["collected"]:
            issues.append(f"❌ {date}: LaboratoryReport missing test identifier or collection date.")

    # --- age vs DOB check ---------------------------------------------------
    dob = data["patient"].get("dob")
    age = data["patient"].get("age")
    rpt = data["patient"].get("report_date")
    try:
        dob_dt = datetime.strptime(dob, "%Y-%m-%d")
        rpt_dt = datetime.strptime(rpt, "%Y-%m-%d")
        calc_age = rpt_dt.year - dob_dt.year - (
            (rpt_dt.month, rpt_dt.day) < (dob_dt.month, dob_dt.day)
        )
        if abs(int(age) - calc_age) > 1:
            issues.append(f"❌ Reported age ({age}) vs calculated ({calc_age}) differs by >1 year.")
    except Exception:
        issues.append("⚠️ Unable to validate age (date format problem).")

    return issues

# ---------------------------------------------------------------------------
# Flask route
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def upload_file():
    error_message = None
    issues = None

    if request.method == "POST":
        f = request.files.get("file")
        if not f or f.filename == "":
            error_message = "❌ No file selected."
        elif not f.filename.lower().endswith(".xml"):
            error_message = "❌ Only .xml files are accepted."
        else:
            tmp_dir = tempfile.gettempdir()
            path = os.path.join(tmp_dir, f.filename)
            f.save(path)

            try:
                data = extract_services(path)
                issues = validate_ndr(data)
            except ParseError:
                error_message = "❌ Uploaded file is not well-formed XML."
            except Exception as exc:
                error_message = f"❌ Unexpected error: {exc}"
            finally:
                if os.path.exists(path):
                    os.remove(path)

    return render_template_string(HTML_FORM,
                                  error_message=error_message,
                                  issues=issues)

if __name__ == "__main__":
    app.run(debug=True)
