import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const page = readFileSync(new URL('../../src/app/nurse/tasks/create/page.tsx', import.meta.url), 'utf8');

describe('护士创建任务表单', () => {
  it('将嵌入式设备放在执行方式中', () => {
    const participantSection = page.split('本次参与人')[1]?.split('执行方式')[0];
    const executionSection = page.split('执行方式</h2>')[1];
    expect(participantSection).not.toContain("value: 'embedded_device'");
    expect(executionSection).toContain("value: 'embedded_device'");
    expect(executionSection).toContain('选择设备');
  });

  it('使用默认场景和提交时间，并简化备注标签', () => {
    expect(page).toContain("const scene = 'admission'");
    expect(page).toContain('plannedStartTime: new Date().toISOString()');
    expect(page).not.toContain('计划开始时间');
    expect(page).not.toContain('护士备注');
    expect(page).toContain('>备注</label>');
  });
});
