#!/usr/bin/env python3
"""
Screenshot Re-Edit Web Panel - Single File Complete Application
Created by Ali HAMZA
All-in-one solution for payment screenshot analysis and editing
"""

import os
import json
import base64
import cv2
import numpy as np
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import pytesseract
from PIL import Image
import google.generativeai as genai
import re
from datetime import datetime
import logging
import tempfile
import io

# Configure Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['SECRET_KEY'] = 'ali-hamza-screenshot-panel-2026'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Gemini API
GEMINI_API_KEY = "AIzaSyAN9zL1fa4thBzp-OFIbWjN7th3mIpq-7w"
try:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("✅ Gemini API configured successfully")
    GEMINI_AVAILABLE = True
except Exception as e:
    logger.error(f"❌ Gemini API configuration failed: {e}")
    GEMINI_AVAILABLE = False

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def preprocess_image_for_ocr(image_data):
    """Preprocess image for better OCR results"""
    try:
        # Convert bytes to numpy array
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return None
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply denoising
        denoised = cv2.fastNlMeansDenoising(gray)
        
        # Apply threshold for better contrast
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Convert back to PIL Image
        pil_image = Image.fromarray(thresh)
        return pil_image
        
    except Exception as e:
        logger.error(f"Image preprocessing error: {e}")
        return Image.open(io.BytesIO(image_data))

def extract_with_tesseract(image_data):
    """Extract text using Tesseract OCR"""
    try:
        # Preprocess image
        processed_image = preprocess_image_for_ocr(image_data)
        if processed_image is None:
            return ""
        
        # Extract text with different PSM modes
        configs = ['--psm 6', '--psm 4', '--psm 3']
        best_text = ""
        
        for config in configs:
            try:
                text = pytesseract.image_to_string(processed_image, config=config)
                if len(text.strip()) > len(best_text.strip()):
                    best_text = text
            except:
                continue
        
        logger.info(f"Tesseract extracted {len(best_text)} characters")
        return best_text
        
    except Exception as e:
        logger.error(f"Tesseract extraction error: {e}")
        return ""

def extract_with_gemini(image_data, mime_type):
    """Extract and analyze text using Gemini Vision API"""
    try:
        if not GEMINI_AVAILABLE:
            return {}
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-pro-vision')
        
        # Create PIL Image
        pil_image = Image.open(io.BytesIO(image_data))
        
        # Enhanced prompt for payment screenshot analysis
        prompt = """
        Analyze this payment screenshot and extract ALL information in JSON format:
        
        {
            "transaction_id": "TID, Transaction ID, or Reference number",
            "amount": "complete amount with currency (Rs., PKR, etc.)",
            "date": "full date and time as shown",
            "sender": "sender name or from field",
            "receiver": "receiver name or to field", 
            "fee": "any fee or charges mentioned",
            "payment_method": "payment app or method used",
            "status": "transaction status (Successful, Failed, Pending)",
            "phone_numbers": ["all phone numbers found"],
            "reference": "additional reference numbers",
            "bank_info": "bank or financial institution",
            "location": "any location mentioned",
            "all_text": "complete raw extracted text"
        }
        
        Extract EXACTLY what you see. Use null for missing fields, not empty strings.
        Be very careful with amounts and numbers. Include currency symbols.
        """
        
        # Generate response
        response = model.generate_content([prompt, pil_image])
        
        # Parse JSON from response
        try:
            response_text = response.text.strip()
            
            # Find JSON in response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                extracted_data = json.loads(json_match.group())
                logger.info("✅ Gemini extraction successful")
                return extracted_data
            else:
                logger.warning("⚠️ No JSON found in Gemini response")
                return {"all_text": response_text}
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            return {"all_text": response.text}
            
    except Exception as e:
        logger.error(f"Gemini extraction error: {e}")
        return {"error": str(e)}

