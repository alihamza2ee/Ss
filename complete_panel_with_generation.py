#!/usr/bin/env python3
"""
Screenshot Re-Edit Web Panel - Complete Version with Screenshot Generation
Creates new screenshot with edited information
"""

import os
import json
import base64
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
import pytesseract
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import google.generativeai as genai
import re
from datetime import datetime
import logging
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
    """Preprocess image using only PIL/Pillow for better OCR"""
    try:
        pil_image = Image.open(io.BytesIO(image_data))
        
        # Convert to grayscale
        if pil_image.mode != 'L':
            pil_image = pil_image.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(pil_image)
        pil_image = enhancer.enhance(1.5)
        
        # Enhance sharpness
        enhancer = ImageEnhance.Sharpness(pil_image)
        pil_image = enhancer.enhance(2.0)
        
        return pil_image
        
    except Exception as e:
        logger.error(f"Image preprocessing error: {e}")
        return Image.open(io.BytesIO(image_data))

def extract_with_tesseract(image_data):
    """Extract text using Tesseract OCR with PIL preprocessing"""
    try:
        # Preprocess image
        processed_image = preprocess_image_for_ocr(image_data)
        
        # Extract text with different configurations
        configs = [
            '--psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz:.,/-+ ',
            '--psm 4',
            '--psm 3'
        ]
        
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

