# PII Redactor Bot (Auto-Provisioning Chrome Extension)

Customers frequently upload text files or forms to company portals that accidentally contain highly sensitive Personally Identifiable Information (PII)—like Social Security Numbers or Credit Card digits. Storing this unencrypted creates a massive legal liability. 

This project provides a **Chrome Extension** that connects to a backend PII redaction service on AWS. 

## 🚀 Auto-Provisioning & Self-Healing Architecture
What makes this extension unique is its **Infrastructure-as-Code** capability. You do not need to manually configure anything in the AWS Console. 

The extension itself bundles the AWS SDK, Python backend code, and CloudFormation templates. By simply providing your AWS keys inside the extension, it will:
1. Automatically provision your SQS Queues, DynamoDB tables, API Gateway, and Lambda functions.
2. Dynamically inject the Python `api_handler.py` and `worker.py` scripts into your Lambda instances.
3. **Self-Heal**: If you ever accidentally delete or break the backend code in the AWS Console, simply click "Deploy / Restore Defaults" in the extension to automatically repair your infrastructure.

---

## Getting Started

### 1. Build the Extension
This extension uses Vite to bundle the AWS SDK. You must build it before loading it into Chrome.

Make sure you have [Node.js](https://nodejs.org/) installed, then run:
```bash
cd extension
npm install
npx vite build
```
*This will generate a `dist/` folder inside the `extension/` directory.*

### 2. Load the Extension into Chrome
1. Open Google Chrome.
2. Navigate to `chrome://extensions/`
3. Toggle **Developer mode** to ON (top right corner).
4. Click **Load unpacked** (top left corner).
5. Select the **`extension/dist`** folder you just built.

### 3. Deploy your AWS Infrastructure
1. Click the PII Redactor extension icon in your browser toolbar.
2. Under **Infrastructure Management (AWS)**, enter your AWS Access Key ID, Secret Access Key, and Region.
3. Click **Deploy / Restore Defaults**.
4. Wait approximately 1-2 minutes for the extension to provision your CloudFormation stack and inject the Lambda code. 
5. Once the status turns green ("API is configured and ready"), you can begin scrubbing text!
