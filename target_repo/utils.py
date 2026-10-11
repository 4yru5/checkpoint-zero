# TEST FIXTURE: deliberately unsafe. Only scanned as text, NEVER executed.
# Planted bug #2: shell=True sends the whole string to the shell, so a host like
# "x; rm -rf ~" would run a second command (command injection).
import subprocess


def ping(host):
    cmd = "ping -c 1 " + host
    return subprocess.run(cmd, shell=True)
