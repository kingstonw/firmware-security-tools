from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from pathlib import Path

def gen_pair(name: str):
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key()

    Path("keys").mkdir(exist_ok=True)

    Path(f"keys/{name}_private.pem").write_bytes(
        priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    Path(f"keys/{name}_public.pem").write_bytes(
        pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

gen_pair("esp32_ota")
gen_pair("stm32_ota")
print("device keys generated")