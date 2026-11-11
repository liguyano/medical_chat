import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('设备管理入口', () => {
  it('在护士端顶部导航提供设备页，并读取真实连接状态', () => {
    const layout = readFileSync(new URL('../../src/components/layout/NurseLayout.tsx', import.meta.url), 'utf8');
    expect(layout).toContain("name: '设备管理', href: '/nurse/devices'");
    const page = readFileSync(new URL('../../src/app/nurse/devices/page.tsx', import.meta.url), 'utf8');
    expect(page).toContain("'/api/tasks/devices'");
    expect(page).toContain('当前没有设备连接');
    expect(page).toContain('尚未登记设备');
    expect(page).toContain('设备状态获取失败');
    expect(page).toContain('待登记申请');
    expect(page).toContain('同意登记');
    expect(page).toContain('verification_code: code.trim()');
  });
});
