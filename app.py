import os
import shutil
import zipfile
import subprocess
import tempfile
import uuid
import sys
import threading
import time
import json
from flask import Flask, request, render_template_string, send_file, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
import logging
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['ALLOWED_EXTENSIONS'] = {'py'}

# Detect if running on Render
ON_RENDER = 'RENDER' in os.environ

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store conversion status
conversion_status = {}

# HTML template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advanced Python to EXE Converter</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f8f9fa;
            padding-top: 2rem;
        }
        .container {
            max-width: 800px;
            background-color: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 2rem;
        }
        .form-container {
            margin-bottom: 2rem;
        }
        .options-container {
            margin-top: 1.5rem;
        }
        .status-container {
            margin-top: 2rem;
        }
        .footer {
            text-align: center;
            margin-top: 2rem;
            font-size: 0.9rem;
            color: #6c757d;
        }
        .progress {
            margin-top: 20px;
        }
        .log-container {
            margin-top: 20px;
            max-height: 300px;
            overflow-y: auto;
            background-color: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
        }
        #statusMessage {
            font-weight: bold;
        }
        .nav-tabs {
            margin-bottom: 20px;
        }
        #codeEditor {
            width: 100%;
            min-height: 200px;
            font-family: monospace;
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Advanced Python to EXE Converter</h1>
            <p class="lead">Convert your Python scripts to executable files</p>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <div class="form-container">
            <ul class="nav nav-tabs" id="inputTabs" role="tablist">
                <li class="nav-item" role="presentation">
                    <button class="nav-link active" id="upload-tab" data-bs-toggle="tab" data-bs-target="#upload-tab-pane" type="button" role="tab" aria-controls="upload-tab-pane" aria-selected="true">Upload File</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="paste-tab" data-bs-toggle="tab" data-bs-target="#paste-tab-pane" type="button" role="tab" aria-controls="paste-tab-pane" aria-selected="false">Paste Code</button>
                </li>
            </ul>
            
            <div class="tab-content" id="inputTabsContent">
                <div class="tab-pane fade show active" id="upload-tab-pane" role="tabpanel" aria-labelledby="upload-tab" tabindex="0">
                    <form method="POST" action="{{ url_for('upload_file') }}" enctype="multipart/form-data" id="uploadForm">
                        <input type="hidden" name="input_type" value="file">
                        <div class="mb-3">
                            <label for="pyfile" class="form-label">Select Python file:</label>
                            <input type="file" class="form-control" id="pyfile" name="file" accept=".py" required>
                        </div>
                        
                        <!-- Build options section -->
                        <div class="options-container" id="fileOptions">
                            <h5>Build Options</h5>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" id="oneFile" name="one_file" checked>
                                        <label class="form-check-label" for="oneFile">
                                            One-file bundle
                                        </label>
                                    </div>
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" id="console" name="console" checked>
                                        <label class="form-check-label" for="console">
                                            Console application
                                        </label>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" id="uac" name="uac">
                                        <label class="form-check-label" for="uac">
                                            Request admin privileges
                                        </label>
                                    </div>
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" id="debug" name="debug">
                                        <label class="form-check-label" for="debug">
                                            Debug mode
                                        </label>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="mb-3 mt-3">
                                <label for="extraPackages" class="form-label">Additional packages (comma separated):</label>
                                <input type="text" class="form-control" id="extraPackages" name="packages" placeholder="numpy,pandas,matplotlib">
                            </div>
                            
                            <div class="mb-3">
                                <label for="extraFiles" class="form-label">Additional files (uploaded later):</label>
                                <input type="file" class="form-control" id="extraFiles" name="extra_files" multiple>
                            </div>
                            
                            <div class="mb-3">
                                <label for="targetPlatform" class="form-label">Target Platform:</label>
                                <select class="form-select" id="targetPlatform" name="platform">
                                    <option value="auto" selected>Auto-detect</option>
                                    <option value="windows">Windows</option>
                                    <option value="linux">Linux</option>
                                    <option value="macos">macOS</option>
                                </select>
                            </div>
                        </div>
                        
                        <button type="submit" class="btn btn-primary w-100" id="uploadSubmitBtn">Convert to EXE</button>
                    </form>
                </div>
                
                <div class="tab-pane fade" id="paste-tab-pane" role="tabpanel" aria-labelledby="paste-tab" tabindex="0">
                    <form method="POST" action="{{ url_for('paste_code') }}" id="pasteForm">
                        <input type="hidden" name="input_type" value="paste">
                        <div class="mb-3">
                            <label for="codeEditor" class="form-label">Python Code:</label>
                            <textarea class="form-control" id="codeEditor" name="code" rows="10" required placeholder="Paste your Python code here..."></textarea>
                        </div>
                        
                        <div class="mb-3">
                            <label for="filename" class="form-label">Filename (with .py extension):</label>
                            <input type="text" class="form-control" id="filename" name="filename" placeholder="main.py" required pattern=".*\.py$">
                            <div class="form-text">Filename must end with .py</div>
                        </div>
                        
                        <!-- Build options section (duplicated for the paste form) -->
                        <div class="options-container" id="pasteOptions">
                            <h5>Build Options</h5>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" id="oneFilePaste" name="one_file" checked>
                                        <label class="form-check-label" for="oneFilePaste">
                                            One-file bundle
                                        </label>
                                    </div>
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" id="consolePaste" name="console" checked>
                                        <label class="form-check-label" for="consolePaste">
                                            Console application
                                        </label>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" id="uacPaste" name="uac">
                                        <label class="form-check-label" for="uacPaste">
                                            Request admin privileges
                                        </label>
                                    </div>
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" id="debugPaste" name="debug">
                                        <label class="form-check-label" for="debugPaste">
                                            Debug mode
                                        </label>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="mb-3 mt-3">
                                <label for="extraPackagesPaste" class="form-label">Additional packages (comma separated):</label>
                                <input type="text" class="form-control" id="extraPackagesPaste" name="packages" placeholder="numpy,pandas,matplotlib">
                            </div>
                            
                            <div class="mb-3">
                                <label for="targetPlatformPaste" class="form-label">Target Platform:</label>
                                <select class="form-select" id="targetPlatformPaste" name="platform">
                                    <option value="auto" selected>Auto-detect</option>
                                    <option value="windows">Windows</option>
                                    <option value="linux">Linux</option>
                                    <option value="macos">macOS</option>
                                </select>
                            </div>
                        </div>
                        
                        <button type="submit" class="btn btn-primary w-100" id="pasteSubmitBtn">Convert to EXE</button>
                    </form>
                </div>
            </div>
            
            <div id="conversionStatus" style="display: none;">
                <div class="alert alert-info mt-3">
                    <h5>Conversion in Progress</h5>
                    <p id="statusMessage">Initializing conversion process...</p>
                    <div class="progress">
                        <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%" id="progressBar"></div>
                    </div>
                </div>
                
                <div class="log-container">
                    <h5>Build Log:</h5>
                    <div id="logContent"></div>
                </div>
            </div>
        </div>
        
        {% if download_link %}
        <div class="status-container">
            <div class="alert alert-success">
                <h5>Conversion successful!</h5>
                <p>Your executable has been created successfully.</p>
                <a href="{{ download_link }}" class="btn btn-success">Download EXE</a>
            </div>
        </div>
        {% endif %}
        
        <div class="footer">
            <p>Advanced Python to EXE Converter © {{ current_year }}</p>
            <p>Powered by PyInstaller</p>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Handle form submission for file upload
        document.getElementById('uploadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            startConversion(this, 'uploadSubmitBtn');
        });
        
        // Handle form submission for code paste
        document.getElementById('pasteForm').addEventListener('submit', function(e) {
            e.preventDefault();
            startConversion(this, 'pasteSubmitBtn');
        });
        
        function startConversion(form, buttonId) {
            // Show progress UI
            document.getElementById('conversionStatus').style.display = 'block';
            document.getElementById(buttonId).disabled = true;
            document.getElementById(buttonId).innerHTML = 'Converting... Please wait';
            
            // Submit the form data via AJAX
            const formData = new FormData(form);
            const action = form.getAttribute('action');
            
            fetch(action, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Start polling for status updates
                    const sessionId = data.session_id;
                    pollStatus(sessionId);
                } else {
                    // Show error
                    document.getElementById('statusMessage').innerText = 'Error: ' + data.message;
                    document.getElementById('progressBar').style.width = '100%';
                    document.getElementById('progressBar').classList.remove('bg-info', 'bg-success');
                    document.getElementById('progressBar').classList.add('bg-danger');
                    document.getElementById(buttonId).disabled = false;
                    document.getElementById(buttonId).innerHTML = 'Try Again';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('statusMessage').innerText = 'Server error occurred. Please try again.';
                document.getElementById('progressBar').style.width = '100%';
                document.getElementById('progressBar').classList.remove('bg-info', 'bg-success');
                document.getElementById('progressBar').classList.add('bg-danger');
                document.getElementById(buttonId).disabled = false;
                document.getElementById(buttonId).innerHTML = 'Try Again';
            });
        }
        
        function pollStatus(sessionId) {
            fetch(`/status/${sessionId}`)
                .then(response => response.json())
                .then(data => {
                    // Update progress bar
                    document.getElementById('progressBar').style.width = data.progress + '%';
                    
                    // Update status message
                    document.getElementById('statusMessage').innerText = data.status;
                    
                    // Update log content
                    if (data.log) {
                        const logElement = document.getElementById('logContent');
                        logElement.innerHTML += `<div>[${new Date().toLocaleTimeString()}] ${data.log}</div>`;
                        logElement.scrollTop = logElement.scrollHeight;
                    }
                    
                    if (data.completed) {
                        if (data.success) {
                            // Show success and download link
                            document.getElementById('progressBar').classList.add('bg-success');
                            document.getElementById('conversionStatus').innerHTML = `
                                <div class="alert alert-success mt-3">
                                    <h5>Conversion successful!</h5>
                                    <p>Your executable has been created successfully.</p>
                                    <a href="${data.download_url}" class="btn btn-success">Download EXE</a>
                                </div>
                            `;
                        } else {
                            // Show error
                            document.getElementById('progressBar').style.width = '100%';
                            document.getElementById('progressBar').classList.remove('bg-info');
                            document.getElementById('progressBar').classList.add('bg-danger');
                            document.getElementById('statusMessage').innerText = 'Error: ' + data.message;
                            document.getElementById('uploadSubmitBtn').disabled = false;
                            document.getElementById('uploadSubmitBtn').innerHTML = 'Try Again';
                            document.getElementById('pasteSubmitBtn').disabled = false;
                            document.getElementById('pasteSubmitBtn').innerHTML = 'Try Again';
                        }
                    } else {
                        // Continue polling
                        setTimeout(() => pollStatus(sessionId), 1000);
                    }
                })
                .catch(error => {
                    console.error('Error polling status:', error);
                    setTimeout(() => pollStatus(sessionId), 2000); // Retry with longer delay
                });
        }
    </script>
