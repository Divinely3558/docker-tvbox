'use strict';

/*
 * DockTVBox JS 源脚本桥。
 *
 * 由 Python 侧以 `node js_bridge.js job.json` 调用：
 * - 用 vm 执行脚本，补齐 req / join / print / Crypto / _ 等 TVBox 全局；
 * - req 通过 worker 线程 + Atomics.wait 实现同步 HTTP；
 * - drpy 模块模式会递归拉取 ES Module 依赖后打包执行；
 * - 执行 init(cfg) 后调用目标函数，结果以 JSON 输出到 stdout。
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const http = require('http');
const https = require('https');
const zlib = require('zlib');
const nodeCrypto = require('crypto');
const { Worker, MessageChannel, receiveMessageOnPort, isMainThread, workerData } = require('worker_threads');

const RESULT_MARK = '__DOCKTV_RESULT__';
const ERROR_MARK = '__DOCKTV_ERROR__';
const DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

function main() {
  let job;
  try {
    job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  } catch (err) {
    reportError('读取任务失败：' + err.message);
    return;
  }

  let result;
  let error = null;
  runScript(job)
    .then((value) => { result = value; })
    .catch((err) => { error = err; })
    .then(() => {
      if (error) {
        reportError((error && error.stack) || String(error));
        return;
      }
      let value = result;
      if (value === undefined || value === null) value = {};
      if (typeof value === 'string') {
        const text = value.trim();
        if (text.startsWith('{') || text.startsWith('[')) {
          try { value = JSON.parse(text); } catch (e) { /* 保留原始字符串 */ }
        }
      }
      process.stdout.write('\n' + RESULT_MARK + JSON.stringify(value) + '\n');
    });
}

function reportError(message) {
  process.stderr.write(String(message) + '\n');
  process.stdout.write('\n' + ERROR_MARK + JSON.stringify({ message: String(message) }) + '\n');
  process.exitCode = 2;
}

function resolveDrpyModule(exportsObject) {
  if (!exportsObject) return null;
  const candidates = [
    exportsObject.DRPY,
    exportsObject.default && exportsObject.default.DRPY,
    exportsObject.default,
    exportsObject,
  ];
  for (const candidate of candidates) {
    if (candidate && typeof candidate.init === 'function') return candidate;
  }
  return null;
}

async function runScript(job) {
  const sandbox = createSandbox(job);
  const context = vm.createContext(sandbox, { name: 'docktvbox-js-spider' });
  sandbox.__context = context;

  let moduleExports = null;
  if (job.module) {
    const source = bundleModule(job.module.url, fs.readFileSync(job.script, 'utf8'), []);
    moduleExports = vm.runInContext('(' + source + ')', context, { filename: job.script, displayErrors: true });
  } else {
    vm.runInContext(fs.readFileSync(job.script, 'utf8'), context, { filename: job.script, displayErrors: true });
  }

  const cfg = job.cfg || {};
  const lookup = (name) => {
    try {
      const value = vm.runInContext('typeof ' + name + ' === "function" ? ' + name + ' : undefined', context);
      return typeof value === 'function' ? value : undefined;
    } catch (err) {
      return undefined;
    }
  };

  let target;
  if (job.drpy) {
    const drpy = resolveDrpyModule(moduleExports);
    if (!drpy) throw new Error('drpy 运行时没有导出 init/home 等函数');
    if (typeof drpy.init === 'function') await drpy.init(cfg.ext);
    target = drpy[job.fn];
  } else {
    // 部分 cat 脚本（如「山有木兮」）只通过 __jsEvalReturn() 暴露函数。
    let exported = null;
    const exportsMap = () => {
      if (exported) return exported;
      try {
        const fn = vm.runInContext(
          'typeof __jsEvalReturn === "function" ? __jsEvalReturn : undefined', context
        );
        const value = typeof fn === 'function' ? fn() : null;
        if (value && typeof value === 'object') exported = value;
      } catch (err) {
        exported = null;
      }
      return exported;
    };
    const initFn = lookup('init') || (exportsMap() || {}).init;
    if (typeof initFn === 'function') await initFn(cfg);
    target = lookup(job.fn) || (exportsMap() || {})[job.fn];
  }
  if (typeof target !== 'function') throw new Error('脚本没有实现函数 ' + job.fn);
  try {
    return await target.apply(undefined, job.args || []);
  } finally {
    if (typeof sandbox.__docktv_persist_local === 'function') sandbox.__docktv_persist_local();
  }
}

