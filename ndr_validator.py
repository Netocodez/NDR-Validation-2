from datetime import datetime, timedelta

from datetime import datetime

def get_last_art_pickup(regimens):
    latest = None

    for visit_date, regimen_list in regimens.items():

        try:
            visit = datetime.strptime(visit_date, "%Y-%m-%d")
        except ValueError:
            continue

        for reg in regimen_list:

            if (reg.get("type") or "").strip().upper() != "ART":
                continue

            try:
                duration = int(reg.get("duration") or 0)
            except (TypeError, ValueError):
                continue

            if latest is None or visit > latest["pickup"]:
                latest = {
                    "pickup": visit,
                    "duration": duration,
                    "regimen": reg
                }

    return latest

def validate_ndr(data: dict) -> list:
    data.setdefault("validation_flags", [])
    issues = []
    seen_issues = set()

    def add_issue(msg):
        if msg not in seen_issues:
            issues.append(msg)
            seen_issues.add(msg)

    def is_expected_to_have_drug_pickup(encounter: dict, regimen: dict) -> bool:
        return any([
            encounter.get("who_stage"),
            encounter.get("weight"),
            encounter.get("cd4"),
            encounter.get("functional_status"),
            regimen and regimen.get("code")
        ])

    def is_drug_pickup_documented(encounter, regimen):
        if regimen is None:
            return False

        return bool(
            encounter.get("arv")
            or regimen.get("code")
            or regimen.get("duration")
        )

    ipt_dates = set()

    for date, regimen_list in data.get("regimens", {}).items():

        for reg in regimen_list:

            if "INH" in (reg.get("code") or "").upper():
                ipt_dates.add(date)

    patient = data.get("patient", {})
    encounters = data.get("encounters", {})
    regimens = data.get("regimens", {})
    labs = data.get("labs", {})
    art_start = data.get("art_start")

    if isinstance(art_start, str):
        try:
            art_start = datetime.strptime(art_start, "%Y-%m-%d")
        except ValueError:
            art_start = None

    # Identifier checks
    invalid_ids = [flag for flag in data["validation_flags"] if "Invalid identifier" in flag]
    for msg in invalid_ids:
        add_issue(f"❌ {msg}")

    if not patient.get("hn"):
        add_issue(f"❌ Missing valid Treatment Patient identifier (HN). Supplied TB ID: {patient.get('tb_id')}")

    # ART Start check
    if "Missing ARTStartDate" in data["validation_flags"] or not art_start:
        add_issue("❌ ARTStartDate is missing in HIVQuestions section.")

    # Address fields
    address_flags = [
        "Missing AddressTypeCode in PatientAddress",
        "Missing LGACode in PatientAddress",
        "Missing StateCode in PatientAddress",
        "Missing CountryCode in PatientAddress",
        "Missing PatientAddress element"
    ]
    for flag in address_flags:
        if flag in data["validation_flags"]:
            add_issue(f"❌ {flag}")

    # Regimen duration and MMD checks
    for date, regimen_list in regimens.items():
        
        for reg in regimen_list:

            try:
                dur = int(reg.get("duration") or 0)
                codetext = reg.get("codetext", "")
                regimen_type = reg.get("type", "")

                if not (1 <= dur <= 180):
                    add_issue(
                        f"❌ {date}: PrescribedRegimenDuration "
                        f"{codetext} ({regimen_type}) is {dur}, "
                        f"expected between 1 and 180 days."
                    )

                if regimen_type == "ART" and dur > 30 and not reg.get("mmd"):
                    add_issue(
                        f"❌ {date}: ART regimen duration >30 days but MMD not specified."
                    )

            except (TypeError, ValueError):
                add_issue(f"⚠️ {date}: Regimen duration not numeric.")

    # Encounters
    last_refill_date = None
    expected_run_out = None

    for date in sorted(encounters):
        enc = encounters[date]
        regimen_list = regimens.get(date, [])

        art_regimen = next(
            (
                r for r in regimen_list
                if (r.get("type") or "").strip().upper() == "ART"
            ),
            None
        )
        try:
            visit_dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            add_issue(f"⚠️ {date}: VisitDate has invalid format.")
            continue

        if is_expected_to_have_drug_pickup(enc, art_regimen) and not is_drug_pickup_documented(enc, art_regimen):
            add_issue(f"❌ {date}: Drug pickup expected but not documented.")

        # ARV runout logic
        if art_regimen and art_regimen.get("duration"):
            try:
                duration = int(art_regimen["duration"])
                last_refill_date = visit_dt
                expected_run_out = visit_dt + timedelta(days=duration)

            except ValueError:
                add_issue(f"⚠️ {date}: ART regimen duration is not numeric.")
        elif expected_run_out and visit_dt > expected_run_out and not enc.get("arv"):
            add_issue(f"❌ {date}: Encounter after ARVs should have run out ({expected_run_out.date()}), but no refill documented.")

        # ARV code mismatch
        if art_regimen:
            if (
                enc.get("arv")
                and art_regimen.get("code")
                and enc["arv"] != art_regimen["code"]
            ):
                add_issue(
                    f"❌ {date}: ARV code mismatch "
                    f"(Encounter={enc['arv']}, Regimen={art_regimen['code']})."
                )

        # Height check
        try:
            height = float(enc.get("height", 0))
            if height > 200:
                add_issue(f"❌ {date}: Child Height > 200 ({height}).")
        except (TypeError, ValueError):
            pass

    # Lab checks
    for date, lab in labs.items():
        if not lab.get("test_id") or not lab.get("collected"):
            add_issue(f"❌ {date}: Lab report missing test ID or collection date.")

    # Age validation
    try:
        dob_dt = datetime.strptime(patient["dob"], "%Y-%m-%d")
        rpt_dt = datetime.strptime(patient["report_date"], "%Y-%m-%d")
        calc_age = rpt_dt.year - dob_dt.year - ((rpt_dt.month, rpt_dt.day) < (dob_dt.month, dob_dt.day))
        reported_age = int(patient.get("age", -1))
        if abs(calc_age - reported_age) > 1:
            add_issue(f"❌ Reported age ({reported_age}) vs calculated ({calc_age}) differs by >1 year.")
        if calc_age < 0 or calc_age > 120:
            add_issue(f"❌ Calculated age ({calc_age}) is out of valid human range.")
    except Exception:
        add_issue("⚠️ Unable to validate age (date format issue).")

    # Height at ART start
    try:
        height_start = float(patient.get("height_at_art_start", 0))
        age = int(patient.get("age", 0))
        if age < 15 and height_start > 200:
            date_str = art_start.strftime("%Y-%m-%d") if art_start else "Unknown date"
            add_issue(f"❌ ART Start ({date_str}): Child Height at ART start > 200 ({height_start}).")
    except (TypeError, ValueError):
        pass
    
    # ==========================================================
    # Active or Inactive ART Status Check
    # ==========================================================
    try:
        today = datetime.today()

        last_pickup = get_last_art_pickup(regimens)

        if last_pickup:

            pickup = last_pickup["pickup"]
            duration = last_pickup["duration"]
            regimen = last_pickup["regimen"]

            regimen_name = regimen.get("codetext", "Unknown Regimen")
            regimen_code = regimen.get("code", "Unknown")

            expected_refill = pickup + timedelta(days=duration)
            inactive_date = expected_refill + timedelta(days=28)

            if today > inactive_date:

                overdue = (today - inactive_date).days

                add_issue(
                    f"❌ Patient is INACTIVE.\n"
                    f"   • Last ART Refill Date : {pickup.date()}\n"
                    f"   • ART Regimen          : {regimen_name} ({regimen_code})\n"
                    f"   • Days Dispensed       : {duration} day(s)\n"
                    f"   • Expected Refill Date : {expected_refill.date()}\n"
                    f"   • Became Inactive On   : {inactive_date.date()}\n"
                    f"   • Days Overdue         : {overdue}"
                )

            else:

                days_remaining = (inactive_date - today).days

                add_issue(
                    f"✅ Patient is ACTIVE.\n"
                    f"   • Last ART Refill Date : {pickup.date()}\n"
                    f"   • ART Regimen          : {regimen_name} ({regimen_code})\n"
                    f"   • Days Dispensed       : {duration} day(s)\n"
                    f"   • Expected Refill Date : {expected_refill.date()}\n"
                    f"   • Will Become Inactive : {inactive_date.date()}\n"
                    f"   • Days Remaining       : {days_remaining}"
                )

        else:
            add_issue(
                "❌ Unable to determine ART status. "
                "No ART regimen/pickup was found in the NDR."
            )

    except Exception as e:
        add_issue(f"⚠️ Unable to determine ART refill status. ({e})")

    return issues
