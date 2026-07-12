import zipfile

from flask import Flask, request, render_template
from xml.etree.ElementTree import ParseError

from ndr_extractor import extract_services
from ndr_validator import validate_ndr

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def home():
    error_message = None
    results = []

    if request.method == 'POST':
        files = request.files.getlist('file')

        if not files or all(f.filename == '' for f in files):
            error_message = "❌ No files selected."
        else:
            for f in files:
                try:
                    filename = f.filename.lower()

                    # -----------------------------
                    # Single XML file
                    # -----------------------------
                    if filename.endswith(".xml"):
                        f.stream.seek(0)

                        data = extract_services(f.stream)
                        issues = validate_ndr(data)

                        results.append({
                            "patient": data.get("patient"),
                            "art_start": (
                                data.get("art_start").date()
                                if data.get("art_start")
                                else None
                            ),
                            "issues": issues
                        })

                    # -----------------------------
                    # ZIP archive containing XML(s)
                    # -----------------------------
                    elif filename.endswith(".zip"):
                        f.stream.seek(0)

                        with zipfile.ZipFile(f.stream) as archive:

                            xml_files = [
                                name for name in archive.namelist()
                                if name.lower().endswith(".xml")
                            ]

                            if not xml_files:
                                raise Exception(
                                    "ZIP archive contains no XML files."
                                )

                            for xml_name in xml_files:
                                try:
                                    with archive.open(xml_name) as xml_file:
                                        data = extract_services(xml_file)
                                        issues = validate_ndr(data)

                                        results.append({
                                            "patient": data.get("patient"),
                                            "art_start": (
                                                data.get("art_start").date()
                                                if data.get("art_start")
                                                else None
                                            ),
                                            "issues": issues
                                        })

                                except ParseError:
                                    results.append({
                                        "patient": {"id": xml_name},
                                        "art_start": None,
                                        "issues": ["Invalid XML file."]
                                    })

                    # -----------------------------
                    # Unsupported file type
                    # -----------------------------
                    else:
                        raise Exception(
                            "Only .xml and .zip files are supported."
                        )

                except ParseError:
                    error_message = "❌ Invalid XML file."
                    break

                except zipfile.BadZipFile:
                    error_message = "❌ Invalid ZIP archive."
                    break

                except Exception as exc:
                    error_message = f"❌ {exc}"
                    break

    return render_template(
        'index.html',
        error_message=error_message,
        results=results
    )


if __name__ == "__main__":
    app.run(debug=True)