function createSandbox(job) {
  const noop = (...args) => { process.stderr.write(args.map(String).join(' ') + '\n'); };
  const Crypto = createCrypto();
  const underscore = createUnderscore();
  const dayjs = createDayjs();
  const uri = createUri();
  const catGlobals = {
    Crypto,
    CryptoJS: Crypto,
    _: underscore,
    cheerio: null,
    dayjs,
    jinja2: null,
    jp: null,
    jq: null,
    load: null,
    merge: null,
    parseHTML: null,
    text: null,
    xml: null,
    Uri: uri,
  };
  const importGlobals = {
    'assets://js/lib/cat.js': catGlobals,
    'assets://js/lib/crypto-js.js': { default: Crypto, CryptoJS: Crypto },
    'assets://js/lib/crypto-js.min.js': { default: Crypto, CryptoJS: Crypto },
    'assets://js/lib/underscore-esm-min.js': { default: underscore, _: underscore },
    'assets://js/lib/dayjs.min.js': { default: dayjs },
  };
  const importResolver = (spec) => {
    if (importGlobals[spec]) return importGlobals[spec];
    const base = String(spec).split('?')[0].split('/').pop();
    for (const key of Object.keys(importGlobals)) {
      if (base && key.endsWith('/' + base)) return importGlobals[key];
    }
    return null;
  };

  let cheerioLib = null;
  const loadCheerio = () => {
    if (cheerioLib) return cheerioLib;
    const code = fs.readFileSync(path.join(VENDOR_DIR, 'cheerio.min.js'), 'utf8');
    const bundled = bundleModule('vendor://cheerio.min.js', code, []);
    cheerioLib = vm.runInContext('(' + bundled + ')', sandbox.__context, { filename: 'cheerio.min.js' });
    return cheerioLib;
  };
  const splitRule = (parse) => {
    const parts = String(parse || '').trim().split('&&');
    return { selector: (parts[0] || '').trim(), attr: (parts[1] || '').trim() };
  };
  const elementValue = ($, node, attr) => {
    if (!node || !node.length) return '';
    const key = attr.toLowerCase();
    if (!attr || key === 'text') return node.text();
    if (key === 'html') return node.html() || '';
    if (key === 'outerhtml' || key === '*') return $.html(node) || '';
    return node.attr(attr) || '';
  };
  const pdfh = (html, parse) => {
    const { selector, attr } = splitRule(parse);
    if (!selector) return '';
    const $ = loadCheerio().load(typeof html === 'string' ? html : String(html));
    return elementValue($, $(selector).first(), attr);
  };
  const pdfa = (html, parse) => {
    const { selector, attr } = splitRule(parse);
    if (!selector) return [];
    const $ = loadCheerio().load(typeof html === 'string' ? html : String(html));
    const out = [];
    $(selector).each((index, element) => {
      const value = attr ? elementValue($, $(element), attr) : ($.html(element) || '');
      if (value) out.push(value);
    });
    return out;
  };
  const pd = (html, parse, base) => {
    const value = pdfh(html, parse);
    if (!value || /^(https?:)?\/\//i.test(value)) return value;
    if (!base) return value;
    try {
      return new URL(value, base).toString();
    } catch (err) {
      return value;
    }
  };
  const joinUrl = (base, suffix) => {
    base = String(base || '');
    suffix = String(suffix || '');
    if (!suffix) return base;
    if (/^(?:[a-z]+:)?\/\//i.test(suffix)) return suffix;
    try {
      return new URL(suffix, base).toString();
    } catch (err) {
      /* 非标准地址走字符串拼接 */
    }
    if (!base) return suffix;
    if (suffix.startsWith('?')) return base.split('?')[0].split('#')[0] + suffix;
    if (suffix.startsWith('#')) return base.split('#')[0] + suffix;
    if (suffix.startsWith('/')) {
      const match = base.match(/^([a-z]+:\/\/[^/]+)/i);
      return (match ? match[1] : '') + suffix;
    }
    return base.replace(/\/?[^/]*$/, '/') + suffix.replace(/^\.?\//, '');
  };
  const stateFile = job.state || '';
  const localStore = new Map();
  if (stateFile) {
    try {
      const raw = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
      if (raw && typeof raw === 'object') {
        for (const key of Object.keys(raw)) localStore.set(key, raw[key]);
      }
    } catch (err) {
      /* 首次运行或状态文件损坏时忽略 */
    }
  }
  const persistLocal = () => {
    if (!stateFile) return;
    try {
      const out = {};
      for (const [key, value] of localStore) out[key] = value;
      fs.mkdirSync(path.dirname(stateFile), { recursive: true });
      fs.writeFileSync(stateFile, JSON.stringify(out));
    } catch (err) {
      /* 状态持久化失败不影响本次结果 */
    }
  };
  const local = {
    get(key, name) {
      const bucket = localStore.get(String(key));
      return bucket ? bucket[String(name)] : undefined;
    },
    set(key, name, value) {
      const bucketKey = String(key);
      const bucket = localStore.get(bucketKey) || {};
      bucket[String(name)] = value;
      localStore.set(bucketKey, bucket);
    },
    delete(key, name) {
      const bucket = localStore.get(String(key));
      if (bucket) delete bucket[String(name)];
    },
  };

  const sandbox = {
    req: syncRequest,
    fetch: (url, options) => syncRequest(url, options || {}).content,
    join: join,
    print: noop,
    console: { log: noop, info: noop, warn: noop, error: noop, debug: noop, trace: noop },
    SpiderDebug: { log: noop },
    setTimeout, clearTimeout, setInterval, clearInterval, setImmediate, clearImmediate,
    Buffer,
    URL,
    URLSearchParams,
    TextEncoder,
    TextDecoder,
    atob: (value) => Buffer.from(String(value), 'base64').toString('binary'),
    btoa: (value) => Buffer.from(String(value), 'binary').toString('base64'),
    crypto: nodeCrypto.webcrypto,
    Crypto,
    CryptoJS: Crypto,
    _: underscore,
    dayjs,
    Uri: uri,
    md5: (value) => Crypto.MD5(value).toString(),
    pdfh,
    pdfa,
    pd,
    joinUrl,
    local,
    __docktv_persist_local: persistLocal,
    localStorage: createLocalStorage(),
    js2Proxy: () => '',
    getProxy: () => '',
    localProxy: () => '',
    sniffer: () => false,
    __docktv_import: (spec, name) => {
      const mod = importResolver(String(spec)) || {};
      if (name === '*') return mod;
      if (name === 'default') return mod.default !== undefined ? mod.default : mod;
      if (Object.prototype.hasOwnProperty.call(mod, name)) return mod[name];
      return sandbox[name];
    },
    __jsEvalReturn: function () {
      const names = ['init', 'home', 'homeVod', 'category', 'detail', 'search', 'play', 'proxy', 'preTask', 'destroy'];
      const out = {};
      for (const name of names) {
        if (typeof sandbox[name] === 'function') out[name] = sandbox[name];
      }
      return out;
    },
    __docktv_job: job,
  };
  sandbox.globalThis = sandbox;
  sandbox.global = sandbox;
  sandbox.self = sandbox;
  return sandbox;
}

/* ------------------------------------------------------------------ */
/* Crypto：CryptoJS 常用子集（AES / MD5 / SHA / HMAC）                  */
/* ------------------------------------------------------------------ */

function createCrypto() {
  class WordArray {
    constructor(buffer) {
      this.__buffer = Buffer.isBuffer(buffer) ? buffer : Buffer.from(buffer || []);
    }
    toString(encoder) {
      return (encoder || enc.Hex).stringify(this);
    }
    concat(other) {
      const buf = other instanceof WordArray ? other.__buffer : Buffer.from(other || []);
      this.__buffer = Buffer.concat([this.__buffer, buf]);
      return this;
    }
    clamp() { return this; }
  }

  const enc = {
    Utf8: {
      stringify: (wordArray) => wordArray.__buffer.toString('utf8'),
      parse: (value) => new WordArray(Buffer.from(String(value), 'utf8')),
    },
    Latin1: {
      stringify: (wordArray) => wordArray.__buffer.toString('latin1'),
      parse: (value) => new WordArray(Buffer.from(String(value), 'latin1')),
    },
    Hex: {
      stringify: (wordArray) => wordArray.__buffer.toString('hex'),
      parse: (value) => {
        let text = String(value).replace(/[^0-9a-fA-F]/g, '');
        if (text.length % 2) text += '0';
        return new WordArray(Buffer.from(text, 'hex'));
      },
    },
    Base64: {
      stringify: (wordArray) => wordArray.__buffer.toString('base64'),
      parse: (value) => new WordArray(Buffer.from(String(value).replace(/^data:[^,]+,/, ''), 'base64')),
    },
    Utf16: {
      stringify: (wordArray) => wordArray.__buffer.toString('utf16le'),
      parse: (value) => new WordArray(Buffer.from(String(value), 'utf16le')),
    },
    Utf16LE: {
      stringify: (wordArray) => wordArray.__buffer.toString('utf16le'),
      parse: (value) => new WordArray(Buffer.from(String(value), 'utf16le')),
    },
  };

  const toBuffer = (value) => {
    if (value instanceof WordArray) return value.__buffer;
    if (Buffer.isBuffer(value)) return value;
    if (value && value.__buffer) return value.__buffer;
    if (value instanceof Uint8Array) return Buffer.from(value);
    return Buffer.from(value === undefined || value === null ? '' : String(value), 'utf8');
  };

  const modeNames = { CBC: 'cbc', ECB: 'ecb', CFB: 'cfb', OFB: 'ofb', CTR: 'ctr' };
  const mode = {};
  for (const name of Object.keys(modeNames)) mode[name] = { name };
  const pad = {
    Pkcs7: { name: 'pkcs7' },
    NoPadding: { name: 'none' },
    ZeroPadding: { name: 'zero' },
    Iso10126: { name: 'iso10126' },
    AnsiX923: { name: 'ansix923' },
  };

  const resolveAesKey = (key) => {
    const buf = toBuffer(key);
    if (buf.length === 16 || buf.length === 24 || buf.length === 32) return buf;
    if (buf.length < 16) return Buffer.concat([buf, Buffer.alloc(16 - buf.length)]);
    if (buf.length < 24) return buf.subarray(0, 16);
    if (buf.length < 32) return buf.subarray(0, 24);
    return buf.subarray(0, 32);
  };

  const paddingName = (opts) => {
    const value = opts && (opts.padding || opts.pad);
    if (!value) return 'pkcs7';
    if (typeof value === 'string') return value.toLowerCase();
    if (value.name) return String(value.name).toLowerCase();
    return 'pkcs7';
  };

  const modeName = (opts) => {
    const value = opts && opts.mode;
    if (!value) return 'cbc';
    if (typeof value === 'string') return value.toLowerCase();
    if (value.name) return String(value.name).toLowerCase();
    return 'cbc';
  };

  const makeIv = (opts) => {
    if (opts && opts.iv !== undefined && opts.iv !== null) {
      return Buffer.concat([toBuffer(opts.iv), Buffer.alloc(16)]).subarray(0, 16);
    }
    return Buffer.alloc(16);
  };

  const padZero = (buf) => {
    const remainder = buf.length % 16;
    return remainder === 0 ? Buffer.concat([buf, Buffer.alloc(16)]) : Buffer.concat([buf, Buffer.alloc(16 - remainder)]);
  };

  const aesCore = (method) => (message, key, opts) => {
    opts = opts || {};
    const modeValue = modeName(opts);
    const padding = paddingName(opts);
    const keyBuf = resolveAesKey(key);
    const alg = 'aes-' + keyBuf.length * 8 + '-' + (modeNames[modeValue] || 'cbc');
    const iv = modeValue === 'ecb' ? null : makeIv(opts);

    if (method === 'encrypt') {
      let data = toBuffer(message);
      if (padding === 'zero' || (padding !== 'pkcs7' && padding !== 'none')) data = padZero(data);
      const cipher = nodeCrypto.createCipheriv(alg, keyBuf, iv);
      cipher.setAutoPadding(padding === 'pkcs7');
      const out = Buffer.concat([cipher.update(data), cipher.final()]);
      const result = new WordArray(out);
      result.ciphertext = result;
      return result;
    }

    let data = toBuffer(message);
    if (padding === 'zero' || (padding !== 'pkcs7' && padding !== 'none')) data = padZero(data);
    const decipher = nodeCrypto.createDecipheriv(alg, keyBuf, iv);
    decipher.setAutoPadding(padding === 'pkcs7');
    let out;
    try {
      out = Buffer.concat([decipher.update(data), decipher.final()]);
    } catch (err) {
      if (padding !== 'pkcs7') throw err;
      const fallback = nodeCrypto.createDecipheriv(alg, keyBuf, iv);
      fallback.setAutoPadding(false);
      out = Buffer.concat([fallback.update(data), fallback.final()]);
      const padLength = out.length ? out[out.length - 1] : 0;
      if (padLength > 0 && padLength <= 16 && padLength <= out.length) out = out.subarray(0, out.length - padLength);
    }
    if (padding === 'zero') {
      let end = out.length;
      while (end > 0 && out[end - 1] === 0) end -= 1;
      out = out.subarray(0, end);
    }
    return new WordArray(out);
  };

  const AES = { encrypt: aesCore('encrypt'), decrypt: aesCore('decrypt') };
  const hashFactory = (algorithm) => (message) => new WordArray(nodeCrypto.createHash(algorithm).update(toBuffer(message)).digest());
  const hmacFactory = (algorithm) => (message, key) => new WordArray(nodeCrypto.createHmac(algorithm, toBuffer(key)).update(toBuffer(message)).digest());

  return {
    enc,
    mode,
    pad,
    AES,
    lib: {
      WordArray: {
        create: (words, sigBytes) => {
          if (Buffer.isBuffer(words)) return new WordArray(sigBytes !== undefined ? words.subarray(0, sigBytes) : words);
          if (Array.isArray(words)) {
            const buf = Buffer.alloc(words.length * 4);
            for (let i = 0; i < words.length; i++) buf.writeUInt32BE(words[i] >>> 0, i * 4);
            return new WordArray(sigBytes !== undefined ? buf.subarray(0, sigBytes) : buf);
          }
          if (words && words.__buffer) return new WordArray(sigBytes !== undefined ? words.__buffer.subarray(0, sigBytes) : words.__buffer);
          return new WordArray(Buffer.alloc(sigBytes || 0));
        },
        random: (length) => new WordArray(nodeCrypto.randomBytes(length || 4)),
      },
    },
    MD5: hashFactory('md5'),
    SHA1: hashFactory('sha1'),
    SHA224: hashFactory('sha224'),
    SHA256: hashFactory('sha256'),
    SHA384: hashFactory('sha384'),
    SHA512: hashFactory('sha512'),
    HmacMD5: hmacFactory('md5'),
    HmacSHA1: hmacFactory('sha1'),
    HmacSHA256: hmacFactory('sha256'),
    HmacSHA512: hmacFactory('sha512'),
    algo: {},
  };
}

function createUnderscore() {
  const _ = {};
  const isArrayLike = (value) => value != null && typeof value !== 'function' && typeof value !== 'string' &&
    typeof value.length === 'number' && value.length >= 0 && value.length <= Number.MAX_SAFE_INTEGER;
  const keys = (obj) => (obj == null ? [] : Object.keys(obj));
  const identity = (value) => value;
  const cb = (iteratee, context) => {
    if (iteratee == null) return identity;
    if (typeof iteratee === 'function') return context ? iteratee.bind(context) : iteratee;
    if (typeof iteratee === 'object') return (value) => _.isMatch(value, iteratee);
    return (value) => value && value[iteratee];
  };
  const each = (obj, iteratee, context) => {
    const fn = cb(iteratee, context);
    if (isArrayLike(obj)) {
      for (let i = 0; i < obj.length; i++) fn(obj[i], i, obj);
    } else {
      for (const key of keys(obj)) fn(obj[key], key, obj);
    }
    return obj;
  };

  _.each = _.forEach = each;
  _.map = (obj, iteratee, context) => {
    const fn = cb(iteratee, context);
    const out = [];
    each(obj, (value, key, list) => out.push(fn(value, key, list)));
    return out;
  };
  _.collect = _.map;
  _.filter = _.select = (obj, predicate, context) => {
    const fn = cb(predicate, context);
    const out = [];
    each(obj, (value, key, list) => { if (fn(value, key, list)) out.push(value); });
    return out;
  };
  _.reject = (obj, predicate, context) => {
    const fn = cb(predicate, context);
    return _.filter(obj, (value, key, list) => !fn(value, key, list));
  };
  _.find = _.detect = (obj, predicate, context) => {
    const fn = cb(predicate, context);
    let found;
    each(obj, (value, key, list) => {
      if (found === undefined && fn(value, key, list)) found = value;
    });
    return found;
  };
  _.findIndex = (obj, predicate, context) => {
    const fn = cb(predicate, context);
    let index = -1;
    each(obj, (value, key, list) => {
      if (index < 0 && fn(value, key, list)) index = Number(key);
    });
    return index;
  };
  _.some = _.any = (obj, predicate, context) => {
    const fn = cb(predicate, context);
    let result = false;
    each(obj, (value, key, list) => { if (!result && fn(value, key, list)) result = true; });
    return result;
  };
  _.every = _.all = (obj, predicate, context) => {
    const fn = cb(predicate, context);
    let result = true;
    each(obj, (value, key, list) => { if (result && !fn(value, key, list)) result = false; });
    return result;
  };
  _.contains = _.includes = (obj, target, fromIndex) => {
    if (!isArrayLike(obj)) obj = _.values(obj);
    const start = Math.max(0, fromIndex || 0);
    for (let i = start; i < obj.length; i++) if (obj[i] === target) return true;
    return false;
  };
  _.invoke = (obj, method, ...args) => _.map(obj, (value) => {
    const fn = typeof method === 'function' ? method : value && value[method];
    return typeof fn === 'function' ? fn.apply(value, args) : undefined;
  });
  _.pluck = (obj, key) => _.map(obj, (value) => value && value[key]);
  _.where = (obj, attrs) => _.filter(obj, attrs);
  _.findWhere = (obj, attrs) => _.find(obj, attrs);
  _.max = (obj, iteratee, context) => {
    const fn = cb(iteratee, context);
    let best;
    let bestValue = -Infinity;
    each(obj, (value, key, list) => {
      const score = fn(value, key, list);
      if (score > bestValue) { bestValue = score; best = value; }
    });
    return best;
  };
  _.min = (obj, iteratee, context) => {
    const fn = cb(iteratee, context);
    let best;
    let bestValue = Infinity;
    each(obj, (value, key, list) => {
      const score = fn(value, key, list);
      if (score < bestValue) { bestValue = score; best = value; }
    });
    return best;
  };
  _.sortBy = (obj, iteratee, context) => {
    const fn = cb(iteratee, context);
    return _.pluck(_.map(obj, (value, key, list) => ({ value, index: key, criteria: fn(value, key, list) }))
      .sort((left, right) => {
        if (left.criteria !== right.criteria) {
          if (left.criteria > right.criteria) return 1;
          if (left.criteria < right.criteria) return -1;
        }
        return left.index - right.index;
      }), 'value');
  };
  _.groupBy = (obj, iteratee, context) => {
    const fn = cb(iteratee, context);
    const out = {};
    each(obj, (value, key, list) => {
      const group = fn(value, key, list);
      (out[group] || (out[group] = [])).push(value);
    });
    return out;
  };
  _.indexBy = (obj, iteratee, context) => {
    const fn = cb(iteratee, context);
    const out = {};
    each(obj, (value, key, list) => { out[fn(value, key, list)] = value; });
    return out;
  };
  _.countBy = (obj, iteratee, context) => {
    const fn = cb(iteratee, context);
    const out = {};
    each(obj, (value, key, list) => {
      const group = fn(value, key, list);
      out[group] = (out[group] || 0) + 1;
    });
    return out;
  };
  _.shuffle = (obj) => {
    const array = isArrayLike(obj) ? Array.from(obj) : _.values(obj);
    for (let i = array.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
  };
  _.sample = (obj, n) => {
    const array = _.shuffle(obj);
    return n == null ? array[0] : array.slice(0, Math.max(0, n));
  };
  _.toArray = (obj) => {
    if (obj == null) return [];
    if (Array.isArray(obj)) return Array.from(obj);
    if (typeof obj === 'string') return obj.split('');
    if (isArrayLike(obj)) return Array.from(obj);
    return _.values(obj);
  };
  _.size = (obj) => (obj == null ? 0 : isArrayLike(obj) ? obj.length : keys(obj).length);
  _.first = _.head = _.take = (obj, n, guard) => {
    if (obj == null || obj.length < 1) return n == null || guard ? undefined : [];
    if (n == null || guard) return obj[0];
    return Array.prototype.slice.call(obj, 0, Math.max(0, n));
  };
  _.initial = (obj, n, guard) => Array.prototype.slice.call(obj, 0, Math.max(0, obj.length - (n == null || guard ? 1 : n)));
  _.last = (obj, n, guard) => {
    if (obj == null || obj.length < 1) return n == null || guard ? undefined : [];
    if (n == null || guard) return obj[obj.length - 1];
    return Array.prototype.slice.call(obj, Math.max(0, obj.length - n));
  };
  _.rest = _.tail = _.drop = (obj, n, guard) => Array.prototype.slice.call(obj, n == null || guard ? 1 : n);
  _.compact = (obj) => _.filter(obj, Boolean);
  _.flatten = (array, shallow) => {
    const out = [];
    const walk = (list, depth) => {
      for (const value of list) {
        if (Array.isArray(value) && depth > 0) walk(value, depth - 1);
        else out.push(value);
      }
    };
    walk(array || [], shallow ? 1 : Infinity);
    return out;
  };
  _.without = (array, ...values) => _.filter(array, (value) => !values.includes(value));
  _.union = (...arrays) => _.uniq(_.flatten(arrays, true));
  _.intersection = (array, ...others) => _.uniq(_.filter(array, (value) => _.every(others, (other) => _.contains(other, value))));
  _.difference = (array, ...others) => _.filter(array, (value) => !_.some(others, (other) => _.contains(other, value)));
  _.uniq = _.unique = (array, isSorted, iteratee) => {
    const fn = cb(iteratee);
    const out = [];
    const seen = [];
    for (const value of array || []) {
      const key = fn(value);
      if (!seen.includes(key)) { seen.push(key); out.push(value); }
    }
    return out;
  };
  _.zip = (...arrays) => {
    const length = Math.max(0, ...arrays.map((array) => array.length));
    const out = [];
    for (let i = 0; i < length; i++) out.push(arrays.map((array) => array[i]));
    return out;
  };
  _.object = (list, values) => {
    const out = {};
    list.forEach((value, index) => {
      if (values) out[value] = values[index];
      else out[value[0]] = value[1];
    });
    return out;
  };
  _.range = (start, stop, step) => {
    if (stop == null) { stop = start || 0; start = 0; }
    const out = [];
    const increment = step || (stop < start ? -1 : 1);
    for (let value = start; increment > 0 ? value < stop : value > stop; value += increment) out.push(value);
    return out;
  };
  _.chunk = (array, count) => {
    const out = [];
    for (let i = 0; i < (array || []).length; i += count) out.push(array.slice(i, i + count));
    return out;
  };
  _.partition = (obj, predicate) => {
    const fn = cb(predicate);
    const pass = [];
    const fail = [];
    each(obj, (value, key, list) => (fn(value, key, list) ? pass : fail).push(value));
    return [pass, fail];
  };
  _.keys = keys;
  _.allKeys = (obj) => {
    const out = [];
    for (const key in obj) out.push(key);
    return out;
  };
  _.values = (obj) => keys(obj).map((key) => obj[key]);
  _.pairs = (obj) => keys(obj).map((key) => [key, obj[key]]);
  _.invert = (obj) => {
    const out = {};
    for (const key of keys(obj)) out[obj[key]] = key;
    return out;
  };
  _.extend = _.assign = (obj, ...sources) => {
    for (const source of sources) if (source) Object.assign(obj, source);
    return obj;
  };
  _.extendOwn = _.assign;
  _.defaults = (obj, ...sources) => {
    for (const source of sources) {
      if (!source) continue;
      for (const key of keys(source)) if (obj[key] === undefined) obj[key] = source[key];
    }
    return obj;
  };
  _.pick = (obj, ...keysOrPredicate) => {
    const out = {};
    if (typeof keysOrPredicate[0] === 'function') {
      const fn = keysOrPredicate[0];
      each(obj, (value, key, list) => { if (fn(value, key, list)) out[key] = value; });
    } else {
      const list = _.flatten(keysOrPredicate, true);
      for (const key of list) if (obj && key in obj) out[key] = obj[key];
    }
    return out;
  };
  _.omit = (obj, ...keysOrPredicate) => {
    if (typeof keysOrPredicate[0] === 'function') {
      const fn = keysOrPredicate[0];
      return _.pick(obj, (value, key, list) => !fn(value, key, list));
    }
    const excluded = _.flatten(keysOrPredicate, true);
    const out = {};
    for (const key of keys(obj)) if (!excluded.includes(key)) out[key] = obj[key];
    return out;
  };
  _.has = (obj, key) => obj != null && Object.prototype.hasOwnProperty.call(obj, key);
  _.get = (obj, pathValue, defaultValue) => {
    const parts = Array.isArray(pathValue) ? pathValue : String(pathValue).split('.');
    let current = obj;
    for (const part of parts) {
      if (current == null) return defaultValue;
      current = current[part];
    }
    return current === undefined ? defaultValue : current;
  };
  _.property = (key) => (obj) => (obj == null ? undefined : obj[key]);
  _.propertyOf = (obj) => (key) => (obj == null ? undefined : obj[key]);
  _.matcher = _.matches = (attrs) => (obj) => _.isMatch(obj, attrs);
  _.isMatch = (obj, attrs) => {
    for (const key of keys(attrs)) if (attrs[key] !== obj || !(key in Object(obj))) return false;
    return true;
  };
  _.isEqual = (left, right) => {
    if (left === right) return true;
    if (left == null || right == null) return false;
    if (typeof left !== 'object' || typeof right !== 'object') return false;
    if (Array.isArray(left) !== Array.isArray(right)) return false;
    const leftKeys = keys(left);
    const rightKeys = keys(right);
    if (leftKeys.length !== rightKeys.length) return false;
    for (const key of leftKeys) if (!_.isEqual(left[key], right[key])) return false;
    return true;
  };
  _.isEmpty = (obj) => {
    if (obj == null) return true;
    if (isArrayLike(obj) && (Array.isArray(obj) || typeof obj === 'string')) return obj.length === 0;
    return keys(obj).length === 0;
  };
  _.isArray = Array.isArray;
  _.isObject = (obj) => obj === Object(obj);
  _.isFunction = (obj) => typeof obj === 'function';
  _.isString = (obj) => typeof obj === 'string' || Object.prototype.toString.call(obj) === '[object String]';
  _.isNumber = (obj) => typeof obj === 'number' || Object.prototype.toString.call(obj) === '[object Number]';
  _.isBoolean = (obj) => obj === true || obj === false || Object.prototype.toString.call(obj) === '[object Boolean]';
  _.isDate = (obj) => Object.prototype.toString.call(obj) === '[object Date]';
  _.isRegExp = (obj) => Object.prototype.toString.call(obj) === '[object RegExp]';
  _.isNull = (obj) => obj === null;
  _.isUndefined = (obj) => obj === undefined;
  _.isNaN = (obj) => _.isNumber(obj) && isNaN(obj);
  _.isFinite = (obj) => isFinite(obj) && !isNaN(parseFloat(obj));
  _.isElement = (obj) => !!(obj && obj.nodeType === 1);
  _.isArguments = (obj) => Object.prototype.toString.call(obj) === '[object Arguments]';
  _.clone = (obj) => {
    if (Array.isArray(obj)) return obj.slice();
    if (obj && typeof obj === 'object') return Object.assign({}, obj);
    return obj;
  };
  _.cloneDeep = (obj) => JSON.parse(JSON.stringify(obj));
  _.tap = (obj, interceptor) => { interceptor(obj); return obj; };
  _.identity = identity;
  _.constant = (value) => () => value;
  _.noop = () => undefined;
  _.times = (n, iteratee, context) => {
    const fn = cb(iteratee, context);
    const out = [];
    for (let i = 0; i < Math.max(0, n); i++) out.push(fn(i));
    return out;
  };
  _.random = (min, max) => {
    if (max == null) { max = min; min = 0; }
    return min + Math.floor(Math.random() * (max - min + 1));
  };
  _.now = Date.now;
  let uniqueIdCounter = 0;
  _.uniqueId = (prefix) => String(prefix == null ? '' : prefix) + (++uniqueIdCounter);
  _.escape = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;',
  })[char]);
  _.unescape = (value) => String(value == null ? '' : value).replace(/&(amp|lt|gt|quot|#x27);/g, (match, entity) => ({
    amp: '&', lt: '<', gt: '>', quot: '"', '#x27': "'",
  })[entity]);
  _.result = (obj, keyValue, fallback) => {
    const value = _.get(obj, keyValue, fallback);
    return typeof value === 'function' ? value.call(obj) : value;
  };
  _.mixin = (source) => { Object.assign(_, source); return _; };
  _.iteratee = cb;
  _.trim = (value, chars) => {
    const text = value == null ? '' : String(value);
    if (chars == null) return text.trim();
    const escaped = String(chars).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return text.replace(new RegExp('^[' + escaped + ']+|[' + escaped + ']+$', 'g'), '');
  };
  return _;
}

