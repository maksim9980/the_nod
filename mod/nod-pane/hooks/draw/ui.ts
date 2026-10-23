import type { Elements, RenderElement } from 'claude-code'
import type { Actions } from '../actions'

/** Elements common to desktop and terminal: the drawing functions take only these. */
export type Ui = Pick<Elements['desktop'] & Elements['terminal'], 'Box' | 'Text' | 'Button' | 'Input' | 'Markdown'>

/** A drawing function: a ready model and the actions in, a tree out; it does not know atoms. */
export type Draw<M> = (ui: Ui, model: M, actions: Actions, width: number) => RenderElement
