
import subprocess

def run_command(cmd):
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,  # <--- IMPORTANT
    )
    stdout, stderr = proc.communicate()
    return proc.returncode, stdout, stderr
