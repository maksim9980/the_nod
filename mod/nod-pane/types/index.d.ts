declare module 'claude-code' {
  interface PluginState {
    'nod': {
      stateDir: string | null
      panePlaced: boolean
      nodPrefix: readonly string[] | null | 'unknown'
      snapshot: unknown
      loadError: string | null
      lastMtime: number
      sinceFrom: string | null
      draft: string
      expanded: string[]
      freeFor: string | null
      instance: string | null
      otherRoot: string | null
    }
  }
}
