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
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>NDR XML Validator</title>
<style>
  /* Reset & base */
  *, *::before, *::after {
    box-sizing: border-box;
  }

  body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background-color: #f9f9f9;
    margin: 0;
    padding: 2rem 1rem;
    color: #333;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 100vh;
  }

  h1 {
    font-weight: 700;
    margin-bottom: 1rem;
    text-align: center;
    color: #222;
  }

  /* Critical rules toggle button */
  button.toggle-rules {
    background-color: #0052cc;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    cursor: pointer;
    border-radius: 5px;
    font-weight: 600;
    font-size: 1rem;
    margin-bottom: 1rem;
    transition: background-color 0.3s ease;
  }
  button.toggle-rules:hover,
  button.toggle-rules:focus {
    background-color: #003d99;
    outline: none;
  }

  /* Critical rules container */
  #critical-rules {
    display: none;
    background: white;
    border: 2px solid #0052cc;
    border-radius: 8px;
    padding: 1.2rem 1.5rem;
    max-width: 650px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    margin-bottom: 2rem;
    line-height: 1.5;
  }
  #critical-rules h2 {
    margin-top: 0;
    margin-bottom: 0.5rem;
    color: #0052cc;
  }
  #critical-rules ul {
    padding-left: 1.2rem;
  }
  #critical-rules ul ul {
    padding-left: 1.2rem;
    list-style-type: circle;
  }

  /* Form styling */
  form {
    background: white;
    padding: 1.5rem 2rem;
    border-radius: 10px;
    box-shadow: 0 6px 20px rgba(0, 123, 255, 0.1);
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: center;
    justify-content: center;
    max-width: 650px;
    width: 100%;
    font-weight: 600;
  }

  form input[type="file"] {
    flex-grow: 1;
    cursor: pointer;
    font-size: 1rem;
    padding: 0.4rem;
  }

  form button[type="submit"] {
    padding: 12px 24px;
    font-size: 1rem;
    font-weight: 700;
    background: linear-gradient(to right, #007BFF, #0056b3);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    box-shadow: 0 2px 10px rgba(0, 123, 255, 0.3);
    transition: background 0.3s ease, transform 0.2s ease;
    white-space: nowrap;
  }
  form button[type="submit"]:hover,
  form button[type="submit"]:focus {
    background: linear-gradient(to right, #0056b3, #003d80);
    transform: scale(1.05);
    outline: none;
  }

  /* Messages */
  .error-message {
    color: #d93025;
    font-weight: 700;
    margin-top: 1rem;
    text-align: center;
    max-width: 650px;
  }

  /* Results container */
  .results-container {
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
    margin-top: 2rem;
    max-width: 900px;
    width: 100%;
    justify-content: center;
  }
  .patient-bio, .validation-report {
    background: white;
    padding: 1.5rem 2rem;
    border-radius: 8px;
    box-shadow: 0 3px 12px rgba(0,0,0,0.1);
    flex: 1 1 350px;
    min-width: 280px;
  }
  .patient-bio h3,
  .validation-report h3 {
    margin-top: 0;
    color: #0052cc;
    font-weight: 700;
  }
  .patient-bio ul,
  .validation-report ul {
    list-style-type: disc;
    padding-left: 1.5rem;
    line-height: 1.4;
  }
  .validation-report p {
    color: #1a7f37;
    font-weight: 700;
    margin: 0.5rem 0 0 0;
  }

  /* Responsive adjustments */
  @media (max-width: 480px) {
    form {
      flex-direction: column;
      gap: 0.8rem;
      padding: 1rem 1.2rem;
    }
    form button[type="submit"] {
      width: 100%;
    }
    .results-container {
      flex-direction: column;
      align-items: center;
    }
  }
</style>
</head>
<body>

<header>
  <h1>NDR XML File Validator</h1>
  <h3>Upload an individual <code>.xml</code> file conforming to the Nigerian National Data Repository (NDR) validation rules.<h3>
</header>

<form method="post" enctype="multipart/form-data" novalidate>
  <input type="file" name="file" accept=".xml" required aria-label="Upload XML file" />
  <button type="submit">Validate</button>
</form>

<!-- Placeholder for error message -->
{% if error_message %}
  <p class="error-message" role="alert">{{ error_message }}</p>
{% endif %}

<!-- Results Section -->
{% if patient or issues is not none %}
  <section class="results-container" aria-live="polite">
    {% if patient %}
    <article class="patient-bio" aria-label="Patient Bio Information">
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
    </article>
    {% endif %}

    {% if issues is not none %}
    <article class="validation-report" aria-label="Validation Report">
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
    </article>
    {% endif %}
  </section>
{% endif %}

<br>

<button class="toggle-rules" aria-expanded="false" aria-controls="critical-rules" onclick="toggleRules()">Show Critical Rules</button>

<section id="critical-rules" aria-live="polite" role="region" aria-label="Critical Validation Rules">
  <h2>Critical Rules</h2>
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
</section>

<script>
  function toggleRules() {
    const rules = document.getElementById('critical-rules');
    const btn = document.querySelector('.toggle-rules');
    const isHidden = rules.style.display === 'none' || rules.style.display === '';
    rules.style.display = isHidden ? 'block' : 'none';
    btn.textContent = isHidden ? 'Hide Critical Rules' : 'Show Critical Rules';
    btn.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
  }

  // Show critical rules by default on page load
  window.addEventListener('DOMContentLoaded', () => {
    const rules = document.getElementById('critical-rules');
    const btn = document.querySelector('.toggle-rules');
    rules.style.display = 'block';
    btn.textContent = 'Hide Critical Rules';
    btn.setAttribute('aria-expanded', 'true');
  });
</script>

</body>
</html>
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
        "art_start": None,
        "validation_flags": []
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
    print("HIVQuestions found:", hiv_q is not None)

    if hiv_q is not None:
        art_start = hiv_q.findtext("ARTStartDate")
        print("ARTStartDate:", repr(art_start))

        if art_start:
            try:
                data["art_start"] = datetime.strptime(art_start, "%Y-%m-%d")
            except ValueError:
                print("Invalid date format for ARTStartDate")
        else:
            data["validation_flags"].append("Missing ARTStartDate")
            print("Flag added: Missing ARTStartDate")
    else:
        data["validation_flags"].append("Missing HIVQuestions section")
        print("Flag added: Missing HIVQuestions section")

    print("Current validation flags:", data.get("validation_flags"))



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
            "tb": enc.findtext("TBStatus"),
            "height": enc.findtext("ChildHeight")
        }

    for lab in root.findall(".//LaboratoryReport"):
        date = lab.findtext("VisitDate") or "Unknown"
        data["labs"][date] = {
            "test_id": lab.findtext("LaboratoryTestIdentifier"),
            "collected": lab.findtext("CollectionDate")
        }
        
    # Print confirmation and key extracted values
    print(data.get("validation_flags", []))
    print("Extracted patient ID:", data["patient"].get("id"))
    print("ChildHeightAtARTStart:", data["patient"].get("height_at_art_start"))
    print("ChildHeight values from encounters:")
    for date, encounter in data["encounters"].items():
        print(f"  Date: {date}, ChildHeight: {encounter.get('height')}")

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
            if "Missing ARTStartDate" in data.get("validation_flags", []):
              issues.append("❌ ARTStartDate is missing in HIVQuestions section.")          
            if art_start and visit_dt < art_start:
                issues.append(f"❌ {date}: Encounter precedes ARTStartDate ({art_start.date()}).")
            if not art_start:
                issues.append(f"❌ {date}: ARTStartDate Missing({art_start.date()}).")
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
        issues.append("Unable to validate age (date format issue).")
        
    
    # Validate height_at_art_start if available
    height_at_art_start = data["patient"].get("height_at_art_start")
    art_start = data.get("art_start")
    if height_at_art_start:
        print(f"Checking height_at_art_start: {height_at_art_start}")
        try:
            height_val = float(height_at_art_start)
            print(f"Parsed height_at_art_start: {height_val}")
            if height_val > 200:
                art_start_str = art_start.strftime("%Y-%m-%d") if art_start else "Unknown date"
                print(f"Issue found: Child height_at_art_start > 200")
                issues.append(f"ART Start ({art_start_str}): Child Height at ART start > 200 ({height_val} cm).")
        except (TypeError, ValueError):
            print(f"Invalid Child height_at_art_start value: {height_at_art_start}")


    # Existing encounter height validations
    for date, enc in data["encounters"].items():
        height = enc.get("height")
        print(f"Checking height for {date}: {height}")
        try:
            height_val = float(height)
            print(f"Parsed height: {height_val}")
            if height_val > 200:
                print(f"Issue found: Height > 200 on {date}")
                issues.append(f"{date}: Child Height > 200 ({height_val}).")
        except (TypeError, ValueError):
            print(f"Child Height value invalid or missing for {date}: {height}")

    print("Validation issues found:", issues)

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