/* ------------------------------------------------------------------ */
/* dayjs / Uri / localStorage 的轻量实现                               */
/* ------------------------------------------------------------------ */

function createDayjs() {
  const pad = (value, size) => String(value).padStart(size || 2, '0');
  const parse = (input) => {
    if (input === undefined || input === null) return new Date();
    if (input instanceof Date) return new Date(input.getTime());
    if (typeof input === 'number') return new Date(input);
    const text = String(input).trim();
    if (/^\d{10}$/.test(text)) return new Date(Number(text) * 1000);
    if (/^\d{13}$/.test(text)) return new Date(Number(text));
    return new Date(text.replace(/-/g, '/'));
  };
  const UNIT_MS = { millisecond: 1, second: 1000, minute: 60000, hour: 3600000, day: 86400000, week: 604800000 };
  const wrap = (date) => {
    const api = {
      __date: date,
      format: (pattern) => {
        const p = pattern || 'YYYY-MM-DDTHH:mm:ssZ';
        const map = {
          YYYY: date.getFullYear(),
          YY: String(date.getFullYear()).slice(-2),
          MM: pad(date.getMonth() + 1),
          M: date.getMonth() + 1,
          DD: pad(date.getDate()),
          D: date.getDate(),
          HH: pad(date.getHours()),
          H: date.getHours(),
          mm: pad(date.getMinutes()),
          m: date.getMinutes(),
          ss: pad(date.getSeconds()),
          s: date.getSeconds(),
          SSS: pad(date.getMilliseconds(), 3),
          d: String(date.getDay()),
          A: date.getHours() < 12 ? 'AM' : 'PM',
        };
        return p.replace(/YYYY|YY|MM|M|DD|D|HH|H|mm|m|ss|s|SSS|d|A/g, (token) => String(map[token]));
      },
      add: (value, unit) => wrap(new Date(date.getTime() + Number(value) * (UNIT_MS[unit] || UNIT_MS.day))),
      subtract: (value, unit) => wrap(new Date(date.getTime() - Number(value) * (UNIT_MS[unit] || UNIT_MS.day))),
      startOf: (unit) => {
        const next = new Date(date.getTime());
        if (unit === 'day' || unit === 'date') next.setHours(0, 0, 0, 0);
        else if (unit === 'hour') next.setMinutes(0, 0, 0);
        else if (unit === 'minute') next.setSeconds(0, 0);
        else if (unit === 'month') { next.setDate(1); next.setHours(0, 0, 0, 0); }
        else if (unit === 'year') { next.setMonth(0, 1); next.setHours(0, 0, 0, 0); }
        return wrap(next);
      },
      endOf: (unit) => wrap(api.startOf(unit).valueOf() + (UNIT_MS[unit] || UNIT_MS.day) - 1),
      unix: () => Math.floor(date.getTime() / 1000),
      valueOf: () => date.getTime(),
      toDate: () => new Date(date.getTime()),
      toJSON: () => date.toJSON(),
      toString: () => date.toString(),
      isBefore: (other) => date.getTime() < parse(other).getTime(),
      isAfter: (other) => date.getTime() > parse(other).getTime(),
      isSame: (other, unit) => {
        if (!unit) return date.getTime() === parse(other).getTime();
        return api.startOf(unit).valueOf() === wrap(parse(other)).startOf(unit).valueOf();
      },
      diff: (other, unit) => {
        const ms = date.getTime() - parse(other).getTime();
        if (unit === 'second') return Math.floor(ms / 1000);
        if (unit === 'minute') return Math.floor(ms / 60000);
        if (unit === 'hour') return Math.floor(ms / 3600000);
        if (unit === 'day') return Math.floor(ms / 86400000);
        return ms;
      },
      day: (value) => {
        if (value === undefined) return date.getDay();
        return wrap(new Date(date.getTime() + (value - date.getDay()) * 86400000));
      },
      date: (value) => {
        if (value === undefined) return date.getDate();
        const next = new Date(date.getTime());
        next.setDate(value);
        return wrap(next);
      },
      year: (value) => {
        if (value === undefined) return date.getFullYear();
        const next = new Date(date.getTime());
        next.setFullYear(value);
        return wrap(next);
      },
      month: (value) => {
        if (value === undefined) return date.getMonth();
        const next = new Date(date.getTime());
        next.setMonth(value);
        return wrap(next);
      },
    };
    return api;
  };
  const dayjs = (input) => wrap(parse(input));
  dayjs.unix = (seconds) => wrap(new Date(Number(seconds) * 1000));
  dayjs.now = () => wrap(new Date());
  return dayjs;
}

