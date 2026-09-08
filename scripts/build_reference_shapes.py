"""Regenerate the Reference walker metadata from the official R4 schema ZIP.

Usage: python scripts/build_reference_shapes.py /path/to/fhir.schema.json.zip
The ZIP is downloaded separately; the validator performs no schema downloads.
"""

import json
import zipfile
import hashlib
import sys
from pathlib import Path

raw = zipfile.ZipFile(sys.argv[1]).read("fhir.schema.json")
schema = json.loads(raw)
defs = schema["definitions"]
resources = [
    n
    for n, d in defs.items()
    if d.get("properties", {}).get("resourceType", {}).get("const") == n
]
shapes = {}
for name, d in defs.items():
    fields = {}
    for field, p in d.get("properties", {}).items():
        node = p.get("items", p)
        typ = node.get("$ref", "").rsplit("/", 1)[-1]
        if field == "valueCanonical":
            typ = "canonical"
        if typ in ("ResourceList", "canonical") or defs.get(typ, {}).get("properties"):
            fields[field] = [typ, p.get("type") == "array"]
    if fields:
        shapes[name] = fields
out = {
    "fhir_version": "4.0.1",
    "source": "https://hl7.org/fhir/R4/fhir.schema.json.zip",
    "source_sha256": hashlib.sha256(raw).hexdigest(),
    "license": "FHIR specification: CC0; https://hl7.org/fhir/R4/license.html",
    "resources": sorted(resources),
    "shapes": shapes,
}
p = Path("data/fhir_r4_reference_shapes.json")
p.write_text(
    json.dumps(out, indent=2).split('  "shapes": {')[0]
    + '  "shapes": {\n'
    + ",\n".join(
        "    " + json.dumps(k) + ": " + json.dumps(v, separators=(",", ":"))
        for k, v in shapes.items()
    )
    + "\n  }\n}\n"
)
