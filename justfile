# Build the HACS release archive with integration files at the ZIP root.
package:
    mkdir -p dist
    rm -f dist/quran_lamp.zip
    cd custom_components/quran_lamp && zip -qr ../../dist/quran_lamp.zip . -x '*/__pycache__/*' '__pycache__/*' '*.pyc'
