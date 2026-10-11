# TEST FIXTURE: clean file, but a "near miss". It uses subprocess the SAFE way
# (a list of arguments, no shell), so a good scanner must NOT flag it.
import subprocess


def list_dir(path):
    return subprocess.run(["ls", path], capture_output=True)
