// Protection against a double load. Two plugins named nod (the installed one and CLAUDE_CODE_PLUGIN_DIRS on the
// same folder) share one pane and the same $.state keys, and a press may go to an instance that did not draw this
// button. The owner is the instance whose token `<id>@<root>` lies in the instance atom: only session.start writes
// it, the last writer does the background work. The pane is drawn by whichever instance the drawing reached —
// always by itself, writing nothing. Only pure decisions here; the atoms are in register.tsx.
import type { Texts } from './texts/index'

/** Role in the background work: my token, a previous load of my folder, or another instance. */
export type Role = 'draw' | 'claim' | 'pass'

export function tokenOf(id: string, root: string): string {
  return id + '@' + root
}

/** Root of the mod from a token: everything after the first "@" (an id of [0-9a-z] holds no "@"). */
export function rootOf(token: string): string {
  return token.slice(token.indexOf('@') + 1)
}

/** Owner: the atom is empty or holds my token. */
export function isOwner(stored: string | null, mine: string): boolean {
  return stored === null || stored.startsWith(mine + '@')
}

/**
 * Role for the background work (timer, tool.call, the session.start chain): a foreign token of another folder —
 * `pass`, that instance does the background work. A drawing does not use the role (viewOf).
 */
export function roleOf(stored: string | null, mine: string, root: string): Role {
  if (stored === null || isOwner(stored, mine)) return 'draw'

  return rootOf(stored) === root ? 'claim' : 'pass'
}

/** The owner's warning line: a second root is recorded and it is not mine. */
export function doubleLoad(myRoot: string, otherRoot: string | null, t: Texts): string | null {
  return otherRoot === null || otherRoot === myRoot ? null : t.doubleLoadLine(myRoot, otherRoot)
}

/** What a drawing knows about the owner: the token read or why it was not read. */
export type OwnerRead = { ok: true; value: string | null } | { ok: false; error: string }

/**
 * The pane view by the instance atom. A drawing ALWAYS draws: it writes nothing and passes nothing down.
 * A foreign token of my folder is a previous load (`stale`), drawn as mine. A token of another folder is a second
 * instance (`foreignRoot`): drawn by me with the double-load line. Not read — drawn.
 */
export function viewOf(owner: OwnerRead, mine: string, root: string): { stale: string | null; foreignRoot: string | null } {
  if (!owner.ok || owner.value === null || isOwner(owner.value, mine)) return { stale: null, foreignRoot: null }
  const other = rootOf(owner.value)

  return other === root ? { stale: owner.value, foreignRoot: null } : { stale: null, foreignRoot: other }
}
