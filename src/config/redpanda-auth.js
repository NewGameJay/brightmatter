const { execSync } = require('child_process');

function getRedpandaConfig() {
  try {
    const output = execSync('rpk profile print', { encoding: 'utf8' });
    return output;
  } catch (error) {
    console.error('Error getting rpk config:', error);
    throw error;
  }
}

function getRedpandaBrokers() {
  return ['d12s0600ht3usuv2rgug.any.us-east-1.mpx.prd.cloud.redpanda.com:9092'];
}

module.exports = {
  getRedpandaConfig,
  getRedpandaBrokers
};
