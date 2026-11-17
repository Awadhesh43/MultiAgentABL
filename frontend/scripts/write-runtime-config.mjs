import { writeFile } from 'node:fs/promises';

const apiBaseUrl = process.env.API_BASE_URL || '/api';
const config = `window.__ABL_CONFIG__ = ${JSON.stringify({ apiBaseUrl })};\n`;

await writeFile(new URL('../public/runtime-config.js', import.meta.url), config);
