import { CloudFormationClient, CreateStackCommand, UpdateStackCommand, DescribeStacksCommand, DescribeStackResourceCommand } from "@aws-sdk/client-cloudformation";
import { LambdaClient, UpdateFunctionCodeCommand } from "@aws-sdk/client-lambda";
import JSZip from "jszip";
import templateJson from '../aws-deployment/template.json?raw';
import apiHandlerPy from '../aws-deployment/lambda/api_handler.py?raw';
import workerPy from '../aws-deployment/lambda/worker.py?raw';

document.addEventListener('DOMContentLoaded', () => {
  const awsKeyInput = document.getElementById('awsKey');
  const awsSecretInput = document.getElementById('awsSecret');
  const awsRegionInput = document.getElementById('awsRegion');
  const deployBtn = document.getElementById('deployBtn');
  const deployStatus = document.getElementById('deployStatus');

  const inputText = document.getElementById('inputText');
  const scrubBtn = document.getElementById('scrubBtn');
  const resultDiv = document.getElementById('result');

  let activeApiUrl = '';

  // Load saved credentials
  chrome.storage.local.get(['awsKey', 'awsSecret', 'awsRegion', 'activeApiUrl'], (result) => {
    if (result.awsKey) awsKeyInput.value = result.awsKey;
    if (result.awsSecret) awsSecretInput.value = result.awsSecret;
    if (result.awsRegion) awsRegionInput.value = result.awsRegion;
    if (result.activeApiUrl) {
      activeApiUrl = result.activeApiUrl;
      scrubBtn.disabled = false;
      deployStatus.innerText = "API is configured and ready.";
      deployStatus.style.color = "green";
    }
  });

  const updateDeployStatus = (msg, color = "#555") => {
    deployStatus.innerText = msg;
    deployStatus.style.color = color;
  };

  const delay = ms => new Promise(res => setTimeout(res, ms));

  deployBtn.addEventListener('click', async () => {
    const accessKeyId = awsKeyInput.value.trim();
    const secretAccessKey = awsSecretInput.value.trim();
    const region = awsRegionInput.value.trim() || 'us-east-1';

    if (!accessKeyId || !secretAccessKey) {
      updateDeployStatus("Please enter AWS Access Key and Secret.", "red");
      return;
    }

    chrome.storage.local.set({ awsKey: accessKeyId, awsSecret: secretAccessKey, awsRegion: region });
    
    deployBtn.disabled = true;
    updateDeployStatus("Initializing AWS connection...");

    const creds = { region, credentials: { accessKeyId, secretAccessKey } };
    const cfClient = new CloudFormationClient(creds);
    const lambdaClient = new LambdaClient(creds);
    const STACK_NAME = "PIIRedactorBackend";

    try {
      let stackExists = false;
      try {
        await cfClient.send(new DescribeStacksCommand({ StackName: STACK_NAME }));
        stackExists = true;
      } catch (err) {
        if (!err.message.includes("does not exist")) throw err;
      }

      updateDeployStatus(`Executing CloudFormation ${stackExists ? 'Update' : 'Create'}...`);

      const cfParams = {
        StackName: STACK_NAME,
        TemplateBody: templateJson,
        Capabilities: ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
      };

      if (stackExists) {
        try {
          await cfClient.send(new UpdateStackCommand(cfParams));
        } catch (err) {
          if (!err.message.includes("No updates are to be performed")) throw err;
          console.log("CFN Stack up to date.");
        }
      } else {
        await cfClient.send(new CreateStackCommand(cfParams));
      }

      updateDeployStatus("Waiting for CloudFormation stack to complete (this takes a minute)...");
      
      let isComplete = false;
      let outputs = [];
      while (!isComplete) {
        await delay(5000);
        const res = await cfClient.send(new DescribeStacksCommand({ StackName: STACK_NAME }));
        const status = res.Stacks[0].StackStatus;
        if (status.endsWith('_COMPLETE')) {
           isComplete = true;
           outputs = res.Stacks[0].Outputs || [];
        } else if (status.endsWith('_FAILED') || status.includes('ROLLBACK')) {
           throw new Error(`Stack deployment failed: ${status}`);
        }
      }

      // Extract physical IDs for Lambdas to update code
      updateDeployStatus("Restoring/Updating Lambda Code...");
      
      const getPhysicalId = async (logicalId) => {
         const res = await cfClient.send(new DescribeStackResourceCommand({ StackName: STACK_NAME, LogicalResourceId: logicalId }));
         return res.StackResourceDetail.PhysicalResourceId;
      };

      const apiHandlerName = await getPhysicalId('ApiHandlerLambda');
      const workerName = await getPhysicalId('WorkerLambda');

      const createZip = async (filename, content) => {
        const zip = new JSZip();
        zip.file(filename, content);
        return await zip.generateAsync({type: 'uint8array'});
      };

      await lambdaClient.send(new UpdateFunctionCodeCommand({
        FunctionName: apiHandlerName,
        ZipFile: await createZip('api_handler.py', apiHandlerPy)
      }));

      await lambdaClient.send(new UpdateFunctionCodeCommand({
        FunctionName: workerName,
        ZipFile: await createZip('worker.py', workerPy)
      }));

      updateDeployStatus("Deployment Successful! Setup Complete.", "green");

      const apiUrlOutput = outputs.find(o => o.OutputKey === 'ApiUrl');
      if (apiUrlOutput) {
         activeApiUrl = apiUrlOutput.OutputValue;
         chrome.storage.local.set({ activeApiUrl });
         scrubBtn.disabled = false;
      }

    } catch (err) {
      updateDeployStatus(`Error: ${err.message}`, "red");
      console.error(err);
    } finally {
      deployBtn.disabled = false;
    }
  });

  // Scrub Text functionality (Polling)
  scrubBtn.addEventListener('click', async () => {
    const rawText = inputText.value;

    if (!activeApiUrl) {
      resultDiv.innerText = "Please deploy the backend first.";
      resultDiv.style.color = "red";
      return;
    }
    if (!rawText) return;

    resultDiv.style.color = 'black';
    resultDiv.innerText = "Submitting for redaction...";
    scrubBtn.disabled = true;

    try {
      const submitResponse = await fetch(activeApiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: rawText })
      });

      if (!submitResponse.ok) throw new Error(`Server returned ${submitResponse.status}`);
      
      const submitData = await submitResponse.json();
      const jobId = submitData.jobId;
      
      if (!jobId) {
          if (submitData.clean_text) {
              resultDiv.style.color = '#28a745';
              resultDiv.innerText = submitData.clean_text;
              scrubBtn.disabled = false;
              return;
          }
          throw new Error("API did not return a jobId.");
      }

      resultDiv.innerText = "Processing (Polling for result)...";

      let isComplete = false;
      let maxAttempts = 30;
      
      while (!isComplete && maxAttempts > 0) {
        await delay(1000);
        const pollUrl = new URL(activeApiUrl);
        pollUrl.searchParams.append('jobId', jobId);

        const pollResponse = await fetch(pollUrl.toString(), { method: 'GET' });
        if (!pollResponse.ok) throw new Error(`Polling failed: ${pollResponse.status}`);

        const pollData = await pollResponse.json();

        if (pollData.status === 'COMPLETED') {
            isComplete = true;
            resultDiv.style.color = '#28a745';
            resultDiv.innerText = pollData.clean_text;
        } else if (pollData.status === 'PROCESSING') {
            maxAttempts--;
            resultDiv.innerText = `Processing... (Waiting, ${maxAttempts} attempts left)`;
        } else {
            throw new Error(`Unknown status received: ${pollData.status}`);
        }
      }

      if (!isComplete) throw new Error("Timed out waiting for redaction to complete.");

    } catch (error) {
      resultDiv.style.color = 'red';
      resultDiv.innerText = "Error: " + error.message;
    } finally {
      scrubBtn.disabled = false;
    }
  });
});
