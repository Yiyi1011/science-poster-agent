import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const source = readFileSync(new URL('../frontend/public/solar-animation/player.js', import.meta.url), 'utf8');
function harness(search = '') {
  const elements = new Map();
  const drawing = new Proxy({}, { get: (target, key) => target[key] ?? (() => {}), set: (target, key, value) => {target[key] = value; return true;} });
  const element = () => ({ textContent: '', value: '', children: [], listeners: {}, attributes: {},
    getContext: () => drawing, appendChild(child) { this.children.push(child); },
    setAttribute(name, value) { this.attributes[name] = value; }, removeAttribute(name) { delete this.attributes[name]; },
    addEventListener(name, callback) { this.listeners[name] = callback; },
  });
  const document = { hidden: false, querySelector(selector) { if (!elements.has(selector)) elements.set(selector, element()); return elements.get(selector); },
    querySelectorAll: () => elements.get('#chapters').children, createElement: element, addEventListener() {},
  };
  const context = vm.createContext({document, location:{search}, URLSearchParams, requestAnimationFrame() {}});
  vm.runInContext(source, context);
  return {context, elements, run: code => vm.runInContext(code, context)};
}
test('seven evidence-bound scenes total 84 seconds; captions <= 18 chars', () => {
  const h=harness();
  assert.equal(h.run('scenes.length'),7); assert.equal(h.run('total'),84);
  assert.equal(h.run('scenes.every(s=>s.sources.length>0 && s.sub.every(t=>t.length<=18))'),true);
  assert.equal(h.elements.get('#chapters').children.length,7);
});
test('every boundary and draw frame works; ending remains in last scene', () => {
  const h=harness();
  for (let t=0;t<=84;t+=.5) h.run(`draw(${t})`);
  assert.equal(h.run('sceneAt(0)'),0); assert.equal(h.run('sceneAt(9)'),1);
  assert.equal(h.run('sceneAt(84)'),6);
});
test('pause, next, seek, last-scene controls and reduced invalid query are local only', () => {
  const h=harness('?t=24'); assert.equal(h.run('playing'),false);
  h.elements.get('#play').listeners.click(); assert.equal(h.run('playing'),true);
  h.elements.get('#play').listeners.click(); assert.equal(h.run('playing'),false);
  h.elements.get('#next').listeners.click(); assert.equal(h.run('position'),35);
  h.elements.get('#seek').value='84'; h.elements.get('#seek').listeners.input();
  assert.equal(h.elements.get('#next').disabled,true);
  h.elements.get('#play').listeners.click(); assert.equal(h.run('position'),0);
  assert.equal(harness('?t=bad').run('position'),0);
  assert.doesNotMatch(source,/\bfetch\s*\(|XMLHttpRequest|speechSynthesis|WebSocket/);
});
