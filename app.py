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
import redis
from flask_session import Session

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['ALLOWED_EXTENSIONS'] = {'py'}
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # Session lasts 1 hour
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'

# Set up Redis for session and conversion status storage
redis_url = os.environ.get('REDIS_URL')
if redis_url:
    logger.info(f"Using Redis for session storage: {redis_url}")
    app.config['SESSION_TYPE'] = 'redis'
    app.config['SESSION_REDIS'] = redis.from_url(redis_url)
else:
    logger.info("Redis URL not found, using filesystem for session storage")
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = tempfile.mkdtemp()

# Initialize the session interface
Session(app)

# Detect if running on Render
ON_RENDER = 'RENDER' in os.environ

# Redis helpers for conversion status
def get_conversion_status(session_id):
    """Get conversion status from Redis or memory"""
    if redis_url:
        r = redis.from_url(redis_url)
        status_data = r.get(f'conversion_status:{session_id}')
        return json.loads(status_data) if status_data else None
    else:
        return conversion_status.get(session_id)

def set_conversion_status(session_id, data):
    """Store conversion status in Redis or memory"""
    if redis_url:
        r = redis.from_url(redis_url)
        r.set(f'conversion_status:{session_id}', json.dumps(data))
        # Set expiration to 1 hour
        r.expire(f'conversion_status:{session_id}', 3600)
    else:
        conversion_status[session_id] = data

def update_conversion_status(session_id, progress=None, status=None, completed=None, 
                             success=None, message=None, log=None, download_url=None):
    """Update conversion status fields"""
    data = get_conversion_status(session_id)
    if data:
        if progress is not None:
            data['progress'] = progress
        if status is not None:
            data['status'] = status
        if completed is not None:
            data['completed'] = completed
        if success is not None:
            data['success'] = success
        if message is not None:
            data['message'] = message
        if log is not None:
            data['log'].append(log)
            logger.info(f"Session {session_id}: {log}")
        if download_url is not None:
            data['download_url'] = download_url
        
        set_conversion_status(session_id, data)

