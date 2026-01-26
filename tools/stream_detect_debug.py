import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from urllib import request


def encode_multipart_formdata(field_name: str, filename: str, file_bytes: bytes, content_type: str | None = None) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    parts = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode()
    )
    parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
    parts.append(file_bytes)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
    content_header = f"multipart/form-data; boundary={boundary}"
    return body, content_header


def main() -> int:
    url = os.environ.get("DETECT_URL", "http://127.0.0.1:8000/detect/")
    zip_path = Path(os.environ.get("ZIP_PATH", str(Path(__file__).parent / "sample.zip")))

    if not zip_path.exists():
        print(f"ZIP not found: {zip_path}")
        return 2

    body, content_type = encode_multipart_formdata(
        "zip_file", zip_path.name, zip_path.read_bytes(), "application/zip"
    )

    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    req.add_header("Accept", "application/x-ndjson")

    msgs = []

    with request.urlopen(req, timeout=600) as resp:
        print("status", resp.status)
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as e:
                print("bad json:", line[:200], e)
                continue
            msgs.append(obj)
            stage = obj.get("stage")
            if stage:
                print("stage=", stage, "keys=", sorted(obj.keys()))
            elif "progress" in obj:
                print("progress=", obj.get("progress"), "keys=", sorted(obj.keys()))
            elif "results" in obj:
                print("final keys=", sorted(obj.keys()))

    out = Path(__file__).parent / "last_response.json"
    out.write_text(json.dumps(msgs, indent=2))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
