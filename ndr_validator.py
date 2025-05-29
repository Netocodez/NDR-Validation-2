from datetime import datetime

def validate_ndr(data: dict) -> list:
    data.setdefault("validation_flags", [])
    issues = []
    
    seen_issues = set()

    def add_issue(msg):
        if msg not in seen_issues:
            issues.append(msg)
            seen_issues.add(msg)
    
    ipt_dates = {
        d for d, r in data["regimens"].items()
        if "INH" in (r["code"] or "").upper()
    }

    # Extract all invalid identifier messages from validation_flags
    invalid_ids = [flag for flag in data["validation_flags"] if "Invalid identifier" in flag]

    idtypeHN = data["patient"].get("hn")
    idtypeTB = data["patient"].get("tb_id")

    # Append all invalid ID messages
    for invalid_msg in invalid_ids:
        issues.append(f"❌ {invalid_msg}")

    # If hn is missing, flag that explicitly and mention tb_id if any
    if idtypeHN is None:
        issues.append(f"❌ Missing valid Treatment Patient identifier (HN). Supplied TB ID: {idtypeTB}")


        
    if "Missing ARTStartDate" in data["validation_flags"] or data.get("art_start") is None:
        issues.append("❌ ARTStartDate is missing in HIVQuestions section.")
      
        
    # List of address-related messages to check
    address_flags = [
        "Missing AddressTypeCode in PatientAddress",
        "Missing LGACode in PatientAddress",
        "Missing StateCode in PatientAddress",
        "Missing CountryCode in PatientAddress",
        "Missing PatientAddress element"
    ]
    # Append any matching address messages to issues
    for flag in address_flags:
        if flag in data["validation_flags"]:
            issues.append(f"❌ {flag}")

    for date, enc in data["encounters"].items():
        if date == "Unknown":
            issues.append("❌ Encounter missing VisitDate.")
            continue

        if not enc["arv"]:
            issues.append(f"❌ {date}: ARVDrugRegimen/Code is missing.")

        art_start = data.get("art_start")
        try:
            visit_dt = datetime.strptime(date, "%Y-%m-%d")
            if art_start and visit_dt < art_start and enc.get("arv"):
                issues.append(f"❌ {date}: Encounter precedes ARTStartDate ({art_start.date()}).")

            if not art_start:
                issues.append(f"❌ {date}: ARTStartDate Missing.")
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
                regcodetext = reg["codetext"] or ""
                print(dur, date, regcodetext)

                # Check if duration is within 1–180
                if not (1 <= dur <= 180):
                    #issues.append(f"❌ {date}: PrescribedRegimenDuration {regcodetext} is {dur}, expected between 1 and 180 days.")
                    add_issue(f"❌ {date}: PrescribedRegimenDuration {regcodetext} is {dur}, expected between 1 and 180 days.")

                # Existing rule: duration >30 but no MMD
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

    # Validate height_at_art_start if available
    height_at_art_start = data["patient"].get("height_at_art_start")
    art_start = data.get("art_start")
    if height_at_art_start:
        try:
            height_val = float(height_at_art_start)
            if height_val > 200:
                art_start_str = art_start.strftime("%Y-%m-%d") if art_start else "Unknown date"
                issues.append(f"❌ ART Start ({art_start_str}): Child Height at ART start > 200 ({height_val}).")
        except (TypeError, ValueError):
            pass

    # Validate encounter heights
    for date, enc in data["encounters"].items():
        height = enc.get("height")
        try:
            height_val = float(height)
            if height_val > 200:
                issues.append(f"❌ {date}: Child Height > 200 ({height_val}).")
        except (TypeError, ValueError):
            pass
        

    return issues
