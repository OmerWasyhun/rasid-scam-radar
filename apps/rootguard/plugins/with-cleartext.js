// Plain-HTTP calls to a RASID server on the local network (hackathon setup). Use HTTPS in production.
const { withAndroidManifest } = require('expo/config-plugins');
module.exports = function withCleartext(config) {
  return withAndroidManifest(config, cfg => {
    const app = cfg.modResults.manifest.application?.[0];
    if (app) app.$['android:usesCleartextTraffic'] = 'true';
    return cfg;
  });
};
