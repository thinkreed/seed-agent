/** Super-agent 工作台：DSH 侧栏入口 + 工单面板。 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import { SuperAgentIcon } from './SuperAgentIcon.tsx'
import { SuperAgentPage } from './SuperAgentPanel.tsx'
import { SeedBrandMark, SeedBrandName } from './SeedBrand.tsx'

export const inject = ['slots']

const PANEL_ID = 'super-agent'

/** 注册侧栏入口与主面板。 */
export function apply(ctx: ClientContext): void {
  ctx.slots.inject('sidebar.brand.mark', () => ctx.slots.register({ name: 'sidebar.brand.mark' }, SeedBrandMark))
  ctx.slots.inject('sidebar.brand.name', () => ctx.slots.register({ name: 'sidebar.brand.name' }, SeedBrandName))
  ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
    name: 'sidebar.panellist', id: PANEL_ID, order: 5, label: () => 'Super-agent',
  }, SuperAgentIcon))
  ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: PANEL_ID }, SuperAgentPage))
}