def generate_new_screenshot(edited_data, template_type="jazzcash"):
    """Generate new screenshot with edited information"""
    try:
        # Create image canvas
        width, height = 400, 600
        
        # Background gradient colors
        if template_type.lower() == "jazzcash":
            color1 = (255, 165, 0)  # Orange
            color2 = (255, 140, 0)  # Dark orange
        else:
            color1 = (34, 139, 34)  # Green
            color2 = (0, 100, 0)    # Dark green
            
        # Create gradient background
        img = Image.new('RGB', (width, height), color1)
        draw = ImageDraw.Draw(img)
        
        # Create gradient effect
        for y in range(height):
            r = color1[0] + (color2[0] - color1[0]) * y // height
            g = color1[1] + (color2[1] - color1[1]) * y // height  
            b = color1[2] + (color2[2] - color1[2]) * y // height
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        # Try to load custom font, fallback to default
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            large_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        except:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            large_font = ImageFont.load_default()
        
        # White rounded rectangle for content
        content_rect = [50, 80, width-50, height-80]
        draw.rounded_rectangle(content_rect, radius=15, fill='white')
        
        # Title
        status = edited_data.get('status', 'Transaction Successful')
        draw.text((width//2, 50), status, fill='white', font=title_font, anchor='mm')
        
        # Transaction ID
        tid = edited_data.get('transaction_id', '')
        if tid:
            draw.text((width//2, 120), f"TID: {tid}", fill='black', font=text_font, anchor='mm')
        
        # Date
        date = edited_data.get('date', datetime.now().strftime("%B %d, %Y at %H:%M"))
        draw.text((width//2, 145), date, fill='gray', font=text_font, anchor='mm')
        
        # Amount (large)
        amount = edited_data.get('amount', 'Rs. 0.00')
        draw.text((width//2, 220), amount, fill='black', font=large_font, anchor='mm')
        
        # Payment method
        method = edited_data.get('payment_method', 'QR Payment')
        draw.text((width//2, 260), method, fill='gray', font=text_font, anchor='mm')
        
        # Fee
        fee = edited_data.get('fee', 'Rs. 0.00')
        draw.text((70, 320), "Fee", fill='black', font=text_font)
        draw.text((width-70, 320), fee, fill='black', font=text_font, anchor='rm')
        
        # Separator line
        draw.line([(70, 345), (width-70, 345)], fill='lightgray', width=1)
        
        # To
        receiver = edited_data.get('receiver', 'Receiver Name')
        phone_numbers = edited_data.get('phone_numbers', [])
        receiver_phone = phone_numbers[0] if phone_numbers else ''
        
        draw.text((70, 370), "To", fill='black', font=text_font)
        draw.text((width-70, 370), receiver, fill='black', font=text_font, anchor='rm')
        if receiver_phone:
            draw.text((width-70, 395), receiver_phone, fill='gray', font=text_font, anchor='rm')
        
        # Separator line
        draw.line([(70, 425), (width-70, 425)], fill='lightgray', width=1)
        
        # From
        sender = edited_data.get('sender', 'Sender Name')
        sender_phone = phone_numbers[1] if len(phone_numbers) > 1 else phone_numbers[0] if phone_numbers else ''
        
        draw.text((70, 450), "From", fill='black', font=text_font)
        draw.text((width-70, 450), sender, fill='black', font=text_font, anchor='rm')
        if sender_phone:
            draw.text((width-70, 475), sender_phone, fill='gray', font=text_font, anchor='rm')
        
        # Bottom branding
        brand_text = template_type.title() if template_type else "Payment App"
        draw.text((width//2, height-30), f"Securely paid via {brand_text}", fill='white', font=text_font, anchor='mm')
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', quality=95)
        buffer.seek(0)
        
        image_b64 = base64.b64encode(buffer.getvalue()).decode()
        
        logger.info("✅ New screenshot generated successfully")
        return f"data:image/png;base64,{image_b64}"
        
    except Exception as e:
        logger.error(f"Screenshot generation error: {e}")
        return None

# HTML Template with Screenshot Generation
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
        
        .btn-warning {
            background: linear-gradient(45deg, #ff6b35, #f7931e);
            border: none;
            border-radius: 25px;
            padding: 8px 25px;
            color: white;
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
        
        .generated-screenshot {
            border: 2px solid #28a745;
            border-radius: 10px;
            padding: 10px;
            background: #f8f9fa;
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
                <p class="lead text-muted">Upload → AI Extract → Edit → Generate New Screenshot</p>
                <div class="stats-card">
                    <strong>🤖 Status:</strong> 
                    <span id="aiStatus">{{ 'Gemini AI Ready' if gemini_available else 'Tesseract OCR Only' }}</span>
                    | <strong>🎨 Feature:</strong> Screenshot Generation Ready
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
                                <h4>Drop Payment Screenshot Here</h4>
                                <p class="text-muted mb-3">JazzCash, EasyPaisa, Bank receipts</p>
                                <input type="file" id="fileInput" accept="image/*" style="display: none;">
                                <button class="btn btn-primary" onclick="document.getElementById('fileInput').click()">
                                    <i class="fas fa-folder-open me-2"></i>Choose Screenshot
                                </button>
                            </div>
                            
                            <div class="loading-spinner" id="loadingSpinner">
                                <div class="spinner-border spinner-border-lg" role="status"></div>
                                <h5 class="mt-3">🤖 Processing with AI...</h5>
                            </div>
                            
                            <div class="success-message" id="successMessage"></div>
                            <div class="error-message" id="errorMessage"></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Results Section -->
            <div class="row mt-4" id="resultsSection" style="display: none;">
                <!-- Original Image -->
                <div class="col-md-4">
                    <div class="card">
                        <div class="card-header">
                            <h6 class="mb-0"><i class="fas fa-image me-2"></i>Original</h6>
                        </div>
                        <div class="card-body text-center">
                            <img id="previewImage" class="preview-image" alt="Original" style="max-height: 250px;">
                        </div>
                    </div>
                    
                    <!-- Extracted Text -->
                    <div class="card mt-3">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h6 class="mb-0"><i class="fas fa-file-text me-2"></i>Extracted Text</h6>
                            <span id="extractionMethod" class="badge"></span>
                        </div>
                        <div class="card-body">
                            <div class="extracted-text" id="extractedText"></div>
                        </div>
                    </div>
                </div>
                
                <!-- Edit Form -->
                <div class="col-md-4">
                    <div class="card">
                        <div class="card-header">
                            <h6 class="mb-0"><i class="fas fa-edit me-2"></i>Edit Information</h6>
                        </div>
                        <div class="card-body">
                            <form id="editForm">
                                <div class="field-group">
                                    <label class="field-label">💳 Transaction ID</label>
                                    <input type="text" class="form-control form-control-sm" id="transaction_id" name="transaction_id">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">💰 Amount</label>
                                    <input type="text" class="form-control form-control-sm" id="amount" name="amount">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">📅 Date & Time</label>
                                    <input type="text" class="form-control form-control-sm" id="date" name="date">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">👤 From</label>
                                    <input type="text" class="form-control form-control-sm" id="sender" name="sender">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">👤 To</label>
                                    <input type="text" class="form-control form-control-sm" id="receiver" name="receiver">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">📞 Phone Numbers</label>
                                    <input type="text" class="form-control form-control-sm" id="phone_numbers" name="phone_numbers">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">✅ Status</label>
                                    <input type="text" class="form-control form-control-sm" id="status" name="status">
                                </div>
                                
                                <div class="field-group">
                                    <label class="field-label">🎨 Template</label>
                                    <select class="form-control form-control-sm" id="template_type" name="template_type">
                                        <option value="jazzcash">JazzCash Style</option>
                                        <option value="easypaisa">EasyPaisa Style</option>
                                        <option value="bank">Bank Transfer</option>
                                    </select>
                                </div>
                                
                                <div class="text-center mt-3">
                                    <button type="button" class="btn btn-warning me-2" onclick="generateScreenshot()">
                                        <i class="fas fa-magic me-2"></i>Generate Screenshot
                                    </button>
                                    <button type="submit" class="btn btn-success">
                                        <i class="fas fa-download me-2"></i>Export JSON
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
                
                <!-- Generated Screenshot -->
                <div class="col-md-4">
                    <div class="card" id="generatedCard" style="display: none;">
                        <div class="card-header">
                            <h6 class="mb-0"><i class="fas fa-sparkles me-2"></i>Generated Screenshot</h6>
                        </div>
                        <div class="card-body text-center">
                            <div class="generated-screenshot">
                                <img id="generatedImage" class="preview-image" alt="Generated" style="max-height: 250px;">
                                <div class="mt-3">
                                    <button class="btn btn-success btn-sm" onclick="downloadGenerated()">
                                        <i class="fas fa-download me-2"></i>Download Screenshot
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.1.3/js/bootstrap.bundle.min.js"></script>
    <script>
        let currentFilename = '';
        let generatedImageData = '';
        
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
                    showSuccess('✅ Screenshot processed successfully!');
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
            
            // Fill form - FIXED VERSION
            const extractedData = data.extracted_data;
            
            // Auto-fill with extracted data
            setTimeout(() => {
                document.getElementById('transaction_id').value = extractedData.transaction_id || '';
                document.getElementById('amount').value = extractedData.amount || '';
                document.getElementById('date').value = extractedData.date || '';
                document.getElementById('sender').value = extractedData.sender || '';
                document.getElementById('receiver').value = extractedData.receiver || '';
                document.getElementById('phone_numbers').value = Array.isArray(extractedData.phone_numbers) ? extractedData.phone_numbers.join(', ') : '';
                document.getElementById('status').value = extractedData.status || '';
            }, 500);
            
            resultsSection.style.display = 'block';
        }
        
        function generateScreenshot() {
            // Get form data
            const formData = new FormData(document.getElementById('editForm'));
            const editedData = {};
            
            for (let [key, value] of formData.entries()) {
                if (key === 'phone_numbers') {
                    editedData[key] = value.split(',').map(s => s.trim()).filter(s => s);
                } else {
                    editedData[key] = value;
                }
            }
            
            // Show loading
            showSuccess('🎨 Generating new screenshot...');
            
            fetch('/generate_screenshot', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(editedData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    generatedImageData = data.screenshot_url;
                    document.getElementById('generatedImage').src = data.screenshot_url;
                    document.getElementById('generatedCard').style.display = 'block';
                    showSuccess('✅ New screenshot generated successfully!');
                } else {
                    showError('Screenshot generation failed: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                showError('Generation error: ' + error.message);
            });
        }
        
        function downloadGenerated() {
            if (generatedImageData) {
                const downloadLink = document.createElement('a');
                downloadLink.href = generatedImageData;
                downloadLink.download = `edited_screenshot_${new Date().getTime()}.png`;
                downloadLink.click();
            }
        }
        
        // Form submission for JSON export
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
            downloadLink.download = `payment_data_${new Date().getTime()}.json`;
            downloadLink.click();
            URL.revokeObjectURL(url);
            
            showSuccess('✅ JSON data exported successfully!');
        });
        
        function showSuccess(message) {
            hideMessages();
            successMessage.style.display = 'block';
            successMessage.innerHTML = message;
        }
        
        function showError(message) {
            hideMessages();
            errorMessage.style.display = 'block';
            errorMessage.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i>' + message;
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
        
        logger.info(f"📸 Processing: {filename}")
        
        # Try Gemini first (if available)
        extraction_method = 'tesseract'
        extracted_data = {}
        
        if GEMINI_AVAILABLE:
            logger.info("🤖 Trying Gemini AI...")
            gemini_data = extract_with_gemini(file_data, file.content_type)
            if gemini_data and not gemini_data.get('error') and gemini_data.get('all_text'):
                extracted_data = gemini_data
                extraction_method = 'gemini'
                logger.info("✅ Gemini successful")
            else:
                logger.warning("⚠️ Gemini failed, using Tesseract")
        
        # Fallback to Tesseract
        if not extracted_data.get('all_text'):
            logger.info("🔍 Using Tesseract OCR...")
            tesseract_text = extract_with_tesseract(file_data)
            extracted_data = parse_text_manually(tesseract_text)
            extraction_method = 'tesseract'
        
        # Create image URL (base64)
        image_b64 = base64.b64encode(file_data).decode()
        image_url = f"data:{file.content_type};base64,{image_b64}"
        
        logger.info(f"✅ Completed with {extraction_method}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'extracted_data': extracted_data,
            'extraction_method': extraction_method,
            'gemini_available': GEMINI_AVAILABLE,
            'image_url': image_url
        })
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/generate_screenshot', methods=['POST'])
def generate_screenshot():
    """Generate new screenshot with edited data"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        template_type = data.get('template_type', 'jazzcash')
        
        logger.info(f"🎨 Generating screenshot with template: {template_type}")
        
        # Generate new screenshot
        screenshot_url = generate_new_screenshot(data, template_type)
        
        if screenshot_url:
            return jsonify({
                'success': True,
                'screenshot_url': screenshot_url,
                'template_used': template_type
            })
        else:
            return jsonify({'error': 'Screenshot generation failed'}), 500
            
    except Exception as e:
        logger.error(f"❌ Generation error: {e}")
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'gemini_available': GEMINI_AVAILABLE,
        'features': ['ai_extraction', 'screenshot_generation', 'json_export'],
        'timestamp': datetime.now().isoformat(),
        'version': 'complete-v2.0'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Ali HAMZA's Complete Screenshot Re-Edit Panel")
    print(f"🤖 Gemini AI: {'✅ Ready' if GEMINI_AVAILABLE else '❌ Not Available'}")
    print(f"🎨 Screenshot Generation: ✅ Ready")
    print(f"📱 Port: {port}")
    print("=" * 60)
    
    app.run(
        debug=False,
        host='0.0.0.0',
        port=port,
        threaded=True
    )
