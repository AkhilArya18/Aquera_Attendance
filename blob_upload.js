#!/usr/bin/env node
/**
 * blob_upload.js – Thin Node.js helper CLI used by blob_api.py.
 * Usage:  node blob_upload.js <pathname> <filepath> <token>
 * Outputs JSON on stdout: {"url":"...","pathname":"..."}  or {"error":"..."}
 */
const { put } = require('/tmp/blobtest/node_modules/@vercel/blob');
const [, , pathname, filepath, token] = process.argv;
const fs = require('fs');

if (!pathname || !filepath || !token) {
    console.log(JSON.stringify({ error: "missing args: pathname filepath token" }));
    process.exit(1);
}

const ext = filepath.split('.').pop().toLowerCase();
const ctMap = { csv: 'text/csv', xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', xls: 'application/vnd.ms-excel' };
const contentType = ctMap[ext] || 'application/octet-stream';

(async () => {
    try {
        const body = fs.readFileSync(filepath);
        const result = await put(pathname, body, {
            access: 'private',
            token,
            allowOverwrite: true,
            addRandomSuffix: false,
            contentType,
        });
        console.log(JSON.stringify({ url: result.url, pathname: result.pathname }));
    } catch (e) {
        console.log(JSON.stringify({ error: e.message }));
        process.exit(1);
    }
})();
