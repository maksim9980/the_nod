// Registering /nod, checked against the engine registry: after each `$.command.register` attempt the mod asks
// `$.command.list()` and names the fact in one line ("in the engine registry: yes/no"). No atoms here;
// register.tsx decides when to retry and what to write to the transcript.
import type { CommandInfo, EngineInterface } from 'claude-code'

import { settleWithin, tryRead } from './state'
import { texts } from './texts/index'

export const COMMAND = 'nod'

/** Limits of `$.command.register` and `$.command.list()`: attempt (a) runs before next(e) and must not hold the start. */
const REGISTER_MS = 2000
const LIST_MS = 2000

/** What the registry answered: our list entry (null — none) or the reason the list was not received. */
export type Listed = { listed: CommandInfo | null; listError: string | null }

/** Outcome of an attempt: the registration error (null — it resolved) and the registry answer. */
export type RegFact = Listed & { error: string | null }

type Engine = Pick<EngineInterface, 'command' | 'clock'>

const describe = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/** Whether /nod is in the registry after an attempt; null — no attempt yet. */
export function isListed(fact: RegFact | null): boolean {
  return fact !== null && fact.listed !== null
}

/** The /nod entry of the command list, if it is there. */
export function findNod(list: readonly CommandInfo[]): CommandInfo | null {
  return list.find(c => c !== null && typeof c === 'object' && c.name === COMMAND) ?? null
}

/** Asks the engine registry; does not throw and does not hang longer than LIST_MS. */
export async function listNod($: Engine): Promise<Listed> {
  // Parsing inside the bounded read: a malformed answer (not an array) is "the command list did not answer", not a throw.
  const read = async (): Promise<CommandInfo | null> => {
    const list: unknown = await $.command.list()
    if (!Array.isArray(list)) throw new Error(texts().listMalformed)

    return findNod(list as CommandInfo[])
  }
  const got = await tryRead($, { read, write: async () => undefined }, LIST_MS)

  return got.ok ? { listed: got.value, listError: null } : { listed: null, listError: got.error }
}

/** One attempt: registration (a repeat replaces the previous one, see the `command.register` types), then the registry. */
export async function registerNod($: Engine): Promise<RegFact> {
  let error: string | null = null
  let settled = false
  // The name is a literal: by it validate knows that the command.run{command=nod} hook answers its own command.
  const work = $.command.register({ name: 'nod', description: texts().commandDescription }).then(
    () => { settled = true },
    (err: unknown) => {
      if (!settled) error = describe(err)
      settled = true
    },
  )
  // No answer within the limit — the fact "no — registration did not answer in 2 s"; a late answer does not change it.
  if (!(await settleWithin($, work, REGISTER_MS)) && !settled) {
    settled = true
    error = texts().registerTimeout
  }

  return { error, ...(await listNod($)) }
}

/** The fact in one line: "/nod registered, in the engine registry: yes (plugin …)" or "… no — reason". */
export function factLine(fact: RegFact): string {
  const { listed } = fact
  const why = fact.error ?? whyMissing(fact)

  return texts().registryLine(fact.error, sourceOf(listed), why)
}

/** /nod in a load without an attempt (a hot reload without session.start): only the registry answer. */
export function listedLine(got: Listed): string {
  const t = texts()

  return t.noAttempt + ' — ' + t.registryTail(sourceOf(got.listed), whyMissing(got))
}

function sourceOf(listed: CommandInfo | null): string | null {
  if (listed === null) return null

  return listed.plugin === undefined ? listed.source : 'plugin ' + listed.plugin
}

function whyMissing(got: Listed): string {
  return got.listError === null ? texts().listMissing : texts().listFailed(got.listError)
}