function createUri() {
  return {
    encode: (value) => encodeURIComponent(String(value)),
    decode: (value) => decodeURIComponent(String(value)),
    encodeURIComponent: (value) => encodeURIComponent(String(value)),
    decodeURIComponent: (value) => decodeURIComponent(String(value)),
  };
}

function createLocalStorage() {
  const store = {};
  return {
    getItem: (key) => (Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null),
    setItem: (key, value) => { store[key] = String(value); },
    removeItem: (key) => { delete store[key]; },
    clear: () => { for (const key of Object.keys(store)) delete store[key]; },
    key: (index) => Object.keys(store)[index] || null,
    get length() { return Object.keys(store).length; },
  };
}

/* ------------------------------------------------------------------ */
/* req                                                                 */
/* ------------------------------------------------------------------ */

const cookieJar = new Map();

function join(...parts) {
  let out = '';
  for (const part of parts) {
    let p = part === undefined || part === null ? '' : String(part);
    if (!p) continue;
    if (/^https?:\/\//i.test(p)) { out = p; continue; }
    if (!out) { out = p; continue; }
    out = out.replace(/\/+$/, '') + '/' + p.replace(/^\/+/, '');
  }
  return out;
}

function flattenParams(value, prefix, out) {
  out = out || [];
  if (value === undefined || value === null) return out;
  if (typeof value === 'object' && !Buffer.isBuffer(value) && !(value instanceof Date)) {
    for (const key of Object.keys(value)) {
      const nextKey = prefix ? prefix + '[' + key + ']' : key;
      flattenParams(value[key], nextKey, out);
    }
  } else {
    out.push([prefix || '', value instanceof Date ? value.toISOString() : String(value)]);
  }
  return out;
}

function serializeParams(data) {
  if (typeof data === 'string') return data;
  if (Buffer.isBuffer(data)) return data;
  return flattenParams(data)
    .map(([key, value]) => encodeURIComponent(key) + '=' + encodeURIComponent(value))
    .join('&');
}

function cookieHeaderFor(url) {
  try {
    const host = new URL(url).hostname;
    const parts = [];
    for (const [domain, jar] of cookieJar) {
      if (host === domain || host.endsWith('.' + domain)) {
        for (const [name, item] of jar) {
          if (!item.expires || item.expires > Date.now()) parts.push(name + '=' + item.value);
        }
      }
    }
    return parts.join('; ');
  } catch (err) {
    return '';
  }
}

function storeCookies(url, headers) {
  let host;
  try { host = new URL(url).hostname; } catch (err) { return; }
  let values = headers && (headers['set-cookie'] || headers['Set-Cookie']);
  if (!values) return;
  if (!Array.isArray(values)) values = [values];
  const jar = cookieJar.get(host) || new Map();
  for (const raw of values) {
    const text = String(raw);
    const first = text.split(';')[0];
    const index = first.indexOf('=');
    if (index <= 0) continue;
    const name = first.slice(0, index).trim();
    const value = first.slice(index + 1).trim();
    const expiresMatch = text.match(/expires=([^;]+)/i);
    const expires = expiresMatch ? Date.parse(expiresMatch[1]) : 0;
    jar.set(name, { value, expires });
  }
  cookieJar.set(host, jar);
}

function hasHeader(headers, name) {
  return Object.keys(headers || {}).some((key) => key.toLowerCase() === name.toLowerCase());
}

function setHeader(headers, name, value) {
  if (!hasHeader(headers, name)) headers[name] = value;
}

function normalizeOptions(rawUrl, options) {
  const opts = options || {};
  const method = String(opts.method || 'GET').toUpperCase();
  const headers = {};
  for (const key of Object.keys(opts.headers || {})) {
    if (opts.headers[key] !== undefined && opts.headers[key] !== null) headers[key] = String(opts.headers[key]);
  }
  let url = String(rawUrl);
  const data = opts.body !== undefined ? opts.body : (opts.data !== undefined ? opts.data : opts.postData);
  const postType = String(opts.postType || '').toLowerCase();
  let body = data;

  if ((method === 'GET' || method === 'HEAD') && data !== undefined && data !== null && data !== '') {
    const query = serializeParams(data);
    if (query) url += (url.includes('?') ? '&' : '?') + query;
    body = undefined;
  } else if (body !== undefined && body !== null) {
    if (typeof body === 'object' && !Buffer.isBuffer(body)) {
      if (postType === 'json') {
        body = JSON.stringify(body);
        setHeader(headers, 'Content-Type', 'application/json; charset=utf-8');
      } else if (postType === 'raw') {
        body = String(body);
      } else {
        body = serializeParams(body);
        setHeader(headers, 'Content-Type', 'application/x-www-form-urlencoded; charset=utf-8');
      }
    } else if (!Buffer.isBuffer(body)) {
      body = String(body);
      if (postType === 'json') setHeader(headers, 'Content-Type', 'application/json; charset=utf-8');
      else if (postType === 'form') setHeader(headers, 'Content-Type', 'application/x-www-form-urlencoded; charset=utf-8');
    }
  } else {
    body = undefined;
  }

  if (opts.cookie) setHeader(headers, 'Cookie', String(opts.cookie));
  if (!hasHeader(headers, 'Cookie') && opts.withCookie !== false) {
    const cookies = cookieHeaderFor(url);
    if (cookies) headers.Cookie = cookies;
  }
  if (!hasHeader(headers, 'User-Agent')) headers['User-Agent'] = DEFAULT_UA;
  if (!hasHeader(headers, 'Accept-Encoding')) headers['Accept-Encoding'] = 'gzip, deflate';
  if (!hasHeader(headers, 'Accept')) headers.Accept = '*/*';

  return {
    url,
    method,
    headers,
    body,
    timeout: Number(opts.timeout) > 0 ? Number(opts.timeout) : 20000,
    charset: opts.charset || opts.encoding || '',
    buffer: Number(opts.buffer || 0),
    redirect: opts.redirect === undefined ? true : !!opts.redirect,
    withCookie: opts.withCookie !== false,
  };
}

function syncRequest(rawUrl, options) {
  const opts = normalizeOptions(rawUrl, options);
  const sab = new SharedArrayBuffer(4);
  const flag = new Int32Array(sab);
  const { port1, port2 } = new MessageChannel();
  const worker = new Worker(__filename, {
    workerData: { __http: { ...opts, port: port2, sab } },
    transferList: [port2],
  });

  const deadline = Date.now() + opts.timeout + 5000;
  try {
    while (Date.now() < deadline) {
      const message = receiveMessageOnPort(port1);
      if (message) {
        const payload = message.message || {};
        if (payload.error) throw new Error(payload.error);
        if (opts.withCookie && payload.result && payload.result.headers) {
          storeCookies(payload.result.url || opts.url, payload.result.headers);
        }
        return payload.result;
      }
      Atomics.wait(flag, 0, 0, 10);
    }
    throw new Error('请求超时：' + opts.url);
  } finally {
    port1.close();
    worker.terminate();
  }
}

function decodeBuffer(buffer, charset, headers) {
  let name = String(charset || '').trim().toLowerCase();
  if (!name && headers) {
    const contentType = headers['content-type'] || headers['Content-Type'] || '';
    const match = String(contentType).match(/charset\s*=\s*["']?([\w-]+)/i);
    if (match) name = match[1].toLowerCase();
  }
  if (!name || name === 'utf8' || name === 'utf-8') {
    let text = buffer.toString('utf8');
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    return text;
  }
  const aliases = { gb2312: 'gbk', gb18030: 'gb18030', 'x-gbk': 'gbk', big5: 'big5', latin1: 'latin1', iso88591: 'latin1' };
  try {
    return new TextDecoder(aliases[name] || name).decode(buffer);
  } catch (err) {
    return buffer.toString('utf8');
  }
}

function inflate(buffer, encoding) {
  try {
    if (!encoding || encoding === 'identity') return buffer;
    if (encoding.includes('gzip')) return zlib.gunzipSync(buffer);
    if (encoding.includes('deflate')) return zlib.inflateSync(buffer);
    if (encoding.includes('br')) return zlib.brotliDecompressSync(buffer);
  } catch (err) {
    return buffer;
  }
  return buffer;
}

function runHttpWorker(job) {
  const flag = new Int32Array(job.sab);
  let finished = false;
  const finish = (payload) => {
    if (finished) return;
    finished = true;
    try { job.port.postMessage(payload); } catch (err) { /* ignore */ }
    Atomics.store(flag, 0, 1);
    Atomics.notify(flag, 0);
    try { job.port.close(); } catch (err) { /* ignore */ }
  };
  requestWithRedirects(job.url, job, 0, finish);
}

function requestWithRedirects(rawUrl, options, depth, finish) {
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch (err) {
    finish({ error: '地址不合法：' + rawUrl });
    return;
  }
  const mod = parsed.protocol === 'https:' ? https : http;
  const headers = {};
  for (const key of Object.keys(options.headers || {})) headers[key] = String(options.headers[key]);

  const body = options.body;
  const request = mod.request(parsed, { method: options.method, headers }, (response) => {
    const status = response.statusCode || 0;
    if (status >= 300 && status < 400 && response.headers.location && options.redirect !== false && depth < 5) {
      response.resume();
      const next = new URL(response.headers.location, parsed).toString();
      requestWithRedirects(next, options, depth + 1, finish);
      return;
    }
    const chunks = [];
    response.on('data', (chunk) => chunks.push(chunk));
    response.on('end', () => {
      let buffer = Buffer.concat(chunks);
      const encoding = String(response.headers['content-encoding'] || response.headers['Content-Encoding'] || '').toLowerCase();
      buffer = inflate(buffer, encoding);
      let content;
      if (options.buffer === 2) content = buffer.toString('base64');
      else if (options.buffer === 1) content = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
      else content = decodeBuffer(buffer, options.charset, response.headers);
      finish({
        result: {
          content,
          url: response.responseUrl || parsed.toString(),
          headers: response.headers,
          statusCode: status,
          code: status,
        },
      });
    });
    response.on('error', (err) => finish({ error: err.message }));
  });

  request.on('error', (err) => finish({ error: err.message }));
  request.setTimeout(options.timeout || 20000, () => {
    request.destroy(new Error('请求超时'));
  });
  if (body !== undefined && body !== null) request.write(body);
  request.end();
}

/* ------------------------------------------------------------------ */
/* ES Module 打包（drpy 运行时用）                                      */
/* ------------------------------------------------------------------ */

function runModuleWorker(job) {
  const flag = new Int32Array(job.sab);
  let finished = false;
  const finish = (payload) => {
    if (finished) return;
    finished = true;
    try { job.port.postMessage(payload); } catch (err) { /* ignore */ }
    Atomics.store(flag, 0, 1);
    Atomics.notify(flag, 0);
    try { job.port.close(); } catch (err) { /* ignore */ }
  };
  requestWithRedirects(job.url, job, 0, finish);
}

function fetchModuleText(url) {
  const opts = normalizeOptions(url, { timeout: 20000 });
  const sab = new SharedArrayBuffer(4);
  const flag = new Int32Array(sab);
  const { port1, port2 } = new MessageChannel();
  const worker = new Worker(__filename, {
    workerData: { __module: { ...opts, port: port2, sab } },
    transferList: [port2],
  });
  const deadline = Date.now() + opts.timeout + 5000;
  try {
    while (Date.now() < deadline) {
      const message = receiveMessageOnPort(port1);
      if (message) {
        const payload = message.message || {};
        if (payload.error) throw new Error(payload.error);
        const result = payload.result || {};
        if (result.statusCode && result.statusCode >= 400) {
          throw new Error('HTTP ' + result.statusCode);
        }
        return result.content || '';
      }
      Atomics.wait(flag, 0, 0, 20);
    }
    throw new Error('模块下载超时：' + url);
  } finally {
    port1.close();
    worker.terminate();
  }
}

const MODULE_CACHE = new Map();
const VENDOR_DIR = path.join(__dirname, 'vendor');

function vendorModule(spec) {
  const name = String(spec).split('?')[0].split('/').pop();
  if (!name || name.includes('..')) return null;
  try {
    return fs.readFileSync(path.join(VENDOR_DIR, name), 'utf8');
  } catch (err) {
    return null;
  }
}


function moduleKey(spec, base) {
  if (/^[a-z]+:\/\//i.test(spec)) return spec;
  if (spec.startsWith('//')) return 'https:' + spec;
  try {
    return new URL(spec, base).toString();
  } catch (err) {
    return spec;
  }
}

function importBindings(clause, resolvedSpec) {
  const moduleRef = '__docktv_modules[' + JSON.stringify(resolvedSpec) + ']';
  const lines = [];
  let rest = String(clause || '').trim();
  if (!rest) return '';
  const defaultMatch = rest.match(/^([^\s,{}*]+)\s*(?:,\s*([\s\S]*))?$/);
  if (defaultMatch && !rest.startsWith('{') && !rest.startsWith('*')) {
    lines.push('const ' + defaultMatch[1] + ' = ' + moduleRef + ' && ' + moduleRef + '.default !== undefined ? ' + moduleRef + '.default : ' + moduleRef + ';');
    rest = (defaultMatch[2] || '').trim();
  }
  const namespaceMatch = rest.match(/^\*\s+as\s+([^\s,{}]+)/);
  if (namespaceMatch) {
    lines.push('const ' + namespaceMatch[1] + ' = ' + moduleRef + ' || {};');
    return lines.join('\n');
  }
  const namedMatch = rest.match(/^\{([\s\S]*)\}$/);
  if (namedMatch) {
    const parts = namedMatch[1].split(',').map((part) => part.trim()).filter(Boolean);
    for (const part of parts) {
      const pieces = part.split(/\s+as\s+/);
      const original = pieces[0].trim();
      const local = (pieces[1] || pieces[0]).trim();
      lines.push('const ' + local + ' = ' + moduleRef + ' ? ' + moduleRef + '[' + JSON.stringify(original) + '] : undefined;');
    }
  }
  return lines.join('\n');
}

function transformModule(code, exportsTarget, base) {
  const exportedNames = [];
  let source = code;

  // 压缩后的脚本常把多条 import 用分号连在同一行，且 `import"..."` 之间没有空格。
  // 不吞掉语句末尾的分号，否则相邻 import 会失去可识别的边界而被漏掉。
  source = source.replace(/(^|[\n;])\s*import\s*([^'";]*?)\s*from\s*['"]([^'"]+)['"]/g, (match, lead, clause, spec) => {
    return lead + '\n' + importBindings(clause, moduleKey(spec, base)) + ';';
  });
  source = source.replace(/(^|[\n;])\s*import\s*['"]([^'"]+)['"]/g, '$1');
  source = source.replace(/(^|[;}\n])\s*export\s*default\s*/g, '$1' + exportsTarget + '.default = ');
  source = source.replace(/(^|[;}\n])\s*export\s*\{([^}]*)\}\s*;?/g, (match, lead, body) => {
    const assigns = body.split(',').map((part) => part.trim()).filter(Boolean).map((part) => {
      const pieces = part.split(/\s+as\s+/);
      const local = pieces[0].trim();
      const exported = (pieces[1] || pieces[0]).trim();
      return exportsTarget + '[' + JSON.stringify(exported) + '] = ' + local + ';';
    });
    return lead + '\n' + assigns.join('\n');
  });
  source = source.replace(/(^|[;}\n])\s*export\s+(async\s+function|function|class|const|let|var)\s+([A-Za-z_$][\w$]*)/g, (match, lead, kind, name) => {
    exportedNames.push(name);
    return lead + '\n' + kind + ' ' + name;
  });

  if (exportedNames.length) {
    source += '\n;' + exportedNames.map((name) => exportsTarget + '[' + JSON.stringify(name) + '] = ' + name + ';').join('\n');
  }
  return source;
}

