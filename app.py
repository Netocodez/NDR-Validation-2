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
<style>
  body {
    font-family: Arial, sans-serif;
    margin: 2rem;
    background: #f9f9f9;
  }
  h2 {
    color: #333;
  }
  button.toggle-rules {
    background-color: #0052cc;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    cursor: pointer;
    border-radius: 4px;
    margin-bottom: 1rem;
  }
  button.toggle-rules:hover {
    background-color: #003d99;
  }
  #critical-rules {
    display: none;
    background: white;
    border: 2px solid #0052cc;
    border-radius: 8px;
    padding: 1rem 1.5rem;
    max-width: 600px;
    box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    margin-bottom: 2rem;
  }
  #critical-rules ul {
    margin-left: 1.2rem;
  }

  form {
    margin-bottom: 2rem;
  }

  /* Layout for patient bio and issues side by side */
  .results-container {
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
    margin-top: 2rem;
  }
  .patient-bio, .validation-report {
    background: white;
    padding: 1rem 1.5rem;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    flex: 1 1 300px;
  }
  .patient-bio ul, .validation-report ul {
    list-style-type: disc;
    margin-left: 1.2rem;
  }
  .validation-report p {
    color: green;
    font-weight: bold;
  }
  .error-message {
    color: red;
    font-weight: bold;
  }
</style>

<h2>NDR XML File Validator (Upload individual xml file)</h2>

<button class="toggle-rules" onclick="toggleRules()">Show Critical Rules</button>

<div id="critical-rules">
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
</div>

<form method="post" enctype="multipart/form-data">
  <input type="file" name="file" accept=".xml" required>
  <input type="submit" value="Validate">
</form>

{% if error_message %}
  <p class="error-message">{{ error_message }}</p>
{% endif %}

{% if patient or issues is not none %}
  <div class="results-container">
    {% if patient %}
    <div class="patient-bio">
      <h3>Patient Bio</h3>
      <ul>
        <li><strong>Patient ID:</strong> {{ patient.id }}</li>
        <li><strong>Hospital Number (HN):</strong> {{ patient.hn or "N/A" }}</li>
        <li><strong>TB Identifier:</strong> {{ patient.tb_id or "N/A" }}</li>
        <li><strong>Sex:</strong> {{ patient.sex }}</li>
        <li><strong>Date of Birth:</strong> {{ patient.dob }}</li>
        <li><strong>Reported Age:</strong> {{ patient.age }}</li>
        <li><strong>Date of Last Report:</strong> {{ patient.report_date }}</li>
        <li><strong>Facility Name:</strong> {{ patient.facility_name }}</li>
        <li><strong>Facility ID:</strong> {{ patient.facility_id }}</li>
        <li><strong>ART Start Date:</strong> {{ art_start }}</li>
      </ul>
    </div>
    {% endif %}

    {% if issues is not none %}
    <div class="validation-report">
      <h3>Validation Report</h3>
      {% if issues %}
        <ul>
        {% for issue in issues %}
          <li>{{ issue }}</li>
        {% endfor %}
        </ul>
      {% else %}
        <p>No blocking issues found – file passes core NDR checks.</p>
      {% endif %}
    </div>
    {% endif %}
  </div>
{% endif %}

<script>
function toggleRules() {
  const rules = document.getElementById('critical-rules');
  const btn = document.querySelector('.toggle-rules');
  if (rules.style.display === 'none' || rules.style.display === '') {
    rules.style.display = 'block';
    btn.textContent = 'Hide Critical Rules';
  } else {
    rules.style.display = 'none';
    btn.textContent = 'Show Critical Rules';
  }
}
</script>

