#!/bin/bash

# Script to set up FRIDA project symlinks in OpenROAD-flow-scripts
# Usage: ./setup_frida_orfs.sh <ORFS_DIRECTORY>

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <ORFS_DIRECTORY>"
    echo "Example: $0 /path/to/OpenROAD-flow-scripts"
    exit 1
fi

ORFS_DIR="$1"

# Validate ORFS directory exists
if [ ! -d "$ORFS_DIR" ]; then
    echo "Error: ORFS directory '$ORFS_DIR' does not exist"
    exit 1
fi

# Validate ORFS directory structure
if [ ! -d "$ORFS_DIR/flow" ]; then
    echo "Error: '$ORFS_DIR' does not appear to be a valid OpenROAD-flow-scripts directory (missing flow/ subdirectory)"
    exit 1
fi

# Get absolute paths
FRIDA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ORFS_DIR="$(cd "$ORFS_DIR" && pwd)"

echo "Setting up FRIDA symlinks in OpenROAD-flow-scripts..."
echo "FRIDA directory: $FRIDA_DIR"
echo "ORFS directory: $ORFS_DIR"

# Create necessary directories if they don't exist
mkdir -p "$ORFS_DIR/flow/designs/src"
mkdir -p "$ORFS_DIR/flow/designs/tsmc65"
mkdir -p "$ORFS_DIR/flow/platforms"

# Remove existing symlinks/directories if they exist
[ -L "$ORFS_DIR/flow/designs/src/frida" ] && rm "$ORFS_DIR/flow/designs/src/frida"
[ -d "$ORFS_DIR/flow/designs/src/frida" ] && rm -rf "$ORFS_DIR/flow/designs/src/frida"
[ -L "$ORFS_DIR/flow/designs/tsmc65/frida" ] && rm "$ORFS_DIR/flow/designs/tsmc65/frida"
[ -d "$ORFS_DIR/flow/designs/tsmc65/frida" ] && rm -rf "$ORFS_DIR/flow/designs/tsmc65/frida"
[ -L "$ORFS_DIR/flow/platforms/tsmc65" ] && rm "$ORFS_DIR/flow/platforms/tsmc65"
[ -d "$ORFS_DIR/flow/platforms/tsmc65" ] && rm -rf "$ORFS_DIR/flow/platforms/tsmc65"

# Create symlinks
echo "Creating symlink: $ORFS_DIR/flow/designs/src/frida -> $FRIDA_DIR/hdl"
ln -sf "$FRIDA_DIR/hdl" "$ORFS_DIR/flow/designs/src/frida"

echo "Creating symlink: $ORFS_DIR/flow/designs/tsmc65/frida -> $FRIDA_DIR/design"
ln -sf "$FRIDA_DIR/design" "$ORFS_DIR/flow/designs/tsmc65/frida"

echo "Creating symlink: $ORFS_DIR/flow/platforms/tsmc65 -> $HOME/asiclab/tech/tsmc65"
ln -sf "$HOME/asiclab/tech/tsmc65" "$ORFS_DIR/flow/platforms/tsmc65"

# Update Makefile on line 8
MAKEFILE="$ORFS_DIR/flow/Makefile"
DESIGN_CONFIG_LINE="DESIGN_CONFIG=./designs/tsmc65/frida/config.mk"

echo "Updating $MAKEFILE line to have a default config for FRIDA..."

# Use sed to replace line 8 with the design config
sed -i "8s|.*|$DESIGN_CONFIG_LINE|" "$MAKEFILE"

echo "Updated line 8 of Makefile:"
sed -n '8p' "$MAKEFILE"

echo ""
echo "Setup complete! Symlinks created:"
echo "  • $ORFS_DIR/flow/designs/src/frida -> $FRIDA_DIR/hdl"
echo "  • $ORFS_DIR/flow/designs/tsmc65/frida -> $FRIDA_DIR/design"  
echo "  • $ORFS_DIR/flow/platforms/tsmc65 -> $HOME/asiclab/tech/tsmc65"
echo "  • FRIDA config.mk to flow/Makefile line 8:"
echo ""