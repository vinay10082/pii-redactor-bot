# PII Redactor Bot

Customers frequently upload text files or forms to company portals that accidentally contain highly sensitive Personally Identifiable Information (PII)—like Social Security Numbers or Credit Card digits. Storing this unencrypted creates a massive legal liability.

This project provides a frontend interface to connect to a backend PII redaction service (like AWS Lambda) to instantly scrub sensitive data from customer text.

## Features
- **Frontend built with Vite**: A fast and lightweight development setup.
- **Environment Configuration**: Easily point to different backend environments using a `.env` file without hardcoding sensitive URLs into your source code.

## Getting Started

### 1. Install Dependencies
Make sure you have [Node.js](https://nodejs.org/) installed, then run:
```bash
npm install
```

### 2. Configure Environment Variables
Create a `.env` file in the root of the project (if it doesn't already exist) and add your backend API URL (e.g., your AWS Lambda URL):

```env
VITE_API_URL=https://your-lambda-url...
```

### 3. Run the Development Server
Start the local Vite development server:
```bash
npm run dev
```

Open the provided URL (usually `http://localhost:5173`) in your browser to test the application.
