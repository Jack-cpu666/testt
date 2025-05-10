import os
import shutil
import zipfile
import subprocess
import tempfile
import uuid
from flask import Flask, request, render_template_string, send_file, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import logging
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['ALLOWED_EXTENSIONS'] = {'py'}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            display: none;
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
            <form method="POST" action="{{ url_for('upload_file') }}" enctype="multipart/form-data" id="uploadForm">
                <div class="mb-3">
                    <label for="pyfile" class="form-label">Select Python file:</label>
                    <input type="file" class="form-control" id="pyfile" name="file" accept=".py" required>
                </div>
                
                <div class="options-container">
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
                
                <button type="submit" class="btn btn-primary w-100" id="submitBtn">Convert to EXE</button>
            </form>
            
            <div class="progress">
                <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%"></div>
            </div>
        </div>
        
        <div class="log-container" id="logContainer" style="display: none;">
            <h5>Build Log:</h5>
            <div id="logContent"></div>
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
        document.getElementById('uploadForm').addEventListener('submit', function() {
            document.querySelector('.progress').style.display = 'block';
            document.getElementById('logContainer').style.display = 'block';
            document.getElementById('submitBtn').disabled = true;
            document.getElementById('submitBtn').innerHTML = 'Converting... Please wait';
            
            // Simulate progress updates (in a real app, this would be updated by server events)
            let progress = 0;
            const progressBar = document.querySelector('.progress-bar');
            const logContent = document.getElementById('logContent');
            
            const updateProgress = () => {
                if (progress < 90) {
                    progress += Math.random() * 10;
                    progressBar.style.width = progress + '%';
                    
                    // Add fake log messages
                    const messages = [
                        "Analyzing Python dependencies...",
                        "Running PyInstaller...",
                        "Collecting modules...",
                        "Building EXE...",
                        "Optimizing executable size...",
                        "Packaging additional files...",
                        "Finalizing build..."
                    ];
                    
                    if (progress > 20 && progress < 80 && Math.random() > 0.7) {
                        const logMsg = messages[Math.floor(Math.random() * messages.length)];
                        logContent.innerHTML += `<div>[${new Date().toLocaleTimeString()}] ${logMsg}</div>`;
                        logContent.scrollTop = logContent.scrollHeight;
                    }
                    
                    setTimeout(updateProgress, 800);
                }
            };
            
            updateProgress();
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
    session_id = str(uuid.uuid4())
    session['session_id'] = session_id
    
    work_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    os.makedirs(work_dir, exist_ok=True)
    
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        try:
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
            one_file = 'one_file' in request.form
            console = 'console' in request.form
            uac = 'uac' in request.form
            debug = 'debug' in request.form
            packages = request.form.get('packages', '')
            platform = request.form.get('platform', 'auto')
            
            # Convert to executable
            exe_path = convert_to_exe(
                file_path, 
                work_dir, 
                one_file=one_file,
                console=console,
                uac=uac,
                debug=debug,
                packages=packages,
                platform=platform
            )
            
            if exe_path:
                # Create a zip if there are multiple files
                if not one_file:
                    zip_path = os.path.join(work_dir, 'executable.zip')
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for root, dirs, files in os.walk(os.path.dirname(exe_path)):
                            for file in files:
                                zipf.write(
                                    os.path.join(root, file),
                                    os.path.relpath(os.path.join(root, file), os.path.dirname(work_dir))
                                )
                    download_path = zip_path
                else:
                    download_path = exe_path
                
                # Generate download link
                download_url = url_for('download_file', session_id=session_id, 
                                       filename=os.path.basename(download_path))
                
                return render_template_string(
                    HTML_TEMPLATE, 
                    current_year=datetime.now().year,
                    download_link=download_url
                )
            else:
                flash('Conversion failed. Check your script for errors.', 'danger')
                return redirect(url_for('index'))
                
        except Exception as e:
            logger.error(f"Error during conversion: {str(e)}")
            flash(f'Error during conversion: {str(e)}', 'danger')
            return redirect(url_for('index'))
    else:
        flash('Only Python (.py) files are allowed', 'warning')
        return redirect(url_for('index'))

def convert_to_exe(file_path, work_dir, one_file=True, console=True, uac=False, 
                   debug=False, packages='', platform='auto'):
    """
    Convert Python script to executable using PyInstaller
    """
    try:
        # Install required packages
        if packages:
            pkg_list = [pkg.strip() for pkg in packages.split(',')]
            for pkg in pkg_list:
                if pkg:
                    subprocess.run(
                        [sys.executable, '-m', 'pip', 'install', pkg],
                        check=True,
                        capture_output=True
                    )
        
        # Build PyInstaller command
        pyinstaller_cmd = ['pyinstaller']
        
        if one_file:
            pyinstaller_cmd.append('--onefile')
        else:
            pyinstaller_cmd.append('--onedir')
            
        if not console:
            pyinstaller_cmd.append('--windowed')
            
        if uac and platform != 'linux':
            pyinstaller_cmd.append('--uac-admin')
            
        if debug:
            pyinstaller_cmd.append('--debug')
            
        # Set workdir and distpath
        pyinstaller_cmd.extend(['--workpath', os.path.join(work_dir, 'build')])
        pyinstaller_cmd.extend(['--distpath', os.path.join(work_dir, 'dist')])
        pyinstaller_cmd.extend(['--specpath', work_dir])
        
        # Add platform if specified
        if platform == 'windows':
            pyinstaller_cmd.extend(['--target-architecture', 'x86_64-windows'])
        elif platform == 'linux':
            pyinstaller_cmd.extend(['--target-architecture', 'x86_64-linux'])
        elif platform == 'macos':
            pyinstaller_cmd.extend(['--target-architecture', 'x86_64-darwin'])
            
        # Finally, add the script path
        pyinstaller_cmd.append(file_path)
        
        # Run PyInstaller
        logger.info(f"Running PyInstaller with command: {' '.join(pyinstaller_cmd)}")
        result = subprocess.run(
            pyinstaller_cmd,
            check=True,
            capture_output=True,
            cwd=work_dir
        )
        
        logger.info(f"PyInstaller stdout: {result.stdout.decode()}")
        logger.info(f"PyInstaller stderr: {result.stderr.decode()}")
        
        # Determine output path
        script_name = os.path.splitext(os.path.basename(file_path))[0]
        if platform == 'windows' or platform == 'auto' and os.name == 'nt':
            exe_extension = '.exe'
        else:
            exe_extension = ''
            
        if one_file:
            exe_path = os.path.join(work_dir, 'dist', script_name + exe_extension)
        else:
            if platform == 'windows' or platform == 'auto' and os.name == 'nt':
                exe_path = os.path.join(work_dir, 'dist', script_name, script_name + exe_extension)
            else:
                exe_path = os.path.join(work_dir, 'dist', script_name, script_name)
        
        if os.path.exists(exe_path):
            return exe_path
        else:
            logger.error(f"Executable not found at expected path: {exe_path}")
            return None
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running PyInstaller: {e.stderr.decode() if e.stderr else str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during conversion: {str(e)}")
        return None

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
        session.pop('session_id', None)
    
    return redirect(url_for('index'))

# Periodic cleanup task
def cleanup_old_sessions():
    import threading
    import time
    
    while True:
        try:
            # Get all session directories
            for item in os.listdir(app.config['UPLOAD_FOLDER']):
                item_path = os.path.join(app.config['UPLOAD_FOLDER'], item)
                if os.path.isdir(item_path):
                    # Check if directory is older than 1 hour
                    if time.time() - os.path.getmtime(item_path) > 3600:
                        logger.info(f"Cleaning up old session: {item}")
                        shutil.rmtree(item_path)
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            
        # Sleep for 15 minutes
        time.sleep(900)

# Start cleanup thread
import threading
import sys
cleanup_thread = threading.Thread(target=cleanup_old_sessions, daemon=True)
cleanup_thread.start()

# Ensure PyInstaller is installed
def ensure_pyinstaller():
    try:
        import PyInstaller
    except ImportError:
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'pyinstaller'],
            check=True
        )

if __name__ == '__main__':
    ensure_pyinstaller()
    # For render.com deployment
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)