import boto3
from pathlib import Path

REGION = "us-east-1"
KMS_KEY_ID = "arn:aws:kms:us-east-1:123456789012:key/xxxx-sign"

kms = boto3.client("kms", region_name=REGION)
resp = kms.get_public_key(KeyId=KMS_KEY_ID)

Path("out").mkdir(exist_ok=True)
Path("out/kms_signing_pub.der").write_bytes(resp["PublicKey"])
print("saved: out/kms_signing_pub.der")