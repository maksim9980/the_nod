import { test, expect } from 'claude-code/testing'
import { seat, startSession } from './harness'

test('/nod answers with text while there is no state', async ($, on) => {
  const calls = seat(on, { files: {} })
  await startSession(calls, $, 'D:\\x\\proj')
  const ran = await $.command.run({ command: 'nod', args: '', origin: { kind: 'composer' },
    presentation: { isFullscreen: true, columns: 120 } })
  expect(ran.text?.split('\n')[0]).toBe('Nod: no state — no .nod/state.json in D:\\x\\proj or above')
})