"""

# ---------------------------------------------------------------------------
# Extract patient and service data
# ---------------------------------------------------------------------------
def extract_services(xml_path: str) -> dict:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    data = {
        "encounters": {},
        "regimens": {},
        "labs": {},
        "patient": {},
        "art_start": None
    }

    demo = root.find(".//PatientDemographics")
    if demo is not None:
        data["patient"] = {
            "id": demo.findtext("PatientIdentifier"),
            "dob": demo.findtext("PatientDateOfBirth"),
            "sex": demo.findtext("PatientSexCode"),
            "facility_name": demo.findtext(".//FacilityName"),
            "facility_id": demo.findtext(".//FacilityID"),
            "hn": None,
            "tb_id": None
        }

        for identifier in demo.findall(".//OtherPatientIdentifiers/Identifier"):
            id_type = identifier.findtext("IDTypeCode")
            id_number = identifier.findtext("IDNumber")
            if id_type == "HN":
                data["patient"]["hn"] = id_number
            elif id_type == "TB":
                data["patient"]["tb_id"] = id_number


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
                pass

    for reg in root.findall(".//Regimen"):
        date = reg.findtext("VisitDate") or "Unknown"
        data["regimens"][date] = {
            "code": reg.findtext("PrescribedRegimen/Code") or "",
            "type": reg.findtext("PrescribedRegimenTypeCode"),
            "duration": reg.findtext("PrescribedRegimenDuration"),
            "mmd": reg.findtext("MultiMonthDispensing")
        }

    for enc in root.findall(".//HIVEncounter"):
        date = enc.findtext("VisitDate") or "Unknown"
        data["encounters"][date] = {
            "arv": enc.findtext("ARVDrugRegimen/Code"),
            "tb": enc.findtext("TBStatus")
        }

    for lab in root.findall(".//LaboratoryReport"):
        date = lab.findtext("VisitDate") or "Unknown"
        data["labs"][date] = {
            "test_id": lab.findtext("LaboratoryTestIdentifier"),
            "collected": lab.findtext("CollectionDate")
        }

    return data

# ---------------------------------------------------------------------------
# NDR Validator
# ---------------------------------------------------------------------------
def validate_ndr(data: dict) -> list:
    issues = []
    ipt_dates = {
        d for d, r in data["regimens"].items()
        if "INH" in (r["code"] or "").upper()
    }

    for date, enc in data["encounters"].items():
        if date == "Unknown":
            issues.append("❌ Encounter missing VisitDate.")
            continue

        if not enc["arv"]:
            issues.append(f"❌ {date}: ARVDrugRegimen/Code is missing.")

        art_start = data["art_start"]
        try:
            visit_dt = datetime.strptime(date, "%Y-%m-%d")
            if art_start and visit_dt < art_start:
                issues.append(f"❌ {date}: Encounter precedes ARTStartDate ({art_start.date()}).")
        except ValueError:
            issues.append(f"⚠️ {date}: VisitDate has invalid format.")

        tb = enc["tb"]
        if tb is None:
            issues.append(f"❌ {date}: TBStatus is missing.")
        else:
            try:
                visit_dt = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                visit_dt = None

            if tb == "0":
                has_ipt = any(
                    datetime.strptime(d, "%Y-%m-%d") >= visit_dt if visit_dt else False
                    for d in ipt_dates
                )
                if not has_ipt:
                    issues.append(f"❌ {date}: TBStatus 0 but no IPT (INH) regimen on/after this date.")
            elif tb in {"2", "3", "4"}:
                conflicting_ipt = any(
                    datetime.strptime(d, "%Y-%m-%d") >= visit_dt if visit_dt else True
                    for d in ipt_dates
                )
                if conflicting_ipt:
                    issues.append(f"❌ {date}: IPT recorded for TBStatus {tb} (should receive TB treatment).")

    for date, reg in data["regimens"].items():
        try:
            dur = int(reg["duration"] or 0)
            if dur > 30 and not reg["mmd"]:
                issues.append(f"❌ {date}: Regimen duration >30 days but MMD not specified.")
        except ValueError:
            issues.append(f"⚠️ {date}: Regimen duration not numeric.")

    for date, enc in data["encounters"].items():
        reg = data["regimens"].get(date)
        if reg and reg["type"] == "ART":
            if enc["arv"] and reg["code"] and enc["arv"] != reg["code"]:
                issues.append(f"❌ {date}: ARV code mismatch (Encounter={enc['arv']}, Regimen={reg['code']}).")

    for date, lab in data["labs"].items():
        if not lab["test_id"] or not lab["collected"]:
            issues.append(f"❌ {date}: Lab report missing test ID or collection date.")

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
        issues.append("⚠️ Unable to validate age (date format issue).")

    return issues

# ---------------------------------------------------------------------------
# Flask route
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def upload_file():
    error_message = None
    issues = None
    patient = None
    art_start = None

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
                patient = data.get("patient")
                art_start = data.get("art_start")
                if art_start:
                    art_start = art_start.date()
            except ParseError:
                error_message = "❌ Uploaded file is not well-formed XML."
            except Exception as exc:
                error_message = f"❌ Unexpected error: {exc}"
            finally:
                if os.path.exists(path):
                    os.remove(path)

    return render_template_string(HTML_FORM,
                                  error_message=error_message,
                                  issues=issues,
                                  patient=patient,
                                  art_start=art_start)

if __name__ == "__main__":
    app.run(debug=True)
