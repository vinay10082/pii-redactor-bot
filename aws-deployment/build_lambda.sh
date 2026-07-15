#!/bin/bash
set -e

echo "Building Lambda Layer..."
mkdir -p assets/layer/python
# We use a lightweight spacy model
pip install spacy==3.5.3 langdetect -t assets/layer/python
# Download the small english model directly into the layer
python -m spacy download en_core_web_sm --target assets/layer/python

cd assets/layer
zip -r9q ../spacy-layer.zip .
cd ../..
rm -rf assets/layer

echo "Lambda Layer built at assets/spacy-layer.zip"

echo "Building Lambda Code..."
mkdir -p assets/code
cp src/aws/lambda/*.py assets/code/
cd assets/code
zip -r9q ../lambda-code.zip .
cd ../..
rm -rf assets/code

echo "Lambda Code built at assets/lambda-code.zip"
