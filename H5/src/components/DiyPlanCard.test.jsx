// DiyPlanCard normalizePlan 测试：模块二卡片扩充字段（难度/耗时/保鲜期/适宜人群/禁忌/情绪标签）
// 后端可能从 design 嵌套或顶层返回，缺失时须回退 null / []（前端显示 —）。
import { describe, expect, it } from 'vitest'
import { normalizePlan } from '../components/DiyPlanCard'

const BASE = {
  plan_id: 'DIY_abc123',
  name: '测试方案',
  style: '韩式',
  recipient: '母亲',
  occasion: '生日',
  design: {
    main_flowers: [{ name: '康乃馨', role: '主花' }],
    fillers: [],
    foliage: [],
    color_scheme: ['粉色'],
    packaging: '雾面纸',
    meaning: '感恩',
  },
}

describe('normalizePlan 卡片扩充字段', () => {
  it('design 内层的扩充字段被归一化到稳定字段', () => {
    const p = normalizePlan({
      ...BASE,
      design: {
        ...BASE.design,
        difficulty: '进阶',
        est_time: 45,
        shelf_life: '约 5-7 天',
        suitable_for: ['母亲', '长辈'],
        caution: '康乃馨花萼易散，请轻拿轻放',
        mood_tags: ['温馨', '感恩'],
      },
    })
    expect(p.difficulty).toBe('进阶')
    expect(p.estTime).toBe(45)
    expect(p.shelfLife).toBe('约 5-7 天')
    expect(p.suitableFor).toEqual(['母亲', '长辈'])
    expect(p.caution).toContain('轻拿轻放')
    expect(p.moodTags).toEqual(['温馨', '感恩'])
  })

  it('顶层的扩充字段同样被读取（兼容混合结构）', () => {
    const p = normalizePlan({
      ...BASE,
      difficulty: '入门',
      est_time: 30,
      shelf_life: '约 3-5 天',
      suitable_for: '朋友、同事',
      caution: '忌暴晒',
      mood_tags: '治愈、宁静',
    })
    expect(p.difficulty).toBe('入门')
    expect(p.estTime).toBe(30)
    expect(p.shelfLife).toBe('约 3-5 天')
    expect(p.suitableFor).toEqual(['朋友', '同事'])
    expect(p.caution).toBe('忌暴晒')
    expect(p.moodTags).toEqual(['治愈', '宁静'])
  })

  it('旧方案缺扩充字段时回退 null / []（卡片显示 — 不崩）', () => {
    const p = normalizePlan(BASE)
    expect(p.difficulty).toBeNull()
    expect(p.estTime).toBeNull()
    expect(p.shelfLife).toBeNull()
    expect(p.suitableFor).toEqual([])
    expect(p.caution).toBeNull()
    expect(p.moodTags).toEqual([])
  })
})
