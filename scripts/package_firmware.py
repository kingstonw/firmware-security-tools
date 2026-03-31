import os, json, base64, hashlib
from pathlib import Path
import boto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

REGION = "us-east-1"
KMS_DATA_KEY_ID = "arn:aws:kms:us-east-1:123456789012:key/xxxx-data"
DEVICE_PUBLIC_KEY_PEM = Path("keys/esp32_ota_public.pem").read_bytes()

INPUT = Path("input/firmware.bin")
OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)

# 1) 明文固件
firmware = INPUT.read_bytes()
firmware_sha256 = hashlib.sha256(firmware).hexdigest()

# 2) KMS 生成 DEK
kms = boto3.client("kms", region_name=REGION)
resp = kms.generate_data_key(
    KeyId=KMS_DATA_KEY_ID,
    KeySpec="AES_256"
)
dek_plain = resp["Plaintext"]
dek_kms_cipher = resp["CiphertextBlob"]

# 3) AES-256-GCM 加密固件
nonce = os.urandom(12)
aesgcm = AESGCM(dek_plain)
ciphertext_with_tag = aesgcm.encrypt(nonce, firmware, None)

# cryptography 的 AESGCM.encrypt 返回 ciphertext||tag
ciphertext = ciphertext_with_tag[:-16]
tag = ciphertext_with_tag[-16:]

(OUT_DIR / "firmware.bin.enc").write_bytes(ciphertext)

# 4) 设备公钥包裹 DEK
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM as AESGCM2

device_pub = serialization.load_pem_public_key(DEVICE_PUBLIC_KEY_PEM)
ephemeral_priv = ec.generate_private_key(ec.SECP256R1())
shared = ephemeral_priv.exchange(ec.ECDH(), device_pub)
wrap_key = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=None,
    info=b"ota-dek-wrap",
).derive(shared)

wrap_nonce = os.urandom(12)
wrapped = AESGCM2(wrap_key).encrypt(wrap_nonce, dek_plain, None)
ephemeral_pub = ephemeral_priv.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

manifest = {
    "device_type": "esp32",
    "version": "1.2.3",
    "firmware_url": "https://example.com/firmware.bin.enc",
    "firmware_size": len(ciphertext),
    "firmware_sha256": firmware_sha256,
    "enc_alg": "AES-256-GCM",
    "nonce_b64": base64.b64encode(nonce).decode(),
    "tag_b64": base64.b64encode(tag).decode(),
    "kms_ciphertext_blob_b64": base64.b64encode(dek_kms_cipher).decode(),
    "wrapped_deks": [{
        "key_id": "esp32_key_v1",
        "wrap_alg": "ECIES-P256+A256GCM",
        "ephemeral_pub_pem_b64": base64.b64encode(ephemeral_pub).decode(),
        "wrap_nonce_b64": base64.b64encode(wrap_nonce).decode(),
        "wrapped_dek_b64": base64.b64encode(wrapped).decode()
    }],
    "sign_alg": "RSASSA_PSS_SHA_256"
}

(OUT_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    encoding="utf-8"
)
print("packaged")