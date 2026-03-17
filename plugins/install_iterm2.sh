#!/bin/bash
# Install agentrace iTerm2 status bar component

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="$HOME/Library/Application Support/iTerm2/Scripts/AutoLaunch"
DEST="$DEST_DIR/agentrace_statusbar.py"

echo ""
echo "  agentrace — iTerm2 status bar install"
echo ""

# Check iTerm2 is installed
if [ ! -d "/Applications/iTerm.app" ]; then
  echo "  ✗ iTerm2 not found at /Applications/iTerm.app"
  echo "    Download from https://iterm2.com"
  exit 1
fi

# Create AutoLaunch directory if needed
mkdir -p "$DEST_DIR"

# Copy the script
cp "$SCRIPT_DIR/iterm2_statusbar.py" "$DEST"
echo "  ✓ Copied to $DEST"

echo ""
echo "  Next steps:"
echo ""
echo "  1. Enable the Python API (if not already):"
echo "     iTerm2 → Settings → General → Magic → Enable Python API ✅"
echo ""
echo "  2. Restart iTerm2 (or: iTerm2 → Scripts → agentrace_statusbar)"
echo ""
echo "  3. Add to your status bar:"
echo "     Settings → Profiles → [profile] → Session → Configure Status Bar"
echo "     → drag 'Agentrace' into the bar"
echo ""
