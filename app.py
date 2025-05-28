import os
import tempfile
from flask import Flask, request, render_template
from xml.etree.ElementTree import ParseError
from ndr_extractor import extract_services
from ndr_validator import validate_ndr

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def home():
    error_message = None
    results = []  # list of dicts {patient, art_start, issues}

    if request.method == 'POST':
        files = request.files.getlist('file')

        if not files or all(f.filename == '' for f in files):
            error_message = "❌ No files selected."
        else:
            for f in files:
                if not f.filename.lower().endswith('.xml'):
                    error_message = "❌ Only .xml files are accepted."
                    break
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xml') as tmp_file:
                    f.save(tmp_file.name)
                    tmp_path = tmp_file.name

                try:
                    data = extract_services(tmp_path)
                    issues = validate_ndr(data)

                    results.append({
                        "patient": data.get("patient"),
                        "art_start": data.get("art_start").date() if data.get("art_start") else None,
                        "issues": issues
                    })
                except ParseError:
                    error_message = "❌ Uploaded file is not well-formed XML."
                    break
                except Exception as exc:
                    error_message = f"❌ Unexpected error: {exc}"
                    break
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

    return render_template('index.html',
                           error_message=error_message,
                           results=results)

if __name__ == "__main__":
    app.run(debug=True)
