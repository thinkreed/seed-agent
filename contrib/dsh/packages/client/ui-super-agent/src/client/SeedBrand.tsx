/** seed-agent 品牌：侧栏 mark 与名字（替换 DSH 官方品牌位）。 */
import { createElement } from 'react'

/** 种子/嫩芽标记：一个圆点 + 两片叶子，取自 "seed" 的意象。 */
export function SeedBrandMark(props: { readonly size: number }): React.ReactElement {
  const size = props.size
  return createElement(
    'svg',
    { width: size, height: size, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': true },
    createElement('circle', { cx: 10, cy: 12.4, r: 3.4, fill: '#4176e6' }),
    createElement('path', { d: 'M10 8.6c0-2.6 1.7-4.4 4.3-4.6-.1 2.7-1.8 4.5-4.3 4.6Z', fill: '#16a34a' }),
    createElement('path', { d: 'M9.6 8.2C9.4 6.1 8 4.7 5.8 4.6c.2 2.2 1.6 3.7 3.8 3.9Z', fill: '#4ade80' }),
  )
}

/** 品牌名：seed-agent（sentence case 由产品名决定）。 */
export function SeedBrandName(): React.ReactElement {
  return createElement('span', {
    style: { fontWeight: 650, letterSpacing: '-0.01em', fontSize: 'inherit' },
  }, 'seed-agent')
}