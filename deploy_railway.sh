#!/bin/bash

echo "🚀 Railway Deployment Guide for Screenshot Panel"
echo "================================================"

# Step 1: Prepare files
echo "📁 Step 1: Preparing deployment files..."
cp requirements_deploy.txt requirements.txt

# Step 2: Create .gitignore
cat > .gitignore << EOF
__pycache__/
*.pyc
*.pyo
*.pyd
.env
.venv/
venv/
uploads/
processed/
*.log
.DS_Store
EOF

echo "✅ Deployment files ready!"
echo ""
echo "📋 Next Steps:"
echo "1. 🌐 GitHub Account banao: https://github.com"
echo "2. 📂 New repository create karo"
echo "3. 📤 Ye files upload karo:"
echo "   - single_file_panel.py"
echo "   - requirements.txt"
echo "   - Procfile"
echo "   - runtime.txt"
echo "   - railway.json"
echo ""
echo "4. 🚂 Railway Account banao: https://railway.app"
echo "5. ➕ New Project → Deploy from GitHub"
echo "6. 🔗 GitHub repository select karo"
echo "7. ⚡ Auto deploy ho jayega!"
echo ""
echo "🎯 Railway URL milega jaise:"
echo "   https://your-project-name.up.railway.app"
echo ""
echo "📱 WebView mein use karo:"
echo "   webview.loadUrl(\"https://your-railway-url\")"
echo ""
echo "💡 Alternative Platforms:"
echo "   - Render.com (easy)"
echo "   - Fly.io (fast)"
echo "   - PythonAnywhere (Python focused)"
