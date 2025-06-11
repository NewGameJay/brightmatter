import { Handler } from '@netlify/functions';
import serverless from 'serverless-http';
import { app } from '../../src/services/api';

// Wrap express app in serverless handler
const handler: Handler = serverless(app);

export { handler };
