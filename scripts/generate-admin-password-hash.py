"""Generate a salted PBKDF2 hash without storing the admin password."""

import base64
import getpass
import hashlib
import secrets


ITERATIONS = 210_000


password = getpass.getpass("Choose the demo admin password: ")
confirmation = getpass.getpass("Confirm the password: ")
if password != confirmation:
    raise SystemExit("Passwords do not match.")
if len(password) < 12:
    raise SystemExit("Use at least 12 characters.")

salt = secrets.token_bytes(18)
digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
encoded_salt = base64.b64encode(salt).decode("ascii")
encoded_digest = base64.b64encode(digest).decode("ascii")
print(f"{ITERATIONS}:{encoded_salt}:{encoded_digest}")
