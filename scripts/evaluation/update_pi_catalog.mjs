// Refresh the packaged selection metadata from the pinned, installed Pi package.
// Usage: node scripts/evaluation/update_pi_catalog.mjs /path/to/@earendil-works/pi-ai
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';

const root = path.resolve(process.argv[2] || 'node_modules/@earendil-works/pi-ai');
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const pins = fs.readFileSync(path.join(repo, 'src/search_swe/data/harnesses.toml'), 'utf8');
const version = pins.match(/^\[agents\.pi\]\s*\nversion\s*=\s*"([^"]+)"/m)?.[1];
if (!version) throw new Error('Missing agents.pi.version in harnesses.toml');
if (pkg.name !== '@earendil-works/pi-ai' || pkg.version !== version) throw new Error(`Expected pi-ai ${version}`);
const {builtinProviders} = await import(pathToFileURL(path.join(root, 'dist/providers/all.js')));
const {findEnvKeys} = await import(pathToFileURL(path.join(root, 'dist/env-api-keys.js')));
const env = new Proxy({}, {get: () => 'catalog-generation-placeholder'});
const providers = {};
for (const provider of builtinProviders()) {
  const models = provider.getModels();
  if (!models.length || !provider.auth.apiKey) continue;
  providers[provider.id] = {
    name: provider.name, base_url: provider.baseUrl || '', auth: Object.keys(provider.auth),
    keys: provider.id === 'amazon-bedrock' ? ['AWS_BEARER_TOKEN_BEDROCK'] :
      (findEnvKeys(provider.id, env) || []).filter(name => !['ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_OAUTH_TOKEN'].includes(name)),
    models: Object.fromEntries(models.map(model => [model.id, {
      name: model.name, api: model.api, base_url: model.baseUrl,
      reasoning: model.reasoning, context_length: model.contextWindow,
    }])),
  };
}
const destination = path.join(repo, 'src/search_swe/data/pi-models.json');
fs.mkdirSync(path.dirname(destination), {recursive: true});
fs.writeFileSync(destination, JSON.stringify({version, source: `https://github.com/earendil-works/pi/tree/v${version}`, providers}, null, 2) + '\n');
console.log(`Wrote ${Object.keys(providers).length} chat providers to ${destination}`);