def parse_text_manually(text):
    """Parse extracted text to find payment information"""
    data = {
        "transaction_id": None,
        "amount": None,
        "date": None,
        "sender": None,
        "receiver": None,
        "fee": None,
        "payment_method": None,
        "status": None,
        "phone_numbers": [],
        "reference": None,
        "bank_info": None,
        "location": None,
        "all_text": text
    }
    
    # Enhanced pattern matching
    patterns = {
        'transaction_id': [
            r'TID[:\s]*([A-Za-z0-9]+)',
            r'Transaction\s+ID[:\s]*([A-Za-z0-9]+)',
            r'Ref[:\s]*([A-Za-z0-9]+)',
            r'Reference[:\s]*([A-Za-z0-9]+)',
        ],
        'amount': [
            r'Rs\.?\s*([0-9,]+\.?\d*)',
            r'PKR\s*([0-9,]+\.?\d*)',
            r'₨\s*([0-9,]+\.?\d*)',
        ],
        'date': [
            r'(\w+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2})',
            r'On\s+(\w+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2})',
            r'(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2})',
        ],
        'fee': [
            r'Fee[:\s]*Rs\.?\s*([0-9,]+\.?\d*)',
            r'Charges[:\s]*Rs\.?\s*([0-9,]+\.?\d*)',
        ]
    }
    
    # Apply patterns
    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if field in ['amount', 'fee']:
                    data[field] = f"Rs. {match.group(1)}"
                else:
                    data[field] = match.group(1)
                break
    
    # Extract phone numbers
    phone_patterns = [
        r'(\+92\d{10})',  # +92 format
        r'(03\d{9})',     # Mobile format  
        r'(\d{11})',      # 11 digit numbers
    ]
    
    phone_numbers = set()
    for pattern in phone_patterns:
        matches = re.findall(pattern, text)
        phone_numbers.update(matches)
    data["phone_numbers"] = list(phone_numbers)
    
    # Extract names and status
    lines = text.split('\n')
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Sender/receiver detection
        if 'from' in line_lower and i + 1 < len(lines):
            potential_sender = lines[i + 1].strip()
            if not re.search(r'\d{10,}', potential_sender):
                data["sender"] = potential_sender
        
        if 'to' in line_lower and 'total' not in line_lower and i + 1 < len(lines):
            potential_receiver = lines[i + 1].strip()
            if not re.search(r'\d{10,}', potential_receiver):
                data["receiver"] = potential_receiver
        
        # Status detection
        if 'successful' in line_lower:
            data["status"] = "Successful"
        elif 'failed' in line_lower:
            data["status"] = "Failed"
        elif 'pending' in line_lower:
            data["status"] = "Pending"
    
    # Payment method detection
    methods = ['jazzcash', 'easypaisa', 'ubl', 'hbl', 'bank', 'wallet']
    for method in methods:
        if method in text.lower():
            data["payment_method"] = method.title()
            break
    
    return data

