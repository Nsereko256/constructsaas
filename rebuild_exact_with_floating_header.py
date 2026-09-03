from pathlib import Path
import re
import zipfile

ORIGINAL = Path(r"C:\Users\840G3\Downloads\HSE SIGNAGE (1).docx")
GENERATED_HEADER = Path(r"C:\Users\840G3\Desktop\CONSTRUCT SAAS\HSE SIGNAGE - Egypro ATC headers.docx")
OUTPUT = Path(r"C:\Users\840G3\Desktop\CONSTRUCT SAAS\HSE SIGNAGE - Egypro ATC headers.docx")

with zipfile.ZipFile(ORIGINAL, 'r') as src, zipfile.ZipFile(GENERATED_HEADER, 'r') as gen:
    parts = {name: src.read(name) for name in src.namelist()}
    header_xml = gen.read('word/header1.xml')
    header_rels = gen.read('word/_rels/header1.xml.rels')
    egypro_bytes = gen.read('word/media/image234.jpeg')
    atc_bytes = gen.read('word/media/image235.jpeg')

document_xml = parts['word/document.xml']
header_ref = b'<w:headerReference w:type="default" r:id="rId238"/>'
assert document_xml.count(b'<w:pgSz') == 173
document_xml = document_xml.replace(b'<w:pgSz', header_ref + b'<w:pgSz')

rels = parts['word/_rels/document.xml.rels']
rel = b'<Relationship Id="rId238" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
rels = rels.replace(b'</Relationships>', rel + b'</Relationships>')

types = parts['[Content_Types].xml']
override = b'<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
types = types.replace(b'</Types>', override + b'</Types>')

parts['word/document.xml'] = document_xml
parts['word/_rels/document.xml.rels'] = rels
parts['[Content_Types].xml'] = types
parts['word/header1.xml'] = header_xml
parts['word/_rels/header1.xml.rels'] = header_rels
parts['word/media/image234.jpeg'] = egypro_bytes
parts['word/media/image235.jpeg'] = atc_bytes

with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as dst:
    for name, data in parts.items():
        dst.writestr(name, data)

print(OUTPUT)
