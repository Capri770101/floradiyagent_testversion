// utils/status.js 单元测试：订单状态徽章元数据（四页共用，禁止各页写死配色）
import { describe, expect, it } from 'vitest'
import { STATUS_META, statusMeta } from './status'

describe('statusMeta', () => {
  it('覆盖完整状态机', () => {
    expect(Object.keys(STATUS_META).sort()).toEqual(
      ['canceled', 'created', 'done', 'paid', 'pending_payment', 'shipped'].sort(),
    )
  })

  it('各状态文案正确', () => {
    expect(statusMeta('created').label).toBe('待付款')
    expect(statusMeta('pending_payment').label).toBe('待付款')
    expect(statusMeta('paid').label).toBe('待发货')
    expect(statusMeta('shipped').label).toBe('配送中')
    expect(statusMeta('done').label).toBe('已完成')
    expect(statusMeta('canceled').label).toBe('已取消')
  })

  it('状态间配色有区分（待付款≠配送中≠已完成）', () => {
    const clsOf = (s) => statusMeta(s).cls
    expect(clsOf('created')).not.toBe(clsOf('shipped'))
    expect(clsOf('shipped')).not.toBe(clsOf('done'))
  })

  it('未知状态回退为原样文案', () => {
    expect(statusMeta('refunded').label).toBe('refunded')
  })
})