import subprocess, time, sys, urllib.request, os

# Change to project root
os.chdir(os.path.dirname(__file__))

# Start Django dev server in a subprocess
proc = subprocess.Popen([
    '.venv\\Scripts\\python.exe',
    'manage.py',
    'runserver',
    '8000'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# Give server time to start
time.sleep(5)

try:
    with urllib.request.urlopen('http://127.0.0.1:8000') as resp:
        data = resp.read().decode('utf-8')
        print('SERVER RESPONSE:')
        print(data[:500])  # print first part
except Exception as e:
    print('ERROR contacting server:', e)
finally:
    # Terminate the server process
    proc.terminate()
    proc.wait()