# HTML Template (embedded in Python)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Screenshot Re-Edit Panel - Ali HAMZA</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.1.3/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        .main-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
            margin: 20px;
            padding: 30px;
        }
        
        .upload-area {
            border: 3px dashed #667eea;
            border-radius: 15px;
            padding: 40px;
            text-align: center;
            background: rgba(102, 126, 234, 0.05);
            transition: all 0.3s ease;
            cursor: pointer;
        }
        
        .upload-area:hover {
            border-color: #764ba2;
            background: rgba(118, 75, 162, 0.1);
        }
        
        .upload-area.dragover {
            border-color: #28a745;
            background: rgba(40, 167, 69, 0.1);
        }
        
        .upload-icon {
            font-size: 3rem;
            color: #667eea;
            margin-bottom: 20px;
        }
        
        .btn-primary {
            background: linear-gradient(45deg, #667eea, #764ba2);
            border: none;
            border-radius: 25px;
            padding: 10px 30px;
            font-weight: 600;
        }
        
        .btn-success {
            background: linear-gradient(45deg, #28a745, #20c997);
            border: none;
            border-radius: 25px;
            padding: 8px 25px;
        }
        
        .form-control {
            border-radius: 10px;
            border: 2px solid #e9ecef;
            padding: 12px 15px;
        }
        
        .form-control:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
        }
        
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.08);
        }
        
        .card-header {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border-radius: 15px 15px 0 0 !important;
            padding: 15px 20px;
        }
        
        .preview-image {
            max-width: 100%;
            max-height: 400px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }
        
        .extracted-text {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 15px;
            font-family: monospace;
            font-size: 0.9rem;
            max-height: 300px;
            overflow-y: auto;
        }
        
        .loading-spinner {
            display: none;
            text-align: center;
            padding: 40px;
        }
        
        .spinner-border {
            color: #667eea;
        }
        
        .success-message, .error-message {
            display: none;
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
        }
        
        .success-message {
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
        }
        
        .error-message {
            background: linear-gradient(45deg, #dc3545, #e74c3c);
            color: white;
        }
        
        .badge {
            font-size: 0.8rem;
            padding: 5px 10px;
        }
        
        .gemini-badge {
            background: linear-gradient(45deg, #4285f4, #34a853);
        }
        
        .tesseract-badge {
            background: linear-gradient(45deg, #ff6b6b, #ee5a24);
        }
        
        .field-group {
            margin-bottom: 20px;
        }
        
        .field-label {
            font-weight: 600;
            color: #495057;
            margin-bottom: 8px;
        }
        
        .stats-card {
            background: linear-gradient(45deg, #ffeaa7, #fab1a0);
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="main-container">
            <!-- Header -->
            <div class="text-center mb-4">
                <h1 class="display-4 fw-bold text-primary">
                    <i class="fas fa-image me-3"></i>Screenshot Re-Edit Panel
                </h1>
                <p class="lead text-muted">AI-Powered Payment Screenshot Analysis & Editing</p>
                <div class="stats-card">
                    <strong>🤖 AI Status:</strong> 
                    <span id="aiStatus">{{ 'Gemini AI Ready' if gemini_available else 'Tesseract OCR Only' }}</span>
                    <br><small>Upload any payment screenshot to extract and edit information</small>
                </div>
            </div>
            
            <!-- Upload Section -->
            <div class="row">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="fas fa-upload me-2"></i>Upload Payment Screenshot</h5>
                        </div>
                        <div class="card-body">
                            <div class="upload-area" id="uploadArea">
                                <div class="upload-icon">
                                    <i class="fas fa-cloud-upload-alt"></i>
                                </div>
                                <h4>Drop your screenshot here</h4>
                                <p class="text-muted mb-3">JazzCash, EasyPaisa, Bank Transfer receipts</p>
                                <input type="file" id="fileInput" accept="image/*" style="display: none;">
                                <button class="btn btn-primary" onclick="document.getElementById('fileInput').click()">
                                    <i class="fas fa-folder-open me-2"></i>Choose Screenshot
                                </button>
                                <div class="mt-3">
                                    <small class="text-muted">PNG, JPG, GIF, BMP, WEBP (Max: 16MB)</small>
                                </div>
                            </div>
                            
                            <div class="loading-spinner" id="loadingSpinner">
                                <div class="spinner-border spinner-border-lg" role="status"></div>
                                <h5 class="mt-3">🤖 AI Processing Screenshot...</h5>
                                <p class="text-muted">Extracting payment information using AI</p>
                            </div>
                            
                            <div class="success-message" id="successMessage">
                                <i class="fas fa-check-circle me-2"></i>Screenshot processed successfully!
                            </div>
                            
                            <div class="error-message" id="errorMessage">
                                <i class="fas fa-exclamation-triangle me-2"></i><span id="errorText"></span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Results Section -->
            <div class="row mt-4" id="resultsSection" style="display: none;">
                <!-- Image Preview -->
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="fas fa-image me-2"></i>Original Screenshot</h5>
                        </div>
                        <div class="card-body text-center">
                            <img id="previewImage" class="preview-image" alt="Payment screenshot">
                        </div>
                    </div>
                    
                    <!-- Extracted Text -->
                    <div class="card mt-3">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h5 class="mb-0"><i class="fas fa-file-text me-2"></i>Extracted Text</h5>
                            <span id="extractionMethod" class="badge"></span>
                        </div>
                        <div class="card-body">
                            <div class="extracted-text" id="extractedText"></div>
                        </div>
                    </div>
                </div>
                
                <!-- Edit Form -->
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="fas fa-edit me-2"></i>Edit Payment Information</h5>
                        </div>
                        <div class="card-body">
                            <form id="editForm">
                                <div class="field-group">
                                    <label class="field-label">💳 Transaction ID</label>
                                    <input type="text" class="form-control" id="transaction_id" name="transaction_id" placeholder="TID or Reference number">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">💰 Amount</label>
                                    <input type="text" class="form-control" id="amount" name="amount" placeholder="Rs. 0.00">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">📅 Date & Time</label>
                                    <input type="text" class="form-control" id="date" name="date" placeholder="Date and time">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">👤 Sender</label>
                                    <input type="text" class="form-control" id="sender" name="sender" placeholder="From name">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">👤 Receiver</label>
                                    <input type="text" class="form-control" id="receiver" name="receiver" placeholder="To name">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">💸 Fee</label>
                                    <input type="text" class="form-control" id="fee" name="fee" placeholder="Rs. 0.00">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">📱 Payment Method</label>
                                    <input type="text" class="form-control" id="payment_method" name="payment_method" placeholder="JazzCash, EasyPaisa, etc.">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">✅ Status</label>
                                    <input type="text" class="form-control" id="status" name="status" placeholder="Successful, Failed, Pending">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">📞 Phone Numbers</label>
                                    <input type="text" class="form-control" id="phone_numbers" name="phone_numbers" placeholder="03xxxxxxxxx, 03xxxxxxxxx">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">🏦 Bank/Reference</label>
                                    <input type="text" class="form-control" id="reference" name="reference" placeholder="Additional reference">
                                </div>
                                
                                <div class="text-center">
                                    <button type="submit" class="btn btn-success btn-lg">
                                        <i class="fas fa-save me-2"></i>Save & Export Data
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.1.3/js/bootstrap.bundle.min.js"></script>
    <script>
        let currentFilename = '';
        
        // Elements
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const loadingSpinner = document.getElementById('loadingSpinner');
        const successMessage = document.getElementById('successMessage');
        const errorMessage = document.getElementById('errorMessage');
        const resultsSection = document.getElementById('resultsSection');
        
        // Drag and drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                handleFile(e.dataTransfer.files[0]);
            }
        });
        
        uploadArea.addEventListener('click', () => {
            fileInput.click();
        });
        
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFile(e.target.files[0]);
            }
        });
        
        function handleFile(file) {
            if (!file.type.startsWith('image/')) {
                showError('Please select a valid image file');
                return;
            }
            
            if (file.size > 16 * 1024 * 1024) {
                showError('File size must be less than 16MB');
                return;
            }
            
            uploadFile(file);
        }
        
        function uploadFile(file) {
            const formData = new FormData();
            formData.append('file', file);
            
            hideMessages();
            loadingSpinner.style.display = 'block';
            resultsSection.style.display = 'none';
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                loadingSpinner.style.display = 'none';
                
                if (data.success) {
                    showSuccess();
                    displayResults(data);
                } else {
                    showError(data.error || 'Processing failed');
                }
            })
            .catch(error => {
                loadingSpinner.style.display = 'none';
                showError('Network error: ' + error.message);
            });
        }
        
        function displayResults(data) {
            currentFilename = data.filename;
            
            // Show preview
            document.getElementById('previewImage').src = data.image_url;
            
            // Show method badge
            const methodBadge = document.getElementById('extractionMethod');
            if (data.extraction_method === 'gemini') {
                methodBadge.textContent = '🤖 Gemini AI';
                methodBadge.className = 'badge gemini-badge';
            } else {
                methodBadge.textContent = '🔍 Tesseract OCR';
                methodBadge.className = 'badge tesseract-badge';
            }
            
            // Show text
            document.getElementById('extractedText').textContent = data.extracted_data.all_text || 'No text extracted';
            
            // Fill form
            const extractedData = data.extracted_data;
            document.getElementById('transaction_id').value = extractedData.transaction_id || '';
            document.getElementById('amount').value = extractedData.amount || '';
            document.getElementById('date').value = extractedData.date || '';
            document.getElementById('sender').value = extractedData.sender || '';
            document.getElementById('receiver').value = extractedData.receiver || '';
            document.getElementById('fee').value = extractedData.fee || '';
            document.getElementById('payment_method').value = extractedData.payment_method || '';
            document.getElementById('status').value = extractedData.status || '';
            document.getElementById('phone_numbers').value = Array.isArray(extractedData.phone_numbers) ? extractedData.phone_numbers.join(', ') : '';
            document.getElementById('reference').value = extractedData.reference || '';
            
            resultsSection.style.display = 'block';
        }
        
        // Form submission
        document.getElementById('editForm').addEventListener('submit', (e) => {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const editedData = {};
            
            for (let [key, value] of formData.entries()) {
                if (key === 'phone_numbers') {
                    editedData[key] = value.split(',').map(s => s.trim()).filter(s => s);
                } else {
                    editedData[key] = value;
                }
            }
            
            editedData.edited_at = new Date().toISOString();
            
            // Create download
            const dataStr = JSON.stringify(editedData, null, 2);
            const dataBlob = new Blob([dataStr], {type: 'application/json'});
            const url = URL.createObjectURL(dataBlob);
            const downloadLink = document.createElement('a');
            downloadLink.href = url;
            downloadLink.download = `edited_payment_data_${new Date().getTime()}.json`;
            downloadLink.click();
            URL.revokeObjectURL(url);
            
            showSuccess('✅ Data exported successfully! JSON file downloaded.');
        });
        
        function showSuccess(message = '✅ Screenshot processed successfully!') {
            hideMessages();
            successMessage.style.display = 'block';
            successMessage.innerHTML = '<i class="fas fa-check-circle me-2"></i>' + message;
        }
        
        function showError(message) {
            hideMessages();
            errorMessage.style.display = 'block';
            document.getElementById('errorText').textContent = message;
        }
        
        function hideMessages() {
            successMessage.style.display = 'none';
            errorMessage.style.display = 'none';
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Main page"""
    return render_template_string(HTML_TEMPLATE, gemini_available=GEMINI_AVAILABLE)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and process screenshot"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file or not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        
        # Read file data
        file_data = file.read()
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        
        logger.info(f"📸 Processing screenshot: {filename}")
        
        # Try Gemini first (if available)
        extraction_method = 'tesseract'
        extracted_data = {}
        
        if GEMINI_AVAILABLE:
            logger.info("🤖 Attempting Gemini AI extraction...")
            gemini_data = extract_with_gemini(file_data, file.content_type)
            if gemini_data and not gemini_data.get('error') and gemini_data.get('all_text'):
                extracted_data = gemini_data
                extraction_method = 'gemini'
                logger.info("✅ Gemini extraction successful")
            else:
                logger.warning("⚠️ Gemini extraction failed, using Tesseract")
        
        # Fallback to Tesseract
        if not extracted_data.get('all_text'):
            logger.info("🔍 Using Tesseract OCR extraction...")
            tesseract_text = extract_with_tesseract(file_data)
            extracted_data = parse_text_manually(tesseract_text)
            extraction_method = 'tesseract'
        
        # Create image URL (base64)
        image_b64 = base64.b64encode(file_data).decode()
        image_url = f"data:{file.content_type};base64,{image_b64}"
        
        logger.info(f"✅ Extraction completed using {extraction_method}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'extracted_data': extracted_data,
            'extraction_method': extraction_method,
            'gemini_available': GEMINI_AVAILABLE,
            'image_url': image_url
        })
        
    except Exception as e:
        logger.error(f"❌ Processing error: {e}")
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'gemini_available': GEMINI_AVAILABLE,
        'timestamp': datetime.now().isoformat(),
        'version': '1.0'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use environment PORT for hosting
    print("🚀 Starting Ali HAMZA's Screenshot Re-Edit Panel...")
    print(f"🤖 Gemini AI: {'✅ Available' if GEMINI_AVAILABLE else '❌ Not Available'}")
    print(f"📱 Access at: http://localhost:{port}")
    print("=" * 50)
    
    app.run(
        debug=False,  # Disable debug for production
        host='0.0.0.0',
        port=port,
        threaded=True
    )
