// A module load without session.start (a hot reload): /nod does not name a registration that did not happen,
// it asks the engine registry. A file of its own: the attempt's outcome is a module variable, the test must not
// see the session.start of other tests.
import { test, expect } from 'claude-code/testing'
import { STATE, STATE_FULL } from './fixtures'
import { seat } from './harness'

test('/nod without session.start: "no registration in this load — in the engine registry: no", nothing registered', async ($, on) => {
  const calls = seat(on, { files: { [STATE]: JSON.stringify(STATE_FULL) }, mtime: 1 })
  const ran = await $.command.run({
    command: 'nod', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 },
  } as never) as { text?: string }
  expect(ran.text).toContain('/nod: no registration in this load — in the engine registry: no — the command is not in the list')
  expect(ran.text).not.toContain('/nod registered')
  expect(calls.registers).toEqual([])
  expect(calls.lists).toBe(1)
})
