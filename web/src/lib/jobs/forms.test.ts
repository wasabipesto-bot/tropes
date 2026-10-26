import { describe, expect, it } from 'vitest';
// Astro's own FormData-to-object step for `accept: 'form'` actions. Not a public export, so this
// path may move on an Astro upgrade; the test failing to import is the signal to find it again.
import { formDataToObject } from '../../../node_modules/astro/dist/actions/runtime/server.js';
import { commitInput } from './forms';

function parse(fd: FormData) {
  return commitInput.parse(formDataToObject(fd, commitInput));
}

describe('commit form', () => {
  it('keeps every checked proposal and every prominence choice', () => {
    const fd = new FormData();
    fd.append('jobId', '14');
    for (const id of ['101', '102', '103']) fd.append('accept', id);
    fd.append('prominence.101', 'core');
    fd.append('prominence.102', 'brief');
    expect(parse(fd)).toEqual({ jobId: 14, accept: [101, 102, 103], prominence: { '101': 'core', '102': 'brief' } });
  });

  it('accepts a single checkbox and an empty selection', () => {
    const one = new FormData();
    one.append('jobId', '14');
    one.append('accept', '7');
    expect(parse(one).accept).toEqual([7]);
    const none = new FormData();
    none.append('jobId', '14');
    expect(parse(none).accept ?? []).toEqual([]);
  });
});

it('carries inline edits and treats a blank field as empty, not as an error', () => {
  const fd = new FormData();
  fd.set('jobId', '14');
  fd.append('accept', '101');
  fd.set('who.101', '');
  fd.set('text.101', 'Edited text.');
  const parsed = commitInput.parse(formDataToObject(fd, commitInput));
  expect(parsed.who).toEqual({ '101': '' }); // a blank field inside a catchall object arrives empty, not null
  expect(parsed.text).toEqual({ '101': 'Edited text.' });
});