</body>
</html>
'''

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, current_year=datetime.now().year, download_link=None)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify(success=False, message='No file part')
    
    file = request.files['file']
    if file.filename == '':
        return jsonify(success=False, message='No selected file')
    
    if not file or not allowed_file(file.filename):
        return jsonify(success=False, message='Only Python (.py) files are allowed')
    
    try:
        # Create session ID
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Initialize status
        conversion_status[session_id] = {
            'progress': 0,
            'status': 'Initializing...',
            'completed': False,
            'success': False,
            'message': '',
            'log': [],
            'download_url': None,
            'timestamp': time.time()
        }
        
        # Create work directory
        work_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        os.makedirs(work_dir, exist_ok=True)
        
        # Save the main Python file
        filename = secure_filename(file.filename)
        file_path = os.path.join(work_dir, filename)
        file.save(file_path)
        
        # Save additional files if provided
        extra_files_paths = []
        if 'extra_files' in request.files:
            extra_files = request.files.getlist('extra_files')
            for extra_file in extra_files:
                if extra_file.filename != '':
                    extra_filename = secure_filename(extra_file.filename)
                    extra_file_path = os.path.join(work_dir, extra_filename)
                    extra_file.save(extra_file_path)
                    extra_files_paths.append(extra_file_path)
        
        # Get options
        options = {
            'one_file': 'one_file' in request.form,
            'console': 'console' in request.form,
            'uac': 'uac' in request.form,
            'debug': 'debug' in request.form,
            'packages': request.form.get('packages', ''),
            'platform': request.form.get('platform', 'auto'),
            'file_path': file_path,
            'work_dir': work_dir,
            'extra_files': extra_files_paths
        }
        
        # Start conversion in background thread
        thread = threading.Thread(
            target=convert_in_background,
            args=(session_id, options),
            daemon=True
        )
        thread.start()
        
        return jsonify(success=True, message='Conversion started', session_id=session_id)
        
    except Exception as e:
        logger.error(f"Error initiating conversion: {str(e)}")
        return jsonify(success=False, message=f'Error: {str(e)}')

@app.route('/paste', methods=['POST'])
def paste_code():
    if 'code' not in request.form or not request.form['code'].strip():
        return jsonify(success=False, message='No code provided')
    
    if 'filename' not in request.form or not request.form['filename'].strip():
        return jsonify(success=False, message='No filename provided')
    
    filename = request.form['filename'].strip()
    if not filename.endswith('.py'):
        return jsonify(success=False, message='Filename must end with .py')
    
    try:
        # Create session ID
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Initialize status
        conversion_status[session_id] = {
            'progress': 0,
            'status': 'Initializing...',
            'completed': False,
            'success': False,
            'message': '',
            'log': [],
            'download_url': None,
            'timestamp': time.time()
        }
        
        # Create work directory
        work_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        os.makedirs(work_dir, exist_ok=True)
        
        # Save the pasted code to a file
        code = request.form['code']
        filename = secure_filename(filename)
        file_path = os.path.join(work_dir, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)
        
        # Get options
        options = {
            'one_file': 'one_file' in request.form,
            'console': 'console' in request.form,
            'uac': 'uac' in request.form,
            'debug': 'debug' in request.form,
            'packages': request.form.get('packages', ''),
            'platform': request.form.get('platform', 'auto'),
            'file_path': file_path,
            'work_dir': work_dir,
            'extra_files': []
        }
        
        # Start conversion in background thread
        thread = threading.Thread(
            target=convert_in_background,
            args=(session_id, options),
            daemon=True
        )
        thread.start()
        
        return jsonify(success=True, message='Conversion started', session_id=session_id)
        
    except Exception as e:
        logger.error(f"Error initiating conversion from pasted code: {str(e)}")
        return jsonify(success=False, message=f'Error: {str(e)}')

def update_status(session_id, progress=None, status=None, completed=None, success=None, message=None, log=None, download_url=None):
    """Update the conversion status for a session"""
    if session_id in conversion_status:
        if progress is not None:
            conversion_status[session_id]['progress'] = progress
        if status is not None:
            conversion_status[session_id]['status'] = status
        if completed is not None:
            conversion_status[session_id]['completed'] = completed
        if success is not None:
            conversion_status[session_id]['success'] = success
        if message is not None:
            conversion_status[session_id]['message'] = message
        if log is not None:
            conversion_status[session_id]['log'].append(log)
        if download_url is not None:
            conversion_status[session_id]['download_url'] = download_url

@app.route('/status/<session_id>')
def get_status(session_id):
    """Get the current conversion status"""
    if session_id not in conversion_status:
        return jsonify(
            progress=0,
            status='Session not found',
            completed=True,
            success=False,
            message='Invalid session ID',
            log=None
        )
    
    status = conversion_status[session_id]
    # Only return the latest log entry
    latest_log = status['log'][-1] if status['log'] else None
    
    return jsonify(
        progress=status['progress'],
        status=status['status'],
        completed=status['completed'],
        success=status['success'],
        message=status['message'],
        log=latest_log,
        download_url=status['download_url']
    )

def convert_in_background(session_id, options):
    """Run the conversion process in a background thread"""
    try:
        update_status(session_id, progress=5, status='Installing dependencies...')
        
        # Install required packages
        if options['packages']:
            pkg_list = [pkg.strip() for pkg in options['packages'].split(',')]
            for pkg in pkg_list:
                if pkg:
                    update_status(session_id, status=f'Installing package: {pkg}')
                    try:
                        subprocess.run(
                            [sys.executable, '-m', 'pip', 'install', pkg],
                            check=True,
                            capture_output=True,
                            timeout=120
                        )
                        update_status(session_id, log=f'Successfully installed {pkg}')
                    except Exception as e:
                        update_status(session_id, log=f'Warning: Failed to install {pkg}: {str(e)}')
        
        update_status(session_id, progress=15, status='Building PyInstaller command...')
        
        # Build PyInstaller command
        pyinstaller_cmd = ['pyinstaller']
        
        if options['one_file']:
            pyinstaller_cmd.append('--onefile')
        else:
            pyinstaller_cmd.append('--onedir')
            
        if not options['console']:
            pyinstaller_cmd.append('--windowed')
            
        # Only use UAC for Windows and not on Render
        if options['uac'] and options['platform'] == 'windows' and not ON_RENDER:
            pyinstaller_cmd.append('--uac-admin')
            
        if options['debug']:
            pyinstaller_cmd.append('--debug')
            
        # Set workdir and distpath
        pyinstaller_cmd.extend(['--workpath', os.path.join(options['work_dir'], 'build')])
        pyinstaller_cmd.extend(['--distpath', os.path.join(options['work_dir'], 'dist')])
        pyinstaller_cmd.extend(['--specpath', options['work_dir']])
        
        # Add target architecture only if not on Render
        if not ON_RENDER:
            if options['platform'] == 'windows':
                pyinstaller_cmd.extend(['--target-architecture', 'x86_64-windows'])
            elif options['platform'] == 'linux':
                pyinstaller_cmd.extend(['--target-architecture', 'x86_64-linux'])
            elif options['platform'] == 'macos':
                pyinstaller_cmd.extend(['--target-architecture', 'x86_64-darwin'])
            
        # Finally, add the script path
        pyinstaller_cmd.append(options['file_path'])
        
        # Run PyInstaller
        update_status(
            session_id, 
            progress=25, 
            status='Running PyInstaller...',
            log=f"Command: {' '.join(pyinstaller_cmd)}"
        )
        
        try:
            # Run with a timeout to prevent hanging
            result = subprocess.run(
                pyinstaller_cmd,
                check=True,
                capture_output=True,
                cwd=options['work_dir'],
                timeout=240  # 4 minutes timeout
            )
            
            stdout = result.stdout.decode()
            stderr = result.stderr.decode()
            
            # Log important output
            for line in stdout.split('\n'):
                if line.strip() and ('error' in line.lower() or 'warning' in line.lower() or 'info:' in line.lower()):
                    update_status(session_id, log=line.strip())
                    
            for line in stderr.split('\n'):
                if line.strip():
                    update_status(session_id, log=line.strip())
                    
            update_status(session_id, progress=75, status='Processing output...')
            
            # Determine output path
            script_name = os.path.splitext(os.path.basename(options['file_path']))[0]
            
            if options['platform'] == 'windows' or (options['platform'] == 'auto' and not ON_RENDER):
                exe_extension = '.exe'
            else:
                exe_extension = ''
                
            if options['one_file']:
                exe_path = os.path.join(options['work_dir'], 'dist', script_name + exe_extension)
            else:
                exe_path = os.path.join(options['work_dir'], 'dist', script_name, script_name + exe_extension)
            
            update_status(session_id, progress=85, status='Packaging results...')
            
            # Create a zip if there are multiple files or extra files
            if not options['one_file'] or options['extra_files']:
                zip_path = os.path.join(options['work_dir'], f'{script_name}_package.zip')
                with zipfile.ZipFile(zip_path, 'w') as zipf:
                    if not options['one_file']:
                        # Add all files from dist directory
                        dist_dir = os.path.join(options['work_dir'], 'dist', script_name)
                        for root, dirs, files in os.walk(dist_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, dist_dir)
                                zipf.write(file_path, arcname)
                    else:
                        # Add the exe file
                        zipf.write(exe_path, os.path.basename(exe_path))
                    
                    # Add extra files
                    for extra_file in options['extra_files']:
                        zipf.write(extra_file, os.path.basename(extra_file))
                        
                download_path = zip_path
                download_filename = os.path.basename(zip_path)
            else:
                download_path = exe_path
                download_filename = os.path.basename(exe_path)
            
            # Check if the file exists
            if os.path.exists(download_path):
                # Generate download URL
                download_url = url_for(
                    'download_file', 
                    session_id=session_id,
                    filename=download_filename
                )
                
                update_status(
                    session_id,
                    progress=100,
                    status='Conversion completed successfully!',
                    completed=True,
                    success=True,
                    message='Your executable is ready for download.',
                    download_url=download_url
                )
            else:
                update_status(
                    session_id,
                    progress=100,
                    status='Conversion failed',
                    completed=True,
                    success=False,
                    message=f'Output file not found at expected path: {download_path}'
                )
                
        except subprocess.TimeoutExpired:
            update_status(
                session_id,
                progress=100,
                status='Conversion failed',
                completed=True,
                success=False,
                message='PyInstaller process timed out. Your script may be too complex or there might be issues with dependencies.'
            )
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.decode() if e.stderr else str(e)
            update_status(
                session_id,
                progress=100,
                status='Conversion failed',
                completed=True,
                success=False,
                message=f'PyInstaller error: {error_message}'
            )
    
    except Exception as e:
        logger.error(f"Error during conversion: {str(e)}")
        update_status(
            session_id,
            progress=100,
            status='Conversion failed',
            completed=True,
            success=False,
            message=f'Unexpected error: {str(e)}'
        )

@app.route('/download/<session_id>/<filename>')
def download_file(session_id, filename):
    if 'session_id' not in session or session['session_id'] != session_id:
        flash('Invalid download session', 'danger')
        return redirect(url_for('index'))
    
    work_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    
    if filename.endswith('.zip'):
        file_path = os.path.join(work_dir, filename)
    else:
        file_path = os.path.join(work_dir, 'dist', filename)
    
    if not os.path.exists(file_path):
        flash('File not found', 'danger')
        return redirect(url_for('index'))
        
    return send_file(file_path, as_attachment=True)

@app.route('/cleanup/<session_id>')
def cleanup(session_id):
    if 'session_id' in session and session['session_id'] == session_id:
        work_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        
        # Clean up status dictionary
        if session_id in conversion_status:
            del conversion_status[session_id]
            
        session.pop('session_id', None)
    
    return redirect(url_for('index'))

# Periodic cleanup task
def cleanup_old_sessions():
    while True:
        try:
            current_time = time.time()
            
            # Clean up old status entries
            session_ids = list(conversion_status.keys())
            for session_id in session_ids:
                if conversion_status[session_id]['completed'] and current_time - conversion_status[session_id].get('timestamp', 0) > 3600:
                    del conversion_status[session_id]
            
            # Clean up old directories
            for item in os.listdir(app.config['UPLOAD_FOLDER']):
                item_path = os.path.join(app.config['UPLOAD_FOLDER'], item)
                if os.path.isdir(item_path):
                    # Check if directory is older than 1 hour
                    if current_time - os.path.getmtime(item_path) > 3600:
                        logger.info(f"Cleaning up old session: {item}")
                        shutil.rmtree(item_path)
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            
        # Sleep for 15 minutes
        time.sleep(900)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_sessions, daemon=True)
cleanup_thread.start()

# Ensure PyInstaller is installed
def ensure_pyinstaller():
    try:
        import PyInstaller
    except ImportError:
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', 'pyinstaller'],
                check=True
            )
            logger.info("PyInstaller installed successfully")
        except Exception as e:
            logger.error(f"Failed to install PyInstaller: {str(e)}")
            print(f"Error installing PyInstaller: {str(e)}")
            # Continue anyway, we'll handle it during conversion

if __name__ == '__main__':
    ensure_pyinstaller()
    # For render.com deployment
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)