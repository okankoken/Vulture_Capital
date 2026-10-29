"""Create a repository-specific deploy key. Never print the private key."""
from pathlib import Path
import subprocess
import requests

root=Path(__file__).resolve().parents[1]
runtime=root/"runtime"
runtime.mkdir(exist_ok=True)
key=runtime/"publisher_ed25519"
if not key.exists():
    subprocess.run(["ssh-keygen","-t","ed25519","-N","","-f",str(key),
                    "-C","vulture-capital-data-publisher"],check=True,capture_output=True)
key.chmod(0o600)
response=requests.get("https://api.github.com/meta",timeout=30)
response.raise_for_status()
hostkeys=response.json()["ssh_keys"]
(runtime/"github_known_hosts").write_text("".join(f"github.com {value}\n" for value in hostkeys),encoding="utf-8")
print(key.with_suffix(".pub").read_text().strip())
