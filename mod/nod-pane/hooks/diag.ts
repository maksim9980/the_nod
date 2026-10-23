// Tail of the /nod answer — diagnostics in one answer, without the pane: who I am, who owns the pane, what is
// being written now, what was last and whether the pane is redrawn. Pure functions: register.tsx gathers the values.
import type { LastAction } from './state'
import type { Texts } from './texts/index'

/** The instance atom: read (the value) or silent (the reason). */
export type StoredOwner = { ok: true; value: string | null } | { ok: false; error: string }

export type DiagInput = {
  id: string
  root: string
  /** Registration fact of /nod by the engine registry (command.ts, factLine). */
  registry: string
  owner: StoredOwner
  /** Line about a double load (owner.ts) or null. */
  double: string | null
  pending: string | null
  lastStatus: string | null
  lastAction: LastAction | null
  renders: number
  renderedAt: number | null
}

function ownerLine(owner: StoredOwner, id: string, t: Texts): string {
  if (!owner.ok) return t.ownerSilent(owner.error)
  if (owner.value === null) return t.ownerUnset()

  return owner.value.startsWith(id + '@') ? t.ownerMine() : t.ownerForeign(owner.value)
}

/** Diagnostic lines in order; each on a new line of the answer. */
export function diagLines(d: DiagInput, t: Texts): string[] {
  return [
    t.selfLine(d.id, d.root),
    d.registry,
    ownerLine(d.owner, d.id, t),
    ...(d.double === null ? [] : [d.double]),
    t.pendingLine(d.pending),
    t.lastPressLine(d.lastStatus),
    d.lastAction === null ? t.noActionLine : t.lastActionLine(d.lastAction),
    t.rendersLine(d.renders, d.renderedAt),
  ]
}
