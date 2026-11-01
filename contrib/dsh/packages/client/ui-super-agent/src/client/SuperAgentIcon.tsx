/** 侧栏入口图标。 */
import { createElement } from 'react'

export function SuperAgentIcon(props: { readonly size: number; readonly active: boolean }): React.ReactElement {
  const color = props.active ? '#4176e6' : 'currentColor'
  return createElement(
    'svg',
    { width: props.size, height: props.size, viewBox: '0 0 16 16', fill: 'none', 'aria-hidden': true },
    createElement('rect', { x: 2, y: 2, width: 12, height: 12, rx: 3, stroke: color, strokeWidth: 1.5 }),
    createElement('path', { d: 'M5 6h6M5 8.5h4', stroke: color, strokeWidth: 1.5, strokeLinecap: 'round' }),
  )
}