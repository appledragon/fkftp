#!/usr/bin/env bash
set -e

echo "============================================"
echo "  FKFTP Build - Generating Executable"
echo "============================================"
echo

pip install pyinstaller pyftpdlib flask

pyinstaller --onefile \
  --add-data "templates:templates" \
  --icon "static/icon.ico" \
  --name fkftp \
  --hidden-import pyasyncore \
  --hidden-import pyasynchat \
  --hidden-import pyftpdlib.handlers \
  --hidden-import pyftpdlib.filesystems \
  --hidden-import pyftpdlib.authorizers \
  --console \
  app.py

echo
if [ -f dist/fkftp ]; then
  echo "Build successful!"
  echo "Output: dist/fkftp"
  echo
  echo "Copy fkftp and config.json to your desired location."
  cp -f config.json dist/config.json 2>/dev/null || true
  echo "config.json has been copied to dist/ folder."
else
  echo "Build failed. Check the output above for errors."
fi
