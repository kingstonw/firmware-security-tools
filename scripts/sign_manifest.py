import json, base64, hashlib
from pathlib import Path
import boto3

REGION = "us-east-1"
KMS_SIGN_KEY_ID = "arn:aws:kms:us-east-1:123456789012:key/xxxx-sign"

manifest_path = Path("out/manifest.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

manifest.pop("signature_b64", None)
canonical = json.dumps(
    manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
).encode("utf-8")

digest = hashlib.sha256(canonical).digest()

kms = boto3.client("kms", region_name=REGION)
resp = kms.sign(
    KeyId=KMS_SIGN_KEY_ID,
    Message=digest,
    MessageType="DIGEST",
    SigningAlgorithm="RSASSA_PSS_SHA_256",
)

manifest["signature_b64"] = base64.b64encode(resp["Signature"]).decode()

manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    encoding="utf-8"
)
print("manifest signed")