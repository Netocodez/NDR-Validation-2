import xml.etree.ElementTree as ET
from datetime import datetime
from xml.etree.ElementTree import ParseError

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
            "tb_id": None,
            "other_ids": {}  # initialize container for other IDs
        }

        for identifier in demo.findall(".//OtherPatientIdentifiers/Identifier"):
            id_type = identifier.findtext("IDTypeCode")
            id_number = identifier.findtext("IDNumber")

            if id_type == "HN":
                data["patient"]["hn"] = id_number
            elif id_type == "TB":
                data["patient"]["tb_id"] = id_number
            else:
                if id_type and id_number:
                    data["patient"]["other_ids"][id_type] = id_number
                if id_type and id_type not in ("HN", "TB"):
                    data["validation_flags"].append(f"Invalid identifier: {id_type}")


    common = root.find(".//CommonQuestions")
    if common is not None:
        data["patient"]["age"] = common.findtext("PatientAge")
        data["patient"]["report_date"] = common.findtext("DateOfLastReport")
     
       
    #Patient Adress code extraction into address
    address = root.find(".//PatientAddress")
    if address is not None:
        data["patient"]["addresscode"] = address.findtext("AddressTypeCode")
        data["patient"]["lgacode"] = address.findtext("LGACode")
        data["patient"]["statecode"] = address.findtext("StateCode")
        data["patient"]["countrycode"] = address.findtext("CountryCode")
        
        # Check for missing or empty fields and append messages
        if not data["patient"]["addresscode"]:
            data["validation_flags"].append("Missing AddressTypeCode in PatientAddress")
        if not data["patient"]["lgacode"]:
            data["validation_flags"].append("Missing LGACode in PatientAddress")
        if not data["patient"]["statecode"]:
            data["validation_flags"].append("Missing StateCode in PatientAddress")
        if not data["patient"]["countrycode"]:
            data["validation_flags"].append("Missing CountryCode in PatientAddress")
    else:
        data["validation_flags"].append("Missing PatientAddress element")    

    hiv_q = root.find(".//HIVQuestions")
    if hiv_q is not None:
        art_start = hiv_q.findtext("ARTStartDate")
        if art_start:
            try:
                data["art_start"] = datetime.strptime(art_start, "%Y-%m-%d")
            except ValueError:
                pass
        else:
            data["validation_flags"].append("Missing ARTStartDate")

        height_at_art_start = hiv_q.findtext("ChildHeightAtARTStart")
        if height_at_art_start:
            data["patient"]["height_at_art_start"] = height_at_art_start

    for reg in root.findall(".//Regimen"):
        date = reg.findtext("VisitDate") or "Unknown"
        data["regimens"][date] = {
            "code": reg.findtext("PrescribedRegimen/Code") or "",
            "codetext": reg.findtext("PrescribedRegimen/CodeDescTxt") or "",
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

    return data
