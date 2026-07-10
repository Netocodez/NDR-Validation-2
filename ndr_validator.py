from datetime import datetime, timedelta

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

    # Patient identifier
    if not patient.get("id"):
        add_issue("❌ Missing PatientIdentifier.")

    # Optional secondary identifiers
    if not patient.get("hn") and not patient.get("tb_id"):
        add_issue("⚠️ No secondary identifier (HN/TB) supplied.")

    # Duplicate identifiers
    if (
        patient.get("hn")
        and patient.get("tb_id")
        and patient["hn"] == patient["tb_id"]
    ):
        add_issue("⚠️ HN and TB identifiers are identical. Verify patient identifiers.")

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

    

    # ==========================================================
    # Regimen Validation
    # ==========================================================
    for date, regimen_list in regimens.items():

        for reg in regimen_list:
            
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                add_issue(f"⚠️ {date}: Regimen VisitDate has invalid format.")
                continue

            reg_code = reg.get("code")
            reg_type = reg.get("type")
            duration = reg.get("duration")
            mmd = reg.get("mmd")
            codetext = reg.get("codetext", "")

            # Required XML elements
            if not reg_code:
                add_issue(f"❌ {date}: Missing PrescribedRegimen Code.")

            if not reg_type:
                add_issue(f"❌ {date}: Missing PrescribedRegimenTypeCode.")

            if duration in (None, "", "NULL"):
                add_issue(
                    f"❌ {date}: Missing PrescribedRegimenDuration. "
                    "This will cause NDR XML validation to fail."
                )
                continue

            # Duration validation
            try:
                dur = int(duration)

                if not (1 <= dur <= 180):
                    add_issue(
                        f"❌ {date}: PrescribedRegimenDuration "
                        f"{codetext} ({reg_type}) is {dur}, "
                        "expected between 1 and 180 days."
                    )

            except (TypeError, ValueError):
                add_issue(
                    f"⚠️ {date}: PrescribedRegimenDuration is not numeric."
                )
                continue

            # MMD validation
            if (
                (reg_type or "").strip().upper() == "ART"
                and dur > 30
                and not mmd
            ):
                add_issue(
                    f"❌ {date}: ART regimen duration >30 days but MultiMonthDispensing is missing."
                )
            
            
    # ==========================================================
    # Encounter Validation
    # ==========================================================
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

        # ARV run-out logic
        if art_regimen and art_regimen.get("duration"):
            try:
                duration = int(art_regimen["duration"])
                last_refill_date = visit_dt
                expected_run_out = visit_dt + timedelta(days=duration)

            except (TypeError, ValueError):
                add_issue(f"⚠️ {date}: ART regimen duration is not numeric.")

        elif expected_run_out and visit_dt > expected_run_out:
            if not enc.get("arv"):
                add_issue(
                    f"❌ {date}: Encounter after ARVs should have run out "
                    f"({expected_run_out.date()}), but no refill documented."
                )

        # Encounter vs Regimen validation
        if art_regimen:

            # ART regimen exists but Encounter ARV code is missing
            if not enc.get("arv"):
                add_issue(
                    f"❌ {date}: ART regimen exists but HIVEncounter is missing ARVDrugRegimen/Code."
                )

            # ART regimen exists but codes do not match
            elif (
                art_regimen.get("code")
                and enc["arv"] != art_regimen["code"]
            ):
                add_issue(
                    f"❌ {date}: ARV code mismatch "
                    f"(Encounter={enc['arv']}, Regimen={art_regimen['code']})."
                )

        # Height validation
        try:
            height = float(enc.get("height", 0))
            if height > 200:
                add_issue(f"❌ {date}: Child Height > 200 ({height}).")
        except (TypeError, ValueError):
            pass
    
    
    # ==========================================================
    # Laboratory Report Validation (Warning Only)
    # ==========================================================
    """for date, lab in labs.items():

        if lab.get("test_id") and not lab.get("collected"):
            add_issue(
                f"⚠️ {date}: LaboratoryTestIdentifier exists but CollectionDate is missing."
            )

        elif lab.get("collected") and not lab.get("test_id"):
            add_issue(
                f"⚠️ {date}: CollectionDate exists but LaboratoryTestIdentifier is missing."
            )"""

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