# In-memory fallback for conversion status if Redis is not available
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
        // Session ID storage - both in session and localStorage for resilience
        let currentSessionId = '';
        
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
            
            // Clear previous log content
            document.getElementById('logContent').innerHTML = '';
            document.getElementById('progressBar').style.width = '0%';
            document.getElementById('progressBar').classList.remove('bg-danger', 'bg-success');
            document.getElementById('progressBar').classList.add('bg-info');
            
            // Submit the form data via AJAX
            const formData = new FormData(form);
            const action = form.getAttribute('action');
            
            fetch(action, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin'  // Important for session cookies
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Store session ID in both variables and localStorage for resilience
                    currentSessionId = data.session_id;
                    localStorage.setItem('conversionSessionId', data.session_id);
                    
                    // Start polling for status updates
                    pollStatus(data.session_id);
                    
                    // Log initial status
                    const logElement = document.getElementById('logContent');
                    logElement.innerHTML += `<div>[${new Date().toLocaleTimeString()}] Conversion started with session ID: ${data.session_id}</div>`;
                } else {
                    // Show error
                    document.getElementById('statusMessage').innerText = 'Error: ' + data.message;
                    document.getElementById('progressBar').style.width = '100%';
                    document.getElementById('progressBar').classList.remove('bg-info', 'bg-success');
                    document.getElementById('progressBar').classList.add('bg-danger');
                    document.getElementById(buttonId).disabled = false;
                    document.getElementById(buttonId).innerHTML = 'Try Again';
                    
                    // Log error
                    const logElement = document.getElementById('logContent');
                    logElement.innerHTML += `<div class="text-danger">[${new Date().toLocaleTimeString()}] Error: ${data.message}</div>`;
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
                
                // Log error
                const logElement = document.getElementById('logContent');
                logElement.innerHTML += `<div class="text-danger">[${new Date().toLocaleTimeString()}] Server error: ${error.message}</div>`;
            });
        }
        
        function pollStatus(sessionId) {
            // Try up to 10 times with increasing delays if there's an error
            let retryCount = 0;
            let maxRetries = 10;
            let retryDelay = 1000;
            
            function makeStatusRequest() {
                fetch(`/status/${sessionId}`, {
                    credentials: 'same-origin'  // Important for session cookies
                })
                .then(response => response.json())
                .then(data => {
                    // Reset retry counter on successful response
                    retryCount = 0;
                    
                    // Check if session is valid
                    if (data.message === 'Invalid session ID') {
                        const logElement = document.getElementById('logContent');
                        logElement.innerHTML += `<div class="text-warning">[${new Date().toLocaleTimeString()}] Session error: Invalid session ID. Attempting recovery...</div>`;
                        
                        // Try to recover by using localStorage
                        const storedSessionId = localStorage.getItem('conversionSessionId');
                        if (storedSessionId && storedSessionId !== sessionId) {
                            logElement.innerHTML += `<div>[${new Date().toLocaleTimeString()}] Attempting to recover with stored session ID: ${storedSessionId}</div>`;
                            setTimeout(() => pollStatus(storedSessionId), 1000);
                            return;
                        }
                        
                        // If unable to recover, show error
                        document.getElementById('statusMessage').innerText = 'Session error. Please try again.';
                        document.getElementById('progressBar').style.width = '100%';
                        document.getElementById('progressBar').classList.remove('bg-info', 'bg-success');
                        document.getElementById('progressBar').classList.add('bg-danger');
                        document.getElementById('uploadSubmitBtn').disabled = false;
                        document.getElementById('uploadSubmitBtn').innerHTML = 'Try Again';
                        document.getElementById('pasteSubmitBtn').disabled = false;
                        document.getElementById('pasteSubmitBtn').innerHTML = 'Try Again';
                        return;
                    }
                    
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
                        setTimeout(() => makeStatusRequest(), 1000);
                    }
                })
                .catch(error => {
                    console.error('Error polling status:', error);
                    
                    const logElement = document.getElementById('logContent');
                    logElement.innerHTML += `<div class="text-warning">[${new Date().toLocaleTimeString()}] Network error while checking status: ${error.message}. Retrying...</div>`;
                    
                    // Implement exponential backoff for retries
                    retryCount++;
                    if (retryCount <= maxRetries) {
                        setTimeout(() => makeStatusRequest(), retryDelay);
                        retryDelay = Math.min(retryDelay * 1.5, 10000); // Cap at 10 seconds
                    } else {
                        logElement.innerHTML += `<div class="text-danger">[${new Date().toLocaleTimeString()}] Failed to connect after ${maxRetries} attempts. Please refresh and try again.</div>`;
                        document.getElementById('statusMessage').innerText = 'Connection lost. Please refresh and try again.';
                    }
                });
            }
            
            // Start the polling
            makeStatusRequest();
        }
        
        // Check for ongoing conversion on page load
        document.addEventListener('DOMContentLoaded', function() {
            const storedSessionId = localStorage.getItem('conversionSessionId');
            if (storedSessionId) {
                // Check if the stored session is still active
                fetch(`/status/${storedSessionId}`, {
                    credentials: 'same-origin'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.message !== 'Invalid session ID' && !data.completed) {
                        // Conversion is still in progress, restore UI
                        document.getElementById('conversionStatus').style.display = 'block';
                        document.getElementById('uploadSubmitBtn').disabled = true;
                        document.getElementById('uploadSubmitBtn').innerHTML = 'Converting... Please wait';
                        document.getElementById('pasteSubmitBtn').disabled = true;
                        document.getElementById('pasteSubmitBtn').innerHTML = 'Converting... Please wait';
                        
                        const logElement = document.getElementById('logContent');
                        logElement.innerHTML += `<div>[${new Date().toLocaleTimeString()}] Reconnected to conversion session: ${storedSessionId}</div>`;
                        
                        // Resume polling
                        pollStatus(storedSessionId);
                    } else if (data.completed && data.success) {
                        // Conversion is complete, show download link
                        document.getElementById('conversionStatus').style.display = 'block';
                        document.getElementById('conversionStatus').innerHTML = `
                            <div class="alert alert-success mt-3">
                                <h5>Conversion successful!</h5>
                                <p>Your executable is ready for download.</p>
                                <a href="${data.download_url}" class="btn btn-success">Download EXE</a>
                            </div>
                        `;
                    }
                })
                .catch(error => {
                    console.error('Error checking stored session:', error);
                });
            }
        });
        
        // Add window beforeunload event to warn about leaving during conversion
        window.addEventListener('beforeunload', function(e) {
            if (document.getElementById('conversionStatus').style.display !== 'none' && 
                !document.getElementById('progressBar').classList.contains('bg-success') &&
                !document.getElementById('progressBar').classList.contains('bg-danger')) {
                e.preventDefault();
                e.returnValue = 'Conversion is in progress. Are you sure you want to leave?';
                return e.returnValue;
            }
        });
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
        session.modified = True  # Explicitly mark the session as modified
        
        logger.info(f"Created new session: {session_id}")
        
        # Initialize status
        initial_status = {
            'progress': 0,
            'status': 'Initializing...',
            'completed': False,
            'success': False,
            'message': '',
            'log': [],
            'download_url': None,
            'timestamp': time.time()
        }
        set_conversion_status(session_id, initial_status)
        
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
        session.modified = True  # Explicitly mark the session as modified
        
        logger.info(f"Created new session from pasted code: {session_id}")
        
        # Initialize status
        initial_status = {
            'progress': 0,
            'status': 'Initializing...',
            'completed': False,
            'success': False,
            'message': '',
            'log': [],
            'download_url': None,
            'timestamp': time.time()
        }
        set_conversion_status(session_id, initial_status)
        
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

