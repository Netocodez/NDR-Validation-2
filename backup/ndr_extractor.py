import xml.etree.ElementTree as ET
from datetime import datetime

def extract_services(xml_path: str) -> dict:
    """Parse NDR XML file and extract patient, encounters, regimens, labs, and flags."""
    
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

    # Extract patient demographics
    demo = root.find(".//PatientDemographics")
    if demo is not None:
        patient = {
            "id": demo.findtext("PatientIdentifier"),
            "dob": demo.findtext("PatientDateOfBirth"),
            "sex": demo.findtext("PatientSexCode"),
            "facility_name": demo.findtext(".//FacilityName"),
            "facility_id": demo.findtext(".//FacilityID"),
            "hn": None,
            "tb_id": None,
            "other_ids": {}
        }

        # Extract other patient identifiers, flag unknown types
        for identifier in demo.findall(".//OtherPatientIdentifiers/Identifier"):
            id_type = identifier.findtext("IDTypeCode")
            id_number = identifier.findtext("IDNumber")

            if id_type == "HN":
                patient["hn"] = id_number
            elif id_type == "TB":
                patient["tb_id"] = id_number
            elif id_type and id_number:
                patient["other_ids"][id_type] = id_number
                # Flag any non-standard identifier types
                if id_type not in ("HN", "TB"):
                    data["validation_flags"].append(f"Invalid identifier: {id_type}")

        data["patient"] = patient

    # Extract common patient info (age, report date)
    common = root.find(".//CommonQuestions")
    if common is not None:
        data["patient"]["age"] = common.findtext("PatientAge")
        data["patient"]["report_date"] = common.findtext("DateOfLastReport")

    # Extract patient address info and flag missing parts
    address = root.find(".//PatientAddress")
    if address is not None:
        data["patient"].update({
            "addresscode": address.findtext("AddressTypeCode"),
            "lgacode": address.findtext("LGACode"),
            "statecode": address.findtext("StateCode"),
            "countrycode": address.findtext("CountryCode")
        })

        for field in ["addresscode", "lgacode", "statecode", "countrycode"]:
            if not data["patient"].get(field):
                data["validation_flags"].append(f"Missing {field.capitalize()} in PatientAddress")
    else:
        data["validation_flags"].append("Missing PatientAddress element")

    # Extract ART start date and child height at ART start
    hiv_q = root.find(".//HIVQuestions")
    if hiv_q is not None:
        art_start_str = hiv_q.findtext("ARTStartDate")
        if art_start_str:
            try:
                data["art_start"] = datetime.strptime(art_start_str, "%Y-%m-%d")
            except ValueError:
                data["validation_flags"].append("Invalid ARTStartDate format")
        else:
            data["validation_flags"].append("Missing ARTStartDate")

        height_at_art_start = hiv_q.findtext("ChildHeightAtARTStart")
        if height_at_art_start:
            data["patient"]["height_at_art_start"] = height_at_art_start

    # Extract regimens keyed by visit date
    for reg in root.findall(".//Regimen"):
        date = reg.findtext("VisitDate") or "Unknown"
        data["regimens"][date] = {
            "code": reg.findtext("PrescribedRegimen/Code") or "",
            "codetext": reg.findtext("PrescribedRegimen/CodeDescTxt") or "",
            "type": reg.findtext("PrescribedRegimenTypeCode"),
            "duration": reg.findtext("PrescribedRegimenDuration"),
            "mmd": reg.findtext("MultiMonthDispensing")
        }

    # Extract encounters keyed by visit date
    for enc in root.findall(".//HIVEncounter"):
        date = enc.findtext("VisitDate") or "Unknown"
        data["encounters"][date] = {
            "arv": enc.findtext("ARVDrugRegimen/Code"),
            "tb": enc.findtext("TBStatus"),
            "height": enc.findtext("ChildHeight"),
            "who_stage": enc.findtext("WHOClinicalStage"),
            "weight": enc.findtext("Weight"),
            "cd4": enc.findtext("CD4Count"),
            "functional_status": enc.findtext("FunctionalStatus"),
            "pregnancy": enc.findtext("PregnancyStatus")
        }

    # Extract lab reports keyed by visit date
    for lab in root.findall(".//LaboratoryReport"):
        date = lab.findtext("VisitDate") or "Unknown"
        data["labs"][date] = {
            "test_id": lab.findtext("LaboratoryTestIdentifier"),
            "collected": lab.findtext("CollectionDate")
        }

    return data
