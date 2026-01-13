#!/bin/bash

echo "🚀 Building kexi's Downloader Pro for macOS..."
echo ""

# Use Python 3.13 universal binary from python.org
PYTHON=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"

# Create/activate venv with universal Python
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment with universal Python..."
    $PYTHON -m venv venv
fi

echo "📦 Using universal Python virtual environment..."
source venv/bin/activate

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build dist

# Install dependencies
echo "📦 Installing/updating dependencies..."
pip install --upgrade pip
pip install --upgrade py2app
# Include PyInstaller so py2app's modulegraph can resolve PyInstaller hooks
pip install --upgrade pyinstaller
pip install --upgrade customtkinter yt-dlp darkdetect certifi


# Set environment variables for Tcl/Tk script lookup
export TCL_LIBRARY="$(pwd)/dist/kexi's Downloader Pro.app/Contents/Resources/lib/tcl8.6"
export TK_LIBRARY="$(pwd)/dist/kexi's Downloader Pro.app/Contents/Resources/lib/tk8.6"

# Build the app
echo ""
echo "🔨 Building application bundle..."
python setup.py py2app

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Build failed!"
    echo ""
    echo "💡 Troubleshooting tips:"
    echo "   1. Make sure you're using Python 3.8-3.12 (not 3.14)"
    echo "   2. Try: python3 --version"
    echo "   3. Try creating a new venv with an older Python version"
    echo ""
    exit 1
fi

# Copy icon to Resources
echo ""
echo "🎨 Copying app icon..."
cp app.icon.png "dist/kexi's Downloader Pro.app/Contents/Resources/"

# Download yt-dlp binary
echo ""
echo "⬇️  Downloading yt-dlp binary..."
mkdir -p "dist/kexi's Downloader Pro.app/Contents/Resources/bin"
curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos -o "dist/kexi's Downloader Pro.app/Contents/Resources/bin/yt-dlp"
chmod +x "dist/kexi's Downloader Pro.app/Contents/Resources/bin/yt-dlp"


# Copy Tcl/Tk script folders into the app bundle (fallback, in case py2app misses them)
echo ""
echo "🗂  Ensuring Tcl/Tk script resources are bundled..."
APP_RES="dist/kexi's Downloader Pro.app/Contents/Resources/lib"
mkdir -p "$APP_RES"
# Prefer the repo-provided tcl/tk trees (included in repo: tcl8.6.16/ tk8.6.16/).
TCL_SRC_REPO="$(pwd)/tcl8.6.16/library"
TK_SRC_REPO="$(pwd)/tk8.6.16/library"
if [ -d "$TCL_SRC_REPO" ]; then
    mkdir -p "$APP_RES/tcl8.6"
    cp -R "$TCL_SRC_REPO" "$APP_RES/tcl8.6/" 2>/dev/null || true
fi
if [ -d "$TK_SRC_REPO" ]; then
    mkdir -p "$APP_RES/tk8.6"
    cp -R "$TK_SRC_REPO" "$APP_RES/tk8.6/" 2>/dev/null || true
fi
# Fallback to system-installed frameworks if repo trees are not present
if [ ! -f "$APP_RES/tcl8.6/library/init.tcl" ]; then
    TCL_SRC_SYS="/Library/Frameworks/Tcl.framework/Versions/8.6/Resources/Scripts/tcl8.6"
    if [ -d "$TCL_SRC_SYS" ]; then
        mkdir -p "$APP_RES/tcl8.6"
        cp -R "$TCL_SRC_SYS" "$APP_RES/tcl8.6/" 2>/dev/null || true
    fi
fi
if [ ! -f "$APP_RES/tk8.6/library/init.tcl" ]; then
    TK_SRC_SYS="/Library/Frameworks/Tk.framework/Versions/8.6/Resources/Scripts/tk8.6"
    if [ -d "$TK_SRC_SYS" ]; then
        mkdir -p "$APP_RES/tk8.6"
        cp -R "$TK_SRC_SYS" "$APP_RES/tk8.6/" 2>/dev/null || true
    fi
fi
echo "✅ Tcl/Tk script folders copied (if available)."
echo ""
echo "🔓 Removing quarantine attribute..."
xattr -cr "dist/kexi's Downloader Pro.app"

echo ""
echo "✅ ============================================"
echo "✅ BUILD COMPLETE!"
echo "✅ ============================================"
echo ""
echo "📱 Your app is ready: dist/kexi's Downloader Pro.app"
echo ""
echo "📋 Next steps:"
echo "   1. Test the app: open \"dist/kexi's Downloader Pro.app\""
echo "   2. Install: drag the app to your Applications folder"
echo ""
echo "🎉 Enjoy kexi's Downloader Pro!"