@app.route('/status/<session_id>')
def get_status(session_id):
    """Get the current conversion status"""
    logger.info(f"Status requested for session: {session_id}")
    
    # Try to get status from Redis/memory
    status = get_conversion_status(session_id)
    
    if not status:
        # Check if the session directory exists as fallback
        work_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        if os.path.exists(work_dir):
            logger.info(f"Session directory exists but no status found: {session_id}")
            # Return a generic status
            return jsonify(
                progress=50,
                status='Processing conversion...',
                completed=False,
                success=False,
                message='',
                log='Reconnected to existing conversion process'
            )
        
        logger.warning(f"Session ID not found: {session_id}")
        return jsonify(
            progress=0,
            status='Session not found',
            completed=True,
            success=False,
            message='Invalid session ID',
            log=None
        )
    
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
        update_conversion_status(session_id, progress=5, status='Installing dependencies...')
        
        # Install required packages
        if options['packages']:
            pkg_list = [pkg.strip() for pkg in options['packages'].split(',')]
            for pkg in pkg_list:
                if pkg:
                    update_conversion_status(session_id, status=f'Installing package: {pkg}')
                    try:
                        subprocess.run(
                            [sys.executable, '-m', 'pip', 'install', pkg],
                            check=True,
                            capture_output=True,
                            timeout=120
                        )
                        update_conversion_status(session_id, log=f'Successfully installed {pkg}')
                    except Exception as e:
                        update_conversion_status(session_id, log=f'Warning: Failed to install {pkg}: {str(e)}')
        
        update_conversion_status(session_id, progress=15, status='Building PyInstaller command...')
        
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
        update_conversion_status(
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
                    update_conversion_status(session_id, log=line.strip())
                    
            for line in stderr.split('\n'):
                if line.strip():
                    update_conversion_status(session_id, log=line.strip())
                    
            update_conversion_status(session_id, progress=75, status='Processing output...')
            
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
            
            update_conversion_status(session_id, progress=85, status='Packaging results...')
            
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
                
                update_conversion_status(
                    session_id,
                    progress=100,
                    status='Conversion completed successfully!',
                    completed=True,
                    success=True,
                    message='Your executable is ready for download.',
                    download_url=download_url
                )
            else:
                update_conversion_status(
                    session_id,
                    progress=100,
                    status='Conversion failed',
                    completed=True,
                    success=False,
                    message=f'Output file not found at expected path: {download_path}'
                )
                
        except subprocess.TimeoutExpired:
            update_conversion_status(
                session_id,
                progress=100,
                status='Conversion failed',
                completed=True,
                success=False,
                message='PyInstaller process timed out. Your script may be too complex or there might be issues with dependencies.'
            )
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.decode() if e.stderr else str(e)
            update_conversion_status(
                session_id,
                progress=100,
                status='Conversion failed',
                completed=True,
                success=False,
                message=f'PyInstaller error: {error_message}'
            )
    
    except Exception as e:
        logger.error(f"Error during conversion: {str(e)}")
        update_conversion_status(
            session_id,
            progress=100,
            status='Conversion failed',
            completed=True,
            success=False,
            message=f'Unexpected error: {str(e)}'
        )

@app.route('/download/<session_id>/<filename>')
def download_file(session_id, filename):
    logger.info(f"Download requested: {session_id}/{filename}")
    
    # More permissive approach for downloads to prevent session issues
    work_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    
    if filename.endswith('.zip'):
        file_path = os.path.join(work_dir, filename)
    else:
        file_path = os.path.join(work_dir, 'dist', filename)
    
    if not os.path.exists(file_path):
        flash('File not found', 'danger')
        return redirect(url_for('index'))
    
    logger.info(f"Sending file: {file_path}")
    return send_file(file_path, as_attachment=True)

@app.route('/cleanup/<session_id>')
def cleanup(session_id):
    # Try to get status from Redis
    status = get_conversion_status(session_id)
    
    # Remove the work directory if it exists
    work_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    if os.path.exists(work_dir):
        try:
            shutil.rmtree(work_dir)
            logger.info(f"Cleaned up session directory: {session_id}")
        except Exception as e:
            logger.error(f"Error cleaning up directory for session {session_id}: {str(e)}")
    
    # If using Redis, delete the key
    if redis_url:
        try:
            r = redis.from_url(redis_url)
            r.delete(f'conversion_status:{session_id}')
            logger.info(f"Removed session from Redis: {session_id}")
        except Exception as e:
            logger.error(f"Error removing session from Redis: {str(e)}")
    else:
        # If using memory, remove from dict
        if session_id in conversion_status:
            del conversion_status[session_id]
            logger.info(f"Removed session from memory tracker: {session_id}")
    
    # Clear session cookie
    session.clear()
    
    return redirect(url_for('index'))

# Add a health check endpoint
@app.route('/health')
def health_check():
    return jsonify(status="healthy", uptime=time.time())

# Periodic cleanup task
def cleanup_old_sessions():
    while True:
        try:
            current_time = time.time()
            
            # Clean up old status entries in Redis
            if redis_url:
                r = redis.from_url(redis_url)
                # Redis already handles expiration, nothing to do here
            else:
                # If using memory dict, clean up old entries
                session_ids = list(conversion_status.keys())
                for session_id in session_ids:
                    if conversion_status[session_id]['completed'] and current_time - conversion_status[session_id].get('timestamp', 0) > 3600:
                        del conversion_status[session_id]
                        logger.info(f"Cleaned up old session from memory tracker: {session_id}")
            
            # Clean up old directories
            for item in os.listdir(app.config['UPLOAD_FOLDER']):
                item_path = os.path.join(app.config['UPLOAD_FOLDER'], item)
                if os.path.isdir(item_path):
                    # Check if directory is older than 1 hour
                    if current_time - os.path.getmtime(item_path) > 3600:
                        try:
                            logger.info(f"Cleaning up old session directory: {item}")
                            shutil.rmtree(item_path)
                        except Exception as e:
                            logger.error(f"Error cleaning up directory {item}: {str(e)}")
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
        logger.info("PyInstaller is already installed")
    except ImportError:
        try:
            logger.info("Installing PyInstaller...")
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
    # Ensure temp directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    logger.info(f"Using temp directory: {app.config['UPLOAD_FOLDER']}")
    
    # Install required packages
    ensure_pyinstaller()
    
    # For render.com deployment
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