function bundleModule(url, code, stack) {
  const key = moduleKey(url, url);
  if (MODULE_CACHE.has(key)) return MODULE_CACHE.get(key);
  if (stack.length > 12) throw new Error('脚本模块依赖层级过深：' + key);
  if (stack.includes(key)) throw new Error('脚本模块循环依赖：' + key);

  const local = code === undefined || code === null ? '' : code;
  if (!/(^|[\n;])\s*(import|export)\b|export\s*\{/.test(local)) {
    MODULE_CACHE.set(key, local);
    return local;
  }

  const importRe = /(?:^|[\n;])\s*import\s*([^'";]*?)\s*from\s*['"]([^'"]+)['"]|(?:^|[\n;])\s*import\s*['"]([^'"]+)['"]/g;
  const imports = [];
  let match;
  while ((match = importRe.exec(local)) !== null) imports.push(match[2] || match[3]);

  let dependencies = '';
  for (const spec of imports) {
    if (!spec) continue;
    const resolved = moduleKey(spec, key);
    if (MODULE_CACHE.has(resolved)) {
      dependencies += MODULE_CACHE.get(resolved) + ';\n';
      continue;
    }
    let depCode;
    try {
      depCode = fetchModuleText(resolved);
    } catch (err) {
      depCode = vendorModule(resolved);
      if (depCode === null) {
        throw new Error('加载脚本模块失败：' + resolved + '（' + err.message + '）');
      }
    }
    dependencies += bundleModule(resolved, depCode, stack.concat(key)) + ';\n';
  }

  const exportsName = '__exports_' + nodeCrypto.createHash('sha1').update(key).digest('hex').slice(0, 10);
  const wrapped = '(function(){\n' +
    'const __docktv_modules = globalThis.__docktv_modules || (globalThis.__docktv_modules = {});\n' +
    'const ' + exportsName + ' = {};\n' +
    dependencies +
    transformModule(local, exportsName, key) + '\n' +
    '__docktv_modules[' + JSON.stringify(key) + '] = ' + exportsName + ';\n' +
    'return ' + exportsName + ';\n' +
    '})()';
  MODULE_CACHE.set(key, wrapped);
  return wrapped;
}

if (!isMainThread && workerData && workerData.__http) {
  runHttpWorker(workerData.__http);
} else if (!isMainThread && workerData && workerData.__module) {
  runModuleWorker(workerData.__module);
} else if (isMainThread) {
  main();
